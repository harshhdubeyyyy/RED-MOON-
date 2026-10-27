#!/bin/sh
# Install The Jal Pari Language (1.0.0) for the current user.
# Usage, from a checkout of RED-MOON-:
#   sh scripts/install.sh
# Usage, without cloning first (needs git):
#   git clone https://github.com/harshhdubeyyyy/RED-MOON- && cd RED-MOON- && sh scripts/install.sh
# What it does:
#   1. Checks python3 and a C compiler (cc) are present.
#   2. Symlinks bin/jalpari into ~/.local/bin/jalpari.
#   3. Verifies: jalpari --version and jalpari run examples/jal_pari_demo.fg
# It does NOT need root, and it does NOT change your system Python.
set -e
if ! command -v python3 >/dev/null 2>&1; then
    echo "install: python3 not found — install Python 3 from python.org, then run this again." >&2
    exit 1
fi
if ! command -v cc >/dev/null 2>&1; then
    echo "install: no C compiler (cc) found — install gcc / Xcode Command Line Tools / Build Tools, then run this again." >&2
    exit 1
fi
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
if [ ! -f "$REPO_DIR/forge.py" ]; then
    echo "install: forge.py not found in $REPO_DIR — run this script from a RED-MOON- checkout." >&2
    exit 1
fi
mkdir -p "$HOME/.local/bin"
ln -sf "$REPO_DIR/bin/jalpari" "$HOME/.local/bin/jalpari"
chmod +x "$REPO_DIR/bin/jalpari"
export PATH="$HOME/.local/bin:$PATH"
echo "installed: $HOME/.local/bin/jalpari"
"$HOME/.local/bin/jalpari" --version
"$HOME/.local/bin/jalpari" run "$REPO_DIR/examples/jal_pari_demo.fg"
echo ""
echo "Done. If 'jalpari' is not found in a new terminal, add this line to your shell profile:"
echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
