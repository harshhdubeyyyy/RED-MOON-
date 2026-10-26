#include <stdio.h>
#include <time.h>
static long long fib(long long n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}
static long long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}
int main(void) {
    long long t = now_us();
    long long r = fib(35);
    printf("fib(35) = %lld us = %lld\n", r, now_us() - t);
    return 0;
}
