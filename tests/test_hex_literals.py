#!/usr/bin/env python3
"""Hex integer literal tests (lexer-only change).

Covers: native arithmetic with 0x literals, a big32 model kernel that
uses 0x10000000 as the UART address (the address kernels used to spell
as 268435456), and the error for a bare 0x with no hex digit.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
MODEL = os.path.expanduser("~/workspace/big32/tools/model.py")
FAILURES = []

NATIVE_SRC = """fn main() {
  println(0xFF);
  println(0x10 + 1);
  println(0xFFFFFFFF);
}
"""

KERNEL_SRC = """fn put(c: int) {
  poke32(0x10000000, c);
}

fn print_int(v: int) {
  if v < 0 {
    put(45);
    print_int(0 - v);
    return;
  }
  if v >= 10 {
    print_int(v / 10);
  }
  put(48 + v % 10);
}

fn trap_handler(frame: int) {
  let cause = csr_read(834);
  if cause < 0 {
    poke32(0x10000018, 0 - 1);
    poke32(0x1000001C, 0 - 1);
    return;
  }
  csr_write(833, csr_read(833) + 4);
}

fn main() {
  print_int(0xFF);
  put(10);
  print_int(0x2A);
  put(10);
  put(68);
  put(79);
  put(78);
  put(69);
  put(10);
  csr_write(773, 0);
  let h = ecall(0, 0);
}
"""


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("hex literals")
    with tempfile.TemporaryDirectory() as td:
        nsrc = os.path.join(td, "hex_native.fg")
        with open(nsrc, "w") as f:
            f.write(NATIVE_SRC)
        nout = os.path.join(td, "hex_native")
        r = subprocess.run(FORGE + ["build", "-o", nout, nsrc],
                           capture_output=True, text=True, cwd=ROOT)
        check("native builds", r.returncode == 0, r.stderr[-300:])
        if r.returncode == 0:
            r2 = subprocess.run([nout], capture_output=True, text=True)
            check("native values", r2.stdout == "255\n17\n4294967295\n",
                  repr(r2.stdout))
        ksrc = os.path.join(td, "hex_kernel.fg")
        with open(ksrc, "w") as f:
            f.write(KERNEL_SRC)
        kout = os.path.join(td, "hex_kernel")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", kout, ksrc],
                           capture_output=True, text=True, cwd=ROOT)
        check("kernel builds freestanding big32", r.returncode == 0,
              r.stderr[-300:])
        if r.returncode == 0:
            spec = importlib.util.spec_from_file_location("big32model", MODEL)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.run(kout + ".hex")
            uart = res["uart"].decode("utf-8", "replace")
            check("kernel halts", res["halted"] is True)
            check("kernel transcript", uart == "255\n42\nDONE\n", repr(uart))
        bad = os.path.join(td, "hex_bad.fg")
        with open(bad, "w") as f:
            f.write("fn main() {\n  println(0x);\n}\n")
        r = subprocess.run(FORGE + ["build", "-o", os.path.join(td, "bad"),
                                    bad], capture_output=True, text=True,
                           cwd=ROOT)
        check("bare 0x rejected", r.returncode != 0 and "hex digit" in
              (r.stdout + r.stderr), r.stderr[-200:])
    if FAILURES:
        print("FAILED:", FAILURES)
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
