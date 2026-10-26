"""Build a static, centrally-hostable registry from a local registry dir.

Usage:
    python3 tools/make_static_registry.py <local_registry_dir> <output_dir>

Output layout (push output_dir to a GitHub repo, enable Pages, and
clients can discover/pull from https://<user>.github.io/<repo>/):
    packages.json
    packages/<name>/<version>/<file>.fg

packages.json format:
    {"packages": [{"name": ..., "versions": [...], "files": {"<version>": [...]}}]}

Clients fetch packages.json, then the .fg files, with no server
code running — this is the static-registry pattern (like a Go
module proxy backed by git), not a dynamic POST server.
"""

import json
import os
import shutil
import sys


def main():
    if len(sys.argv) != 3:
        print("usage: make_static_registry.py <local_registry_dir> <output_dir>", file=sys.stderr)
        return 1
    src, out = sys.argv[1], sys.argv[2]
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    packages = []
    if os.path.isdir(src):
        for name in sorted(os.listdir(src)):
            base = os.path.join(src, name)
            if not os.path.isdir(base):
                continue
            versions = sorted(os.listdir(base))
            files_by_version = {}
            for version in versions:
                vdir = os.path.join(base, version)
                srcdir = os.path.join(vdir, "src")
                files = sorted(os.listdir(srcdir)) if os.path.isdir(srcdir) else []
                files_by_version[version] = files
                for fname in files:
                    dst = os.path.join(out, "packages", name, version, fname)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copyfile(os.path.join(srcdir, fname), dst)
            packages.append({"name": name, "versions": versions, "files": files_by_version})
    with open(os.path.join(out, "packages.json"), "w", encoding="utf-8") as f:
        json.dump({"packages": packages}, f, indent=2)
    print(f"static registry: {len(packages)} package(s) in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
