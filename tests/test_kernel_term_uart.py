#!/usr/bin/env python3
"""Terminal command core test (big32 model).

Prompt, echo, backspace, and first-character dispatch over UART
RX. The VRAM window draw is NOT covered here — that still needs
the SOC2 testbench (see kernel_term_uart.fg header).
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

EXPECTED = ("KERN\n> h\nh f c q\n> h\x08 \x08f\nFILE 1\nFILE 2\nFILE 3\n"
            "> c\n[CLR]\n> x\n?\n> q\nBYE\n")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("terminal command core (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_term_uart")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_term_uart.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex", input_bytes=b"h\nh\x08f\nc\nx\nq\n")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
