use std::time::Instant;
fn main() {
    let mut xs: Vec<i64> = Vec::with_capacity(1000000);
    let mut x: i64 = 42;
    for _ in 0..1000000 {
        x = (x * 1103515245 + 12345) % 2147483647;
        xs.push(x);
    }
    let t = Instant::now();
    let mut total: i64 = 0;
    for v in &xs { total += v * 3 + v % 7; }
    println!("sum = {} us = {}", total, t.elapsed().as_micros());
}
