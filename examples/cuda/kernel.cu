#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>
#include <cuda_fp16.h>

__global__ void forge_dot_kernel(const double *a, const double *b, double *partial, long long n) {
    __shared__ double s[256];
    long long tid = threadIdx.x;
    long long i = blockIdx.x * blockDim.x + tid;
    double v = (i < n) ? a[i] * b[i] : 0.0;
    s[tid] = v;
    __syncthreads();
    for (int stride = 128; stride > 0; stride >>= 1) {
        if (tid < stride) s[tid] += s[tid + stride];
        __syncthreads();
    }
    if (tid == 0) partial[blockIdx.x] = s[0];
}

double forge_cuda_dot(const double *a, const double *b, long long n) {
    double *da, *db, *dpartial;
    cudaMalloc(&da, sizeof(double) * n);
    cudaMalloc(&db, sizeof(double) * n);
    int blocks = (int)((n + 255) / 256);
    cudaMalloc(&dpartial, sizeof(double) * blocks);
    cudaMemcpy(da, a, sizeof(double) * n, cudaMemcpyHostToDevice);
    cudaMemcpy(db, b, sizeof(double) * n, cudaMemcpyHostToDevice);
    forge_dot_kernel<<<blocks, 256>>>(da, db, dpartial, n);
    double *partial = (double *)malloc(sizeof(double) * blocks);
    cudaMemcpy(partial, dpartial, sizeof(double) * blocks, cudaMemcpyDeviceToHost);
    double total = 0.0;
    for (int i = 0; i < blocks; i++) total += partial[i];
    cudaFree(da); cudaFree(db); cudaFree(dpartial); free(partial);
    return total;
}

__global__ void forge_matmul_kernel(const double *a, const double *b, double *out, long long n) {
    long long r = blockIdx.y * blockDim.y + threadIdx.y;
    long long c = blockIdx.x * blockDim.x + threadIdx.x;
    if (r >= n || c >= n) return;
    double s = 0.0;
    for (long long k = 0; k < n; k++) s += a[r * n + k] * b[k * n + c];
    out[r * n + c] = s;
}

void forge_cuda_matmul(const double *a, const double *b, double *out, long long n) {
    double *da, *db, *dout;
    cudaMalloc(&da, sizeof(double) * n * n);
    cudaMalloc(&db, sizeof(double) * n * n);
    cudaMalloc(&dout, sizeof(double) * n * n);
    cudaMemcpy(da, a, sizeof(double) * n * n, cudaMemcpyHostToDevice);
    cudaMemcpy(db, b, sizeof(double) * n * n, cudaMemcpyHostToDevice);
    dim3 block(16, 16);
    dim3 grid((unsigned)((n + 15) / 16), (unsigned)((n + 15) / 16));
    forge_matmul_kernel<<<grid, block>>>(da, db, dout, n);
    cudaMemcpy(out, dout, sizeof(double) * n * n, cudaMemcpyDeviceToHost);
    cudaFree(da); cudaFree(db); cudaFree(dout);
}


/* ---- Transformer kernels (new in the Mojo-level batch) ---- */
/* These are NOT yet run on a real GPU (no nvcc in this VM, and the
   Kaggle run for this batch has not been launched). They are
   mirrored exactly by tools/simulate_cuda.py, which verifies the
   numbers below; the Kaggle GPU run is the remaining step, not a
   claim made here. Demo sizes assume seq <= 256 and d <= 256. */

__global__ void forge_embedding_kernel(const long long *tokens, const double *emb,
                                       const double *posemb, double *out,
                                       long long seq, long long d, int use_pos) {
    long long idx = blockIdx.x * blockDim.x + threadIdx.x;
    if (idx >= seq * d) return;
    long long pos = idx / d;
    long long c = idx % d;
    double v = emb[tokens[pos] * d + c];
    if (use_pos) v += posemb[pos * d + c];
    out[idx] = v;
}

/* Launch with blockDim.x == d, and d a power of two (the tree
   reduction below assumes it); demo sizes are d=2. */
