use std::time::Instant;
fn fib(n: i64) -> i64 {
    if n < 2 { return n; }
    fib(n - 1) + fib(n - 2)
}
fn main() {
    let t = Instant::now();
    let r = fib(35);
    println!("fib(35) = {} us = {}", r, t.elapsed().as_micros());
}
