# Forge CUDA kernels — ready to run on a CUDA GPU

This VM has no GPU and no nvcc, so this .cu file cannot run here.
On a machine with a CUDA GPU and nvcc, run:

    nvcc -o kernel kernel.cu
    ./kernel

Expected output (same as the CPU-thread kernels and the serial code):

    cuda dot = 70.000000
    cuda matmul = 19.000000 22.000000 43.000000 50.000000

The kernel algorithm itself is verified in this repo by
`tools/simulate_cuda.py`, which runs the exact same block/thread
logic in Python and asserts those same numbers. That simulation
is not GPU execution — it proves the algorithm, not the hardware.
