#!/usr/bin/env python3
"""Integrated kernel test (SOC2 simulation).

Rebases examples/os/kernel_full.fg for SOC2, builds it
freestanding with the SOC2 stack top, compiles the combined
testbench against the SOC2 sources, runs the full shell
tour (with the network peer active), and checks the
verdict, both TX packets, and the exact UART transcript.

The transcript's spawn interleave (H, prompt, I, echo)
is deterministic for this binary and testbench timing;
any change to the kernel or the feeder pacing that moves
a timer tick will show up here first.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROOF = os.path.expanduser("~/workspace/rx-proof")
BIG32 = os.path.expanduser("~/workspace/big32")
TMP = "/tmp"

EXPECTED = (
    "KERN\n"
    "> h\n"
    "h p s w m f g n t v q\n"
    "> p\n"
    "P0:2 P1:0 P2:0 P3:0 \n"
    "> s\n"
    "H> Iw\n"
    "W0\n"
    "> m\n"
    "M80008400\n"
    "> f\n"
    "F\n"
    "> g\n"
    "\x1b[2J\x1b[H"
    "\x1b[2;2H+A-------+\x1b[3;2H|        |\x1b[4;2H|        |\x1b[5;2H+--------+"
    "\x1b[4;5H+B-------+\x1b[5;5H|        |\x1b[6;5H|        |\x1b[7;5H+--------+"
    "\x1b[2;2H+A-------+\x1b[3;2H|        |\x1b[4;2H|        |\x1b[5;2H+--------+\n"
    "> n\n"
    "PONG\n"
    "S2R2D1\n"
    "> t\n"
    "T\n"
    "> v\n"
    "V\n"
    "> q\n"
    "BYE\n"
)


def sh(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def main():
    failures = []

    def check(name, ok, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'} {name} {detail}")
        if not ok:
            failures.append(name)

    r = sh([sys.executable, os.path.join(ROOT, "tools/rebase_soc2.py"),
            os.path.join(ROOT, "examples/os/kernel_full.fg"),
            os.path.join(ROOT, "examples/os/kernel_full_soc2.fg")])
    check("rebase succeeds", r.returncode == 0, r.stderr[-200:])

    b = sh([sys.executable, os.path.join(ROOT, "forge.py"), "build",
            "--target", "big32", "--freestanding",
            "--stack-top", "0x800F0000",
            "-o", os.path.join(TMP, "kern_full"),
            os.path.join(ROOT, "examples/os/kernel_full_soc2.fg")])
    check("builds freestanding big32", b.returncode == 0, b.stderr[-200:])

    c = sh(["iverilog", "-o", os.path.join(PROOF, "tb_full.vvp"),
            os.path.join(BIG32, "src/big32_core_pipe.v"),
            os.path.join(BIG32, "src/big32_soc2.v"),
            os.path.join(PROOF, "tb_full.v")])
    check("SOC2 + testbench compile", c.returncode == 0, c.stderr[-200:])

    v = sh(["vvp", os.path.join(PROOF, "tb_full.vvp"),
            f"+HEX={os.path.join(TMP, 'kern_full.hex')}",
            f"+TXOUT={os.path.join(TMP, 'full_tx.txt')}"],
           timeout=900)
    out = v.stdout + v.stderr
    verdict = [ln for ln in out.splitlines() if "FULL PASS" in ln or "FULL FAIL" in ln]
    check("combined verdict FULL PASS", bool(verdict) and "FULL PASS" in verdict[0], str(verdict))
    check("TX packet 1 OK", "TX packet 1 OK (8 bytes)" in out)
    check("TX packet 2 OK", "TX packet 2 OK (7 bytes)" in out)
    try:
        tx = open(os.path.join(TMP, "full_tx.txt"), "rb").read().decode("ascii")
    except OSError:
        tx = ""
    check("exact shell-tour transcript", tx == EXPECTED,
          f"got {len(tx)} chars, expected {len(EXPECTED)}")
    print(f"\n{len(failures)} failure(s): {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
