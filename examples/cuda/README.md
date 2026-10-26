# Forge CUDA kernels — VERIFIED ON A REAL GPU

Verified 26 Oct 2026 on Kaggle (GPU notebook, private,
`arshhdubeyy/forge-cuda-kernel`, version 2):
- GPU: 2x Tesla T4, 15360 MiB each, NVIDIA driver 580.178.04
- nvcc: CUDA compilation tools, release 12.8, V12.8.93
- Real output from the GPU run:
    cuda dot = 70.000000
    cuda matmul = 19.000000 22.000000 43.000000 50.000000

These match the CPU-thread kernels, the serial code, and the
`tools/simulate_cuda.py` simulation exactly.

This VM itself has no GPU and no nvcc, so the .cu file cannot
run here. On any machine with a CUDA GPU and nvcc, run:

    nvcc -o kernel kernel.cu
    ./kernel

and expect the same output as above. The Kaggle notebook that
produced the verified run is in `kaggle/` (private, GPU
enabled, writes its output to `cuda_output.txt`).

## Transformer kernels (0.2.0, simulation-verified only)
`kernel.cu` now also has: `forge_embedding_kernel`,
`forge_layernorm_kernel` (launch with blockDim.x == d, d a power
of two), `forge_attention_kernel` (fused QK^T + softmax + PV, one
block per query position, seq <= 256, d <= 256) and
`forge_matmul_half_kernel` (fp16, via `__half`).
`tools/simulate_cuda.py` mirrors them exactly: embedding
1 0 0 1 1 0, layernorm ±0.99998, attention rows
1.0/0.0, 0.330/0.670, 0.802/0.198, half matmul 19 22 43 50.
VERIFIED on a real GPU 26 Oct 2026 — Kaggle notebook v4
(arshhdubeyy/forge-cuda-kernel), 2x Tesla T4, driver 580.178.04,
nvcc 12.8.93: dot 70, matmul 19 22 43 50, embedding
1 0 0 1 1 0, layernorm ±0.999980, attention 1.0/0.0,
0.330238/0.669762, 0.802224/0.197776, half matmul
19 22 43 50 — matching tools/simulate_cuda.py to 6 decimals.
Notebook v3 failed to build (`__half2double` does not exist
in CUDA; fixed to `(double)__half2float`); v4 is the run
above. The dot/matmul kernels were also verified on T4 in
the earlier run.
