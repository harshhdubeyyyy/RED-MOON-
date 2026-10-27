#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 2: free-list allocator.

Checkpoint 1 could only bump-allocate; freed memory was lost.
Here every block carries an 8-byte header [next, total_size]
before its payload, and freed blocks live in an address-ordered
singly linked list. alloc first-fit searches the list, splits
when the remainder is at least 16 bytes, else takes the block
whole, and falls back to bump allocation; free inserts
address-ordered and coalesces with the next physical neighbour
first, then the previous one.

The kernel (examples/os/kernel_freelist.fg) allocs a, b, c,
frees b, allocs d (must reuse b's exact block), frees a, c, d
(adjacent — must coalesce into one block), allocs 48 (must
succeed from the coalesced space), and verifies patterns at each
step, printing K per passed check and E per failed one.

Expects the exact transcript KERNKKKKDONE, halted, and the
predicted heap state: a 16-byte split remainder at 0xA038 as
the free-list head, and e's pattern at 0xA008. Exits 0 only if
every test passes.
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
    print("free-list allocator (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_freelist")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_freelist.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        spec = importlib.util.spec_from_file_location("big32model", MODEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        res = mod.run(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNKKKKDONE", uart == "KERNKKKKDONE", uart)
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("split remainder is free-list head",
              word(d, 0x8044) == 0xA038, hex(word(d, 0x8044)))
        check("remainder size is 16", word(d, 0xA038 + 4) == 16,
              str(word(d, 0xA038 + 4)))
        check("coalesced alloc pattern intact", word(d, 0xA008) == 99)
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
