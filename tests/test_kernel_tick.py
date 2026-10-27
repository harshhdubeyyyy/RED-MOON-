#!/usr/bin/env python3
"""End-to-end test for Phase E checkpoint 1: the first kernel tick.

The Python big32 model gained a minimal timer for Phase E (the
Verilog has no CLINT yet): mtime at 0x10000010, mtimecmp at
0x10000018 (32-bit halves, mtime +1 per step), mip.MTIP
level-sensitive while mtime >= mtimecmp. Delivery needs mtvec set,
mstatus.MIE and mie.MTIE set; trap entry saves MIE into MPIE and
clears MIE, mret restores it — otherwise the first handler
instruction would re-trap before the handler could reprogram
mtimecmp.

The kernel (examples/os/kernel_tick.fg) enables ONLY the timer
interrupt, so its handler needs no mcause dispatch: every trap is a
tick. Handler state lives in RAM scratch 0x8000 (freestanding
programs have no globals). The handler bumps the tick count, prints
'T', and reprograms mtimecmp past mtime before mret; main prints
KERN, arms the timer, spins to 5 ticks, prints DONE, and returns
(returning halts: main's ending clears mtvec first).

Expects the exact UART transcript KERNTTTTTDONE and halted=True
(not a 1M-step slide). Also checks the model rejects nothing new:
the Phase D trap suite still passes unchanged (run separately).
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
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def run_model(hexpath):
    sys.path.insert(0, os.path.dirname(MODEL))
    import importlib.util
    spec = importlib.util.spec_from_file_location("big32model", MODEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(hexpath)


def main():
    print("kernel tick (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_tick")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_tick.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        res = run_model(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNTTTTTDONE", uart == "KERNTTTTTDONE", uart)
        check("halts (not a slide)", res["halted"] is True)
        check("tick count in scratch is 5",
              res["dmem"][0x8000] == 5, str(res["dmem"][0x8000]))
        check("sane step count (< 20000)", res["steps"] < 20000,
              str(res["steps"]))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
