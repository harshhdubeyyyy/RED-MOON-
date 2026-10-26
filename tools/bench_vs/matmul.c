#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static long long now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}
int main(void) {
    int n = 128;
    double *a = malloc(sizeof(double) * n * n);
    double *b = malloc(sizeof(double) * n * n);
    double *c = malloc(sizeof(double) * n * n);
    for (int i = 0; i < n * n; i++) { a[i] = 1.0; b[i] = 2.0; }
    long long t = now_us();
    for (int r = 0; r < n; r++)
        for (int col = 0; col < n; col++) {
            double s = 0.0;
            for (int k = 0; k < n; k++) s += a[r * n + k] * b[k * n + col];
            c[r * n + col] = s;
        }
    double total = 0.0;
    for (int i = 0; i < n * n; i++) total += c[i];
    printf("matmul checksum = %f us = %lld\n", total, now_us() - t);
    return 0;
}