__global__ void forge_layernorm_kernel(const double *x, const double *gamma,
                                       const double *beta, double *out,
                                       long long rows, long long d, double eps) {
    __shared__ double s[256];
    long long row = blockIdx.x;
    long long tid = threadIdx.x;
    if (row >= rows || tid >= d) return;
    double v = x[row * d + tid];
    s[tid] = v;
    __syncthreads();
    for (int stride = (int)d / 2; stride > 0; stride >>= 1) {
        if (tid < (long long)stride) s[tid] += s[tid + stride];
        __syncthreads();
    }
    double mean = s[0] / (double)d;
    __syncthreads();
    double diff = v - mean;
    s[tid] = diff * diff;
    __syncthreads();
    for (int stride = (int)d / 2; stride > 0; stride >>= 1) {
        if (tid < (long long)stride) s[tid] += s[tid + stride];
        __syncthreads();
    }
    double inv = 1.0 / sqrt(s[0] / (double)d + eps);
    out[row * d + tid] = diff * inv * gamma[tid] + beta[tid];
}

/* Fused single-head causal attention: QK^T + softmax + PV in one
   launch, one block per query position. Scores and probs live in
   shared memory; the PV phase reuses the block's threads as dim
   threads. The softmax max/sum is done by thread 0 (fine for
   seq <= 256; a production kernel would reduce in parallel). */
__global__ void forge_attention_kernel(const double *q, const double *k, const double *v,
                                       double *out, long long seq, long long d) {
    __shared__ double scores[256];
    __shared__ double probs[256];
    __shared__ double mx;
    __shared__ double denom;
    long long i = blockIdx.x;
    long long tid = threadIdx.x;
    if (tid < seq) {
        if (tid <= i) {
            double s = 0.0;
            for (long long c = 0; c < d; c++) s += q[i * d + c] * k[tid * d + c];
            scores[tid] = s / sqrt((double)d);
        } else {
            scores[tid] = -1e30;
        }
    }
    __syncthreads();
    if (tid == 0) {
        double m = scores[0];
        for (long long j = 1; j <= i; j++) if (scores[j] > m) m = scores[j];
        mx = m;
        double sum = 0.0;
        for (long long j = 0; j <= i; j++) sum += exp(scores[j] - m);
        denom = sum;
    }
    __syncthreads();
    if (tid < seq) {
        probs[tid] = (tid <= i) ? exp(scores[tid] - mx) / denom : 0.0;
    }
    __syncthreads();
    if (tid < d) {
        double acc = 0.0;
        for (long long j = 0; j <= i; j++) acc += probs[j] * v[j * d + tid];
        out[i * d + tid] = acc;
    }
}

__global__ void forge_matmul_half_kernel(const __half *a, const __half *b, __half *out, long long n) {
    long long r = blockIdx.y * blockDim.y + threadIdx.y;
    long long c = blockIdx.x * blockDim.x + threadIdx.x;
    if (r >= n || c >= n) return;
    __half s = __float2half(0.0f);
    for (long long k = 0; k < n; k++) s = __hadd(s, __hmul(a[r * n + k], b[k * n + c]));
    out[r * n + c] = s;
}

void forge_cuda_matmul_half(const double *a, const double *b, double *out, long long n) {
    __half *da, *db, *dout;
    cudaMalloc(&da, sizeof(__half) * n * n);
    cudaMalloc(&db, sizeof(__half) * n * n);
    cudaMalloc(&dout, sizeof(__half) * n * n);
    __half *ha = (__half *)malloc(sizeof(__half) * n * n);
    __half *hb = (__half *)malloc(sizeof(__half) * n * n);
    for (long long i = 0; i < n * n; i++) {
        ha[i] = __double2half(a[i]);
        hb[i] = __double2half(b[i]);
    }
    cudaMemcpy(da, ha, sizeof(__half) * n * n, cudaMemcpyHostToDevice);
    cudaMemcpy(db, hb, sizeof(__half) * n * n, cudaMemcpyHostToDevice);
    dim3 block(16, 16);
    dim3 grid((unsigned)((n + 15) / 16), (unsigned)((n + 15) / 16));
    forge_matmul_half_kernel<<<grid, block>>>(da, db, dout, n);
    __half *ho = (__half *)malloc(sizeof(__half) * n * n);
    cudaMemcpy(ho, dout, sizeof(__half) * n * n, cudaMemcpyDeviceToHost);
    for (long long i = 0; i < n * n; i++) out[i] = __half2double(ho[i]);
    cudaFree(da); cudaFree(db); cudaFree(dout);
    free(ha); free(hb); free(ho);
}

