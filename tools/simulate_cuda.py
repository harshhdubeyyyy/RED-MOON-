"""Simulate the CUDA kernels in Python, thread-by-thread, to prove
the kernel algorithm is correct — this is NOT execution on a GPU.

It mirrors forge_lang/codegen_cuda.py exactly:
- dot: 256 threads per block, shared-memory tree reduction,
  one partial per block, host sums the partials.
- matmul: 16x16 thread blocks, one thread per output cell.

Run: python3 tools/simulate_cuda.py
Expected: cuda dot = 70, cuda matmul = 19 22 43 50
(the same numbers the CPU-thread kernels and the serial code give).
"""

def cuda_dot(a, b):
    n = len(a)
    blocks = (n + 255) // 256
    partials = []
    for blk in range(blocks):
        s = [0.0] * 256
        for tid in range(256):
            i = blk * 256 + tid
            s[tid] = a[i] * b[i] if i < n else 0.0
        stride = 128
        while stride > 0:
            for tid in range(stride):
                s[tid] += s[tid + stride]
            stride >>= 1
        partials.append(s[0])
    return sum(partials)


def cuda_matmul(a, b, n):
    out = [0.0] * (n * n)
    for by in range((n + 15) // 16):
        for bx in range((n + 15) // 16):
            for ty in range(16):
                for tx in range(16):
                    r = by * 16 + ty
                    c = bx * 16 + tx
                    if r >= n or c >= n:
                        continue
                    s = 0.0
                    for k in range(n):
                        s += a[r * n + k] * b[k * n + c]
                    out[r * n + c] = s
    return out

import math

def cuda_embedding(tokens, emb, posemb, d, use_pos=True):
    out = []
    for pos, tok in enumerate(tokens):
        for c in range(d):
            v = emb[tok * d + c]
            if use_pos:
                v += posemb[pos * d + c]
            out.append(v)
    return out


def cuda_layernorm(x, gamma, beta, rows, d, eps=0.00001):
    out = []
    for r in range(rows):
        row = x[r * d:(r + 1) * d]
        mean = sum(row) / d
        var = sum((v - mean) ** 2 for v in row) / d
        inv = 1.0 / math.sqrt(var + eps)
        for c in range(d):
            out.append((row[c] - mean) * inv * gamma[c] + beta[c])
    return out


def cuda_attention(q, k, v, seq, d):
    out = []
    for i in range(seq):
        scores = []
        for j in range(seq):
            if j <= i:
                s = sum(q[i * d + c] * k[j * d + c] for c in range(d))
                scores.append(s / math.sqrt(d))
            else:
                scores.append(-1e30)
        m = max(scores[:i + 1])
        exps = [math.exp(scores[j] - m) if j <= i else 0.0 for j in range(seq)]
        denom = sum(exps[:i + 1])
        probs = [e / denom if j <= i else 0.0 for j, e in enumerate(exps)]
        for c in range(d):
            out.append(sum(probs[j] * v[j * d + c] for j in range(i + 1)))
    return out


def cuda_matmul_half(a, b, n):
    import numpy as np
    ah = np.array(a, dtype=np.float16).reshape(n, n)
    bh = np.array(b, dtype=np.float16).reshape(n, n)
    out = []
    for r in range(n):
        for c in range(n):
            s = np.float16(0.0)
            for k in range(n):
                s = np.float16(s + np.float16(ah[r, k] * bh[k, c]))
            out.append(float(s))
    return out


if __name__ == "__main__":
    a = [1.0, 2.0, 3.0, 4.0]
    b = [5.0, 6.0, 7.0, 8.0]
    print("cuda dot =", cuda_dot(a, b))
    print("cuda matmul =", *cuda_matmul(a, b, 2))
    assert cuda_dot(a, b) == 70.0
    assert cuda_matmul(a, b, 2) == [19.0, 22.0, 43.0, 50.0]
    emb = cuda_embedding([0, 1, 0], [1.0, 0.0, 0.0, 1.0],
                         [0.0] * 6, 2, True)
    print("cuda embedding =", *emb)
    assert emb == [1.0, 0.0, 0.0, 1.0, 1.0, 0.0]
    ln = cuda_layernorm(emb, [1.0, 1.0], [0.0, 0.0], 3, 2)
    print("cuda layernorm =", *ln)
    assert abs(ln[0] - 1.0) < 0.001 and abs(ln[1] + 1.0) < 0.001
    att = cuda_attention(emb, emb, emb, 3, 2)
    print("cuda attention =", *att)
    assert abs(att[0] - 1.0) < 1e-9 and abs(att[1]) < 1e-9
    assert abs(att[2] - 0.330238) < 0.001 and abs(att[3] - 0.669762) < 0.001
    half = cuda_matmul_half(a, b, 2)
    print("cuda half matmul =", *half)
    assert half == [19.0, 22.0, 43.0, 50.0]
    print("cuda simulation ok — algorithm matches serial/CPU results")
