package main
import ("fmt"; "time")
func fib(n int64) int64 {
    if n < 2 { return n }
    return fib(n-1) + fib(n-2)
}
func main() {
    t := time.Now()
    r := fib(35)
    fmt.Printf("fib(35) = %d us = %d\n", r, time.Since(t).Microseconds())
}
