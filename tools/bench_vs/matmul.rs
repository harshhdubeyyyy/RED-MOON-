use std::time::Instant;
fn main() {
    let n: usize = 128;
    let a = vec![1.0f64; n * n];
    let b = vec![2.0f64; n * n];
    let t = Instant::now();
    let mut c = vec![0.0f64; n * n];
    for r in 0..n {
        for col in 0..n {
            let mut s = 0.0;
            for k in 0..n { s += a[r * n + k] * b[k * n + col]; }
            c[r * n + col] = s;
        }
    }
    let total: f64 = c.iter().sum();
    println!("matmul checksum = {} us = {}", total, t.elapsed().as_micros());
}
