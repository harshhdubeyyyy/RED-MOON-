import time
xs = []
x = 42
for _ in range(1000000):
    x = (x * 1103515245 + 12345) % 2147483647
    xs.append(x)
t = time.perf_counter()
total = 0
for v in xs:
    total += v * 3 + v % 7
print(f"sum = {total} us = {int((time.perf_counter() - t) * 1e6)}")
