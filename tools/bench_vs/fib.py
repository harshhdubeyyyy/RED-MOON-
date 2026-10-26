import sys, time
sys.setrecursionlimit(10000)
def fib(n):
    if n < 2: return n
    return fib(n - 1) + fib(n - 2)
t = time.perf_counter()
r = fib(35)
print(f"fib(35) = {r} us = {int((time.perf_counter() - t) * 1e6)}")
