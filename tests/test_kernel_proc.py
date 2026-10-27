#!/usr/bin/env python3
"""End-to-end test for Phase F checkpoint 5: processes.

Process table in scratch 0x8000 (4 slots x 16 bytes [state,
frame, mepc, exit_code]; 0 free, 1 ready, 2 running, 3 done).
Syscalls via ecall: 2 = spawn (fork into a free slot; parent
gets the pid, child gets 0, -1 if no slot), 3 = yield (switch
to the next ready task, round-robin), 4 = exit(code) (mark
done, switch on; if nobody is ready, clear mtvec and ecall,
which halts).

The kernel (examples/os/kernel_proc.fg) spawns two children,
waits for both, then prints DONE. Expects the exact
transcript KERNABABABDONE (the ABABAB interleave is the proof
that switching is real), halted, main running, both children
done with exit code 0, the spare slot free, and pids 1 and 2
recorded in scratch. Also runs a probe program in which the
only task exits with nobody left, proving the halt path.
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

PROBE = """
fn put(c: int) {
  poke32(268435456, c);
}

fn trap_handler(frame: int) {
  let cause = csr_read(834);
  if cause < 0 {
    return;
  }
  let eid = peek32(frame + 60);
  if eid == 4 {
    csr_write(773, 0);
    let h = ecall(0, 0);
    return;
  }
  csr_write(833, csr_read(833) + 4);
}

fn main() {
  put(88);
  let x = ecall(4, 7);
}
"""


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'} {name} {detail}")
    if not cond:
        FAILURES.append(name)


def word(dmem, a):
    return (dmem[a] | (dmem[a + 1] << 8) |
            (dmem[a + 2] << 16) | (dmem[a + 3] << 24))


def run_kernel(path):
    spec = importlib.util.spec_from_file_location("big32model", MODEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.run(path)


def main():
    print("processes spawn/yield/exit/wait (big32 model)")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "kern_proc")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", out,
                                    "examples/os/kernel_proc.fg"],
                           capture_output=True, text=True, cwd=ROOT)
        check("builds freestanding big32", r.returncode == 0, r.stderr[-200:])
        res = run_kernel(out + ".hex")
        uart = res["uart"].decode("utf-8", "replace")
        check("exact transcript KERNABABABDONE",
              uart == "KERNABABABDONE", uart)
        check("halts", res["halted"] is True)
        d = res["dmem"]
        check("final states [running, done, done, free]",
              [word(d, 0x8000 + 16 * i) for i in range(4)] == [2, 3, 3, 0])
        check("exit codes 0",
              [word(d, 0x8000 + 16 * i + 12) for i in range(4)] ==
              [0, 0, 0, 0])
        check("current back to main", word(d, 0x8040) == 0)
        check("pids recorded", word(d, 0x8044) == 1 and
              word(d, 0x8048) == 2)
        probe_src = os.path.join(td, "probe_exit.fg")
        with open(probe_src, "w") as f:
            f.write(PROBE)
        probe_out = os.path.join(td, "probe_exit")
        r = subprocess.run(FORGE + ["build", "--target", "big32",
                                    "--freestanding", "-o", probe_out,
                                    probe_src],
                           capture_output=True, text=True, cwd=ROOT)
        check("exit-alone probe builds", r.returncode == 0, r.stderr[-200:])
        pres = run_kernel(probe_out + ".hex")
        check("exit with nobody left halts",
              pres["halted"] is True and
              pres["uart"].decode("utf-8", "replace") == "X")
    print(f"\n{len(FAILURES)} failure(s): {FAILURES}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
