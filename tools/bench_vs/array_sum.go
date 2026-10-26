package main
import ("fmt"; "time")
func main() {
    xs := make([]int64, 0, 1000000)
    var x int64 = 42
    for i := 0; i < 1000000; i++ {
        x = (x*1103515245 + 12345) % 2147483647
        xs = append(xs, x)
    }
    t := time.Now()
    var total int64 = 0
    for _, v := range xs { total += v*3 + v%7 }
    fmt.Printf("sum = %d us = %d\n", total, time.Since(t).Microseconds())
}
