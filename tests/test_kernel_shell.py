#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 6: shell.

A REPL over UART RX: prompt, line input with echo, dispatch on
the first character (freestanding rejects string values, so
commands are single characters): h = help, p = procs, s =
spawn the demo task, w = wait for the last spawned task, q =
quit, anything else = ?. The shell yields while waiting for
input and once per iteration, so spawned tasks run between
keystrokes. Input arrives through the model's input_bytes
queue (added by this checkpoint — the model previously had no
RX input at all).

The kernel (examples/os/kernel_shell.fg) is fed the lines h,
x, s, w, p, q. Expects the exact transcript (the H and I
landing between prompts proves tasks run between keystrokes;
the p output proves the child went ready -> done), halted,
main running, the child done, and the last pid recorded.
Exits 0 only if every test passes.
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

EXPECTED = ("KERN\n"
            "> h\n"
            "h p s w q\n"
            "> x\n"
            "?\n"
            "> s\n"
            "H> w\n"
            "IW0\n"
            "> p\n"
            "P0:2 P1:3 P2:0 P3:0 \n"
            "> q\n"
            "BYE\n")


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def main():
    print("shell REPL (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_shell")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_shell.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex", input_bytes=b"h\nx\ns\nw\np\nq\n")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript", uart == EXPECTED, repr(uart))
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("final states [running, done, free, free]",
              [word(d, 0x8000 + 16 * i) for i in range(4)] == [2, 3, 0, 0])
        check("last pid recorded", word(d, 0x8044) == 1)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
