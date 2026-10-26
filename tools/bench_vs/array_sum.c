#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static long long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}
int main(void) {
    long long *xs = malloc(sizeof(long long) * 1000000);
    long long x = 42;
    for (int i = 0; i < 1000000; i++) {
        x = (x * 1103515245LL + 12345) % 2147483647LL;
        xs[i] = x;
    }
    long long t = now_us();
    long long total = 0;
    for (int i = 0; i < 1000000; i++) total += xs[i] * 3 + xs[i] % 7;
    printf("sum = %lld us = %lld\n", total, now_us() - t);
    return 0;
}
