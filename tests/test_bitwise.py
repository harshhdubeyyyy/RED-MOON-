#!/usr/bin/env python3
"""End-to-end tests for the bitwise operators & | ^ << >> ~.

Bitwise ops are the first language capability on the road to a
from-scratch OS (device registers are all bitfields). Semantics,
pinned here on every backend that supports them:

  * & | ^ operate on ints, two's-complement.
  * << wraps through the unsigned width (never UB for negative
    left operands, unlike plain C).
  * >> is an arithmetic shift (sign-extending).
  * Shift counts are masked: to 0..63 on native (i64) and WASM
    (i64), to 0..31 on big32 (32-bit words). Counts >= the word
    width therefore differ across backends by design; the tests
    below only assert masking on native/WASM, and only small
    counts on big32.
  * Precedence is C-like: | loosest, then ^, then &, then
    ==/!=, then comparisons, then << >>, then + -, then * / %.

Tests:
  1. native: & | ^ values
  2. native: << >> values, including negative >> (arithmetic)
  3. native: ~ values
  4. native: precedence (1 << 2 + 3 == 32; 2 | 3 & 1 == 3)
  5. native: shift-count masking (1 << 64 == 1; 256 >> 65 == 128)
  6. native: wrap (1 << 62, 1 << 63 == INT_MIN)
  7. native: checker rejects float & int, str | str, ~bool
  8. WASM: & | ^ << >> ~ via main()'s return value
  9. big32: build + model run, UART transcript (32-bit values)
 10. fmt: formatting a bitwise program is stable and keeps the ops

Exits 0 only if every test passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS {name}")
    else:
        print(f"  FAIL {name} {detail}")
        FAILURES.append(name)


def write_prog(d, prog, name="prog.fg"):
    path = os.path.join(d, name)
    with open(path, "w") as f:
        f.write(prog)
    return path


def run_native(prog):
    d = tempfile.mkdtemp(prefix="bitwise-test-")
    path = write_prog(d, prog)
    r = subprocess.run(FORGE + ["run", path], capture_output=True,
                       text=True, timeout=60)
    return r


def run_wasm_value(expr):
    """Build a program whose main returns expr; return its stdout."""
    d = tempfile.mkdtemp(prefix="bitwise-wasm-")
    path = write_prog(d, f"fn main() -> int {{ return {expr}; }}\n")
    out = os.path.join(d, "prog.wasm")
    r = subprocess.run(FORGE + ["build", path, "--target", "wasm", "-o", out],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return None, r.stderr
    r2 = subprocess.run(["node", os.path.join(ROOT, "tools", "run_wasm.mjs"), out],
                        capture_output=True, text=True, timeout=60)
    return r2.stdout.strip(), r2.stderr


def main():
    print("native values")
    prog = """fn main() {
  println(12 & 10);
  println(12 | 10);
  println(12 ^ 10);
  println(255 & 15);
  println(0 | 0);
  println(1 << 10);
  println(1024 >> 3);
  println(256 >> 8);
  println(-8 >> 2);
  println(~0);
  println(~5);
  println(1 << 2 + 3);
  println(2 | 3 & 1);
  println(1 << 64);
  println(256 >> 65);
  println(1 << 62);
  println(1 << 63);
}
"""
    r = run_native(prog)
    expected = ("8\n14\n6\n15\n0\n1024\n128\n1\n-2\n-1\n-6\n"
                "32\n3\n1\n128\n4611686018427387904\n-9223372036854775808\n")
    check("native & | ^ << >> ~ + precedence + masking + wrap",
          r.returncode == 0 and r.stdout == expected,
          f"rc={r.returncode} out={r.stdout!r} err={r.stderr!r}")

    print("checker rejections")
    for name, bad in [
        ("float & int", "fn main() { println(1.5 & 2); }\n"),
        ("str | str", 'fn main() { println("a" | "b"); }\n'),
        ("~bool", "fn main() { println(~true); }\n"),
        ("int & bool", "fn main() { println(3 & true); }\n"),
    ]:
        d = tempfile.mkdtemp(prefix="bitwise-check-")
        path = write_prog(d, bad)
        r = subprocess.run(FORGE + ["check", path], capture_output=True,
                           text=True, timeout=60)
        check(f"checker rejects {name}", r.returncode != 0,
              f"rc={r.returncode} out={r.stdout!r}")

    print("wasm values")
    for expr, want in [("12 & 10", "8"), ("12 | 10", "14"),
                       ("12 ^ 10", "6"), ("1 << 10", "1024"),
                       ("1024 >> 3", "128"), ("-8 >> 2", "-2"),
                       ("~5", "-6"), ("1 << 64", "1"),
                       ("1 << 2 + 3", "32")]:
        got, err = run_wasm_value(expr)
        check(f"wasm {expr} == {want}", got == want, f"got={got!r} err={err!r}")

    print("big32 build + model run")
    if os.path.exists(MODEL):
        d = tempfile.mkdtemp(prefix="bitwise-big32-")
        path = write_prog(d, """fn main() {
  println(12 & 10);
  println(12 | 10);
  println(12 ^ 10);
  println(1 << 10);
  println(1024 >> 3);
  println(-8 >> 2);
  println(~5);
  println(1 << 30);
}
""")
        out = os.path.join(d, "prog")
        r = subprocess.run(FORGE + ["build", path, "--target", "big32", "-o", out],
                           capture_output=True, text=True, timeout=120)
        hexpath = out + ".hex"
        if r.returncode != 0 or not os.path.exists(hexpath):
            check("big32 build", False, f"rc={r.returncode} err={r.stderr!r}")
        else:
            r2 = subprocess.run([sys.executable, MODEL, hexpath],
                                capture_output=True, text=True, timeout=120)
            uart = ""
            if "uart:\n" in r2.stdout:
                uart = r2.stdout.split("uart:\n", 1)[1]
            check("big32 model uart transcript",
                  uart.strip() == "8\n14\n6\n1024\n128\n-2\n-6\n1073741824",
                  f"uart={uart!r} full={r2.stdout!r} err={r2.stderr!r}")
    else:
        print("  SKIP big32 (model.py not found)")

    print("fmt stability")
    d = tempfile.mkdtemp(prefix="bitwise-fmt-")
    path = write_prog(d, "fn main() {\nprintln(12&10);\nprintln(1<<2+3);\n}\n")
    r = subprocess.run(FORGE + ["fmt", path], capture_output=True,
                       text=True, timeout=60)
    with open(path) as f:
        once = f.read()
    r2 = subprocess.run(FORGE + ["fmt", path], capture_output=True,
                        text=True, timeout=60)
    with open(path) as f:
        twice = f.read()
    check("fmt keeps ops and is idempotent",
          r.returncode == 0 and "12 & 10" in once and "1 << 2 + 3" in once
          and once == twice, f"once={once!r} twice={twice!r}")

    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
