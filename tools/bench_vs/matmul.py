import time
n = 128
a = [1.0] * (n * n)
b = [2.0] * (n * n)
t = time.perf_counter()
c = [0.0] * (n * n)
for r in range(n):
    for col in range(n):
        s = 0.0
        for k in range(n):
            s += a[r * n + k] * b[k * n + col]
        c[r * n + col] = s
total = sum(c)
print(f"matmul checksum = {total} us = {int((time.perf_counter() - t) * 1e6)}")
