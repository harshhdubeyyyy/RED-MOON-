#!/usr/bin/env python3
"""Combined-workflow check for RED-MOON- x BLACK-MOON-OS-.

Verifies, with no network access:
  1. All jalos.fg copies are byte-identical:
     - RED-MOON- examples/os/jalos.fg (source of truth)
     - BLACK-MOON-OS- jalos.fg (vendored root copy)
     - BLACK-MOON-OS- distro/archiso/airootfs/usr/share/blackmoon/jalos.fg
  2. The RED-MOON- compiler builds the source copy and its demo output
     matches BLACK-MOON-OS- tests/expected_output.txt (modulo CR).
  3. The single-command `ai` and `audit` commands print their markers.

Usage:
  python3 tools/check_jalos_sync.py --blackmoon ../jalos-push
  python3 tools/check_jalos_sync.py --blackmoon /path/to/blackmoon-checkout

Exit 0 only if every check passes; otherwise prints FAIL lines and
exits 1. Run this before any release touching either repository.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "examples", "os", "jalos.fg")
FORGE = os.path.join(ROOT, "forge.py")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, timeout=300, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blackmoon", required=True,
                    help="BLACK-MOON-OS- checkout (staging dir works)")
    ap.add_argument("--forge", default=FORGE)
    args = ap.parse_args()
    bm = args.blackmoon
    fails = []

    def check(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name + (f" ({detail})" if detail and not ok else ""))
        if not ok:
            fails.append(name)

    copies = {
        "RED-MOON- source": SRC,
        "BLACK-MOON-OS- root": os.path.join(bm, "jalos.fg"),
        "BLACK-MOON-OS- distro": os.path.join(
            bm, "distro", "archiso", "airootfs", "usr", "share", "blackmoon", "jalos.fg"),
    }
    hashes = {}
    for name, path in copies.items():
        if not os.path.isfile(path):
            check(f"exists: {name}", False, f"missing {path}")
        else:
            hashes[name] = sha256(path)
            check(f"exists: {name}", True)
    if len(set(hashes.values())) == 1 and len(hashes) == 3:
        check("all 3 jalos.fg copies byte-identical", True)
    elif len(hashes) == 3:
        check("all 3 jalos.fg copies byte-identical", False,
              f"hashes differ: {hashes}")

    expected = os.path.join(bm, "tests", "expected_output.txt")
    if not os.path.isfile(expected):
        check("BLACK-MOON-OS- expected output present", False, f"missing {expected}")
        expected = None
    else:
        check("BLACK-MOON-OS- expected output present", True)

    with tempfile.TemporaryDirectory(prefix="jalos-sync-") as td:
        binary = os.path.join(td, "jalos")
        r = run([sys.executable, args.forge, "build", SRC, "-o", binary])
        check("compiler builds jalos.fg", r.returncode == 0,
              (r.stderr or r.stdout)[-300:] if r.returncode else "")
        if r.returncode == 0 and expected:
            demo = run([binary], cwd=td)
            got = demo.stdout.replace("\r", "")
            with open(expected, encoding="utf-8") as f:
                want = f.read()
            check("demo output matches expected (254 lines)",
                  got == want,
                  f"got {len(got.splitlines())} lines, want {len(want.splitlines())}")
            ai = run([binary, "ai"], cwd=td)
            check("ai command marker",
                  "perceptron learned OR in 4 epochs" in ai.stdout, ai.stdout[-200:])
            audit = run([binary, "audit"], cwd=td)
            check("audit command marker",
                  "permission model is owner-or-root only" in audit.stdout,
                  audit.stdout[-200:])

    print()
    if fails:
        print(f"SYNC CHECK FAILED: {len(fails)} failing check(s): {', '.join(fails)}")
        return 1
    print("SYNC CHECK PASSED: RED-MOON- and BLACK-MOON-OS- agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
