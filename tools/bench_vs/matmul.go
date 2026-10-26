package main
import ("fmt"; "time")
func main() {
    n := 128
    a := make([]float64, n*n)
    b := make([]float64, n*n)
    for i := range a { a[i] = 1.0; b[i] = 2.0 }
    t := time.Now()
    c := make([]float64, n*n)
    for r := 0; r < n; r++ {
        for col := 0; col < n; col++ {
            s := 0.0
            for k := 0; k < n; k++ { s += a[r*n+k] * b[k*n+col] }
            c[r*n+col] = s
        }
    }
    total := 0.0
    for _, v := range c { total += v }
    fmt.Printf("matmul checksum = %v us = %d\n", total, time.Since(t).Microseconds())
}
