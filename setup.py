#!/usr/bin/env python3
"""Packaging for The Jal Pari Language (pip install path).

`pip install .` installs the `jalpari-pip` command and the
whole repo tree under <prefix>/share/jalpari, where the
command finds forge.py. Publishing to PyPI is a separate
step needing the maintainer's PyPI account/token and is
NOT done by this file.
"""
import os
import re
import sys
from setuptools import setup

ROOT = os.path.dirname(os.path.abspath(__file__))
EXCLUDE_DIRS = {".git", "__pycache__", ".github", "data_scaled"}
# examples/big32/out is generated output; data_scaled is large
# training data that pip users can regenerate with
# tools/prepare_tinystories.py --out-dir data_scaled.
EXCLUDE_PATHS = {"examples/big32/out"}


def version():
    text = open(os.path.join(ROOT, "forge.py")).read()
    m = re.search(r'VERSION = "([^"]+)"', text)
    return m.group(1) if m else "0.0.0"


def tree_files():
    # data_files installs each entry's files flat into its
    # target directory, so group by directory to preserve
    # the tree (forge_lang/, stdlib/, examples/, ...).
    grouped = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel_dir = os.path.relpath(dirpath, ROOT)
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS
                       and os.path.join(rel_dir, d) not in EXCLUDE_PATHS]
        for fn in sorted(filenames):
            if fn.endswith(".pyc") or fn in ("setup.py",):
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), ROOT)
            if rel.startswith("examples/big32/out/"):
                continue
            target = "share/jalpari" if rel_dir == "." else os.path.join("share/jalpari", rel_dir)
            grouped.setdefault(target, []).append(os.path.join(dirpath, fn))
    return [(d, sorted(fs)) for d, fs in sorted(grouped.items())]


setup(
    name="jalpari",
    version=version(),
    description="The Jal Pari Language — a small, safe, fast language with an ML stack",
    author="Jayant Dubey",
    license="MIT",
    python_requires=">=3.10",
    packages=[],
    py_modules=[],
    scripts=[os.path.join(ROOT, "bin", "jalpari-pip")],
    data_files=tree_files(),
)
