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


if __name__ == "__main__":
    a = [1.0, 2.0, 3.0, 4.0]
    b = [5.0, 6.0, 7.0, 8.0]
    print("cuda dot =", cuda_dot(a, b))
    print("cuda matmul =", *cuda_matmul(a, b, 2))
    assert cuda_dot(a, b) == 70.0
    assert cuda_matmul(a, b, 2) == [19.0, 22.0, 43.0, 50.0]
    print("cuda simulation ok — algorithm matches serial/CPU results")