int main(void) {
    double a[4] = {1.0, 2.0, 3.0, 4.0};
    double b[4] = {5.0, 6.0, 7.0, 8.0};
    printf("cuda dot = %f\n", forge_cuda_dot(a, b, 4));
    double out[4];
    forge_cuda_matmul(a, b, out, 2);
    printf("cuda matmul = %f %f %f %f\n", out[0], out[1], out[2], out[3]);
    /* Transformer demo: seq=3, d=2, tokens [0, 1, 0], emb rows
       token0=[1,0], token1=[0,1], pos all zero; Q=K=V=input. */
    long long tokens[3] = {0, 1, 0};
    double emb[4] = {1.0, 0.0, 0.0, 1.0};
    double pos[6] = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
    long long *dtok; double *demb, *dpos, *dembout, *dattn, *dln;
    cudaMalloc(&dtok, sizeof(long long) * 3);
    cudaMalloc(&demb, sizeof(double) * 4);
    cudaMalloc(&dpos, sizeof(double) * 6);
    cudaMalloc(&dembout, sizeof(double) * 6);
    cudaMalloc(&dattn, sizeof(double) * 6);
    cudaMalloc(&dln, sizeof(double) * 6);
    cudaMemcpy(dtok, tokens, sizeof(long long) * 3, cudaMemcpyHostToDevice);
    cudaMemcpy(demb, emb, sizeof(double) * 4, cudaMemcpyHostToDevice);
    cudaMemcpy(dpos, pos, sizeof(double) * 6, cudaMemcpyHostToDevice);
    forge_embedding_kernel<<<1, 6>>>(dtok, demb, dpos, dembout, 3, 2, 1);
    double embout[6];
    cudaMemcpy(embout, dembout, sizeof(double) * 6, cudaMemcpyDeviceToHost);
    printf("cuda embedding = %f %f %f %f %f %f\n",
           embout[0], embout[1], embout[2], embout[3], embout[4], embout[5]);
    double gamma[2] = {1.0, 1.0};
    double beta[2] = {0.0, 0.0};
    double *dgamma, *dbeta;
    cudaMalloc(&dgamma, sizeof(double) * 2);
    cudaMalloc(&dbeta, sizeof(double) * 2);
    cudaMemcpy(dgamma, gamma, sizeof(double) * 2, cudaMemcpyHostToDevice);
    cudaMemcpy(dbeta, beta, sizeof(double) * 2, cudaMemcpyHostToDevice);
    forge_layernorm_kernel<<<3, 2>>>(dembout, dgamma, dbeta, dln, 3, 2, 0.00001);
    double lnout[6];
    cudaMemcpy(lnout, dln, sizeof(double) * 6, cudaMemcpyDeviceToHost);
    printf("cuda layernorm = %f %f %f %f %f %f\n",
           lnout[0], lnout[1], lnout[2], lnout[3], lnout[4], lnout[5]);
    forge_attention_kernel<<<3, 256>>>(dembout, dembout, dembout, dattn, 3, 2);
    double attnout[6];
    cudaMemcpy(attnout, dattn, sizeof(double) * 6, cudaMemcpyDeviceToHost);
    printf("cuda attention = %f %f %f %f %f %f\n",
           attnout[0], attnout[1], attnout[2], attnout[3], attnout[4], attnout[5]);
    double hout[4];
    forge_cuda_matmul_half(a, b, hout, 2);
    printf("cuda half matmul = %f %f %f %f\n", hout[0], hout[1], hout[2], hout[3]);
    return 0;
}
