#!/usr/bin/env python3
"""End-to-end test for the network device kernel.

The kernel (examples/os/kernel_netdev.fg, SOC2-only) runs
its SLIP + checksum + echo stack against the SOC2 serial
packet device at 0x10003000, with the testbench as the
peer: it verifies both packets the kernel transmits, then
sends a reflection (ESC path), a corrupted packet (drop
path), and a pong. Expects the TB's NETDEV PASS line, the
kernel halted, and the transcript KERN / PONG / S2R2D1 /
DONE. The model cannot run this kernel (it has no net
device), so the check is the SOC2 simulation itself.
Exits 0 only if every test passes.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = [sys.executable, os.path.join(ROOT, "forge.py")]
BIG32 = os.path.expanduser("~/workspace/big32")
PROOF = os.path.expanduser("~/workspace/rx-proof")
FAILURES = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def main():
    print("network device kernel (SOC2 simulation)")
    with tempfile.TemporaryDirectory() as td:
        soc2_fg = os.path.join(td, "kernel_netdev_soc2.fg")
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "tools", "rebase_soc2.py"),
             os.path.join(ROOT, "examples", "os", "kernel_netdev.fg"),
             soc2_fg], capture_output=True, text=True, cwd=ROOT)
        check("rebase succeeds", r.returncode == 0, r.stderr[-200:])
        out = os.path.join(td, "kern_netdev")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding",
                                    "--stack-top", "0x800F0000",
                                    "-o", out, soc2_fg],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        vvp = os.path.join(td, "tb_netdev.vvp")
        r = subprocess.run(["iverilog", "-o", vvp,
                            os.path.join(BIG32, "src", "big32_core_pipe.v"),
                            os.path.join(BIG32, "src", "big32_soc2.v"),
                            os.path.join(PROOF, "tb_netdev.v")],
                           capture_output=True, text=True)
        check("SOC2 + testbench compile", r.returncode == 0, r.stderr[-500:])
        tx = os.path.join(td, "net_tx.txt")
        r = subprocess.run(["vvp", vvp, f"+HEX={out}.hex", f"+TXOUT={tx}"],
                           capture_output=True, text=True, timeout=600)
        check("peer verdict NETDEV PASS", "NETDEV PASS" in r.stdout,
              r.stdout.strip().splitlines()[-3:])
        with open(tx, encoding="utf-8", errors="replace") as f:
            uart = f.read()
        check("exact transcript",
              uart == "KERN\nPONG\nS2R2D1\nDONE\n", repr(uart))
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
