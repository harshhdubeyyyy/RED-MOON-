#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 7: GUI.

There is no framebuffer hardware in the model or the
Verilog, so the GUI is a text windowing system over UART:
ANSI-drawn boxes, rendered by the terminal. Windows have
single-character titles (freestanding rejects string values),
and focus is a redraw, since there is no back-buffer.

The kernel (examples/os/kernel_gui.fg) clears the screen,
draws window A at (2,2,10,4), window B at (5,4,10,4)
overlapping A, draws A again (bring to front), then prints
DONE. Expects the exact ANSI byte stream and halted. Exits 0
only if every test passes.
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

EXPECTED = ("\x1b[2J\x1b[H"
            "\x1b[2;2H+A-------+\x1b[3;2H|        |\x1b[4;2H|        |"
            "\x1b[5;2H+--------+"
            "\x1b[4;5H+B-------+\x1b[5;5H|        |\x1b[6;5H|        |"
            "\x1b[7;5H+--------+"
            "\x1b[2;2H+A-------+\x1b[3;2H|        |\x1b[4;2H|        |"
            "\x1b[5;2H+--------+"
            "DONE\n")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("GUI terminal windows (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_gui")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_gui.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact ANSI transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
