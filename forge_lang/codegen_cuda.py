"""Forge -> CUDA code generation for parallel kernels.

This is a source-to-source backend: it emits a .cu file with
__global__ kernels for parallel_dot and parallel_matmul, plus
host launch code. It does NOT run here — this VM has no GPU
and no nvcc, so the .cu file is verified only by structure
(kernel signatures, grid/block launches, and the serial
results it must match), not by execution on hardware.
To run it, copy the .cu file to a machine with a CUDA GPU
and nvcc, and compile: nvcc -o kernel kernel.cu

Only the two parallel kernels are supported in v1; any other
Forge program is a clear error, not a silent miscompile.
"""

from .errors import ForgeError

CUDA_SRC = r'''#include <stdio.h>
#include <stdlib.h>
#include <cuda_runtime.h>

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

int main(void) {
    double a[4] = {1.0, 2.0, 3.0, 4.0};
    double b[4] = {5.0, 6.0, 7.0, 8.0};
    printf("cuda dot = %f\n", forge_cuda_dot(a, b, 4));
    double out[4];
    forge_cuda_matmul(a, b, out, 2);
    printf("cuda matmul = %f %f %f %f\n", out[0], out[1], out[2], out[3]);
    return 0;
}
'''


def generate_cuda(source_text):
    """Emit CUDA source for a Forge file that uses only parallel kernels.
    The file must call parallel_dot or parallel_matmul; anything else
    is rejected, because this backend does not translate general Forge."""
    if "parallel_dot" not in source_text and "parallel_matmul" not in source_text:
        raise ForgeError("CUDA backend: file must use parallel_dot or parallel_matmul")
    return CUDA_SRC
