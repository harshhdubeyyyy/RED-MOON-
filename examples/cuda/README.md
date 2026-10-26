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
