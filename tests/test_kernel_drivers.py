#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 8: drivers.

UART driver (putc/getc) and timer driver (mtime/mtimecmp,
interrupt enable, sleep) over MMIO. Sleep blocks the task
until its wake time; the timer interrupt wakes due tasks and
preemptively switches. Tick period is 1000 model steps.
Interrupts resume at mepc, ecalls at mepc + 4.

The kernel (examples/os/kernel_drivers.fg) spawns A (sleeps
6 ticks, prints A) and B (sleeps 1 tick, prints B), then
waits for both. Expects the exact transcript KERNBADONE (B
before A proves wake ordering — the first version used 3 vs
1 ticks and the two wake times landed in the same tick
interval, so A printed first; 6 vs 1 gives a ~3000-step
margin over the ~1900-step scheduling jitter), halted, main
running, both children done, and at least 6 timer ticks
fired. Exits 0 only if every test passes.
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


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def main():
    print("drivers UART + timer sleep (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_drv")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_drivers.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNBADONE", uart == "KERNBADONE", uart)
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("final states [running, done, done, free]",
              [word(d, 0x8000 + 16 * i) for i in range(4)] == [2, 3, 3, 0])
        check("timer fired repeatedly", word(d, 0x804C) >= 6,
              str(word(d, 0x804C)))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
