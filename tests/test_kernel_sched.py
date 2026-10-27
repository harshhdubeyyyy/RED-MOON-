#!/usr/bin/env python3
"""End-to-end tests for Phase E checkpoint 2: preemptive round-robin
scheduler on big32.

Mechanism (backend stub change, Phase E): the trap stub now passes
the trap-frame pointer in a0 (no-arg handlers ignore it, so Phase D
programs keep working) and, after the handler returns, switches
stacks if the handler wrote a non-zero frame pointer to mscratch
(832). The scheduler handler uses that: on every timer tick it
saves the current task's frame+mepc into its TCB, loads the next
task's, and hands the next frame to the stub through mscratch.
Tasks are created by fork: ecall(2, 0) copies the 120-byte trap
frame onto a fresh stack, sets the child's saved-a0 slot to 0 and
the parent's to 1, records the child in TCB[1], and advances mepc
past the ecall for both (forgetting the parent's advance
re-executes the ecall forever).

The kernel (examples/os/kernel_sched.fg) prints KERN, forks into
task_a/task_b (each printing its letter until tick 20, when the
handler clears mtvec and the next ecall halts). Slice boundaries
depend on step timing, so the test asserts structure, not an exact
transcript: starts with KERN, both letters present in bulk,
repeated switching both ways, halted, tick count exactly 20.

Also checks the handler signature rule: a trap_handler with two
parameters, or one non-int parameter, is rejected with a clear
error. Exits 0 only if every test passes.
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


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_model(hexpath):
    spec = importlib.util.spec_from_file_location("big32model", MODEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(hexpath)


def build_src(src, extra=None):
    with tempfile.TemporaryDirectory() as td:
        srcp = os.path.join(td, "t.fg")
        open(srcp, "w").write(src)
        out = os.path.join(td, "t")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out, srcp],
                           capture_output=True, text=True, cwd=ROOT)
        return r


def main():
    print("round-robin scheduler (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_sched")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_sched.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        res = run_model(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("starts with KERN", uart.startswith("KERN"))
        check("both tasks printed in bulk",
              uart.count("A") > 200 and uart.count("B") > 200,
              f"A={uart.count('A')} B={uart.count('B')}")
        trans = sum(1 for a, b in zip(uart, uart[1:])
                    if {a, b} == {"A", "B"})
        check("switches repeatedly both ways", trans >= 10, str(trans))
        check("halts", res["halted"] is True)
        check("tick count exactly 20", res["dmem"][0x8000] == 20,
              str(res["dmem"][0x8000]))
    print("handler signature rules")
    r = build_src("fn trap_handler(a: int, b: int) {}\nfn main() {}\n")
    check("two-param handler rejected",
          r.returncode != 0 and "trap_handler" in r.stderr, r.stderr[-120:])
    r = build_src("fn trap_handler(frame: str) {}\nfn main() {}\n")
    check("non-int handler param rejected",
          r.returncode != 0 and "trap_handler" in r.stderr, r.stderr[-120:])
    r = build_src("fn trap_handler(frame: int) {}\nfn main() {}\n")
    check("one-int handler accepted", r.returncode == 0, r.stderr[-120:])
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
