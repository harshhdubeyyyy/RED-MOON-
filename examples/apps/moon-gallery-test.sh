#!/bin/bash
# moon-gallery-test.sh — standalone test for examples/apps/moon-gallery.fg.
# Runs the app for real and verifies real outputs (grep/counts, not
# echo-only checks). Exits non-zero on any failure.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
FORGE="$REPO/forge.py"
APP="$DIR/moon-gallery.fg"
PNG="$REPO/../jalos-push/distro/archiso/airootfs/usr/share/backgrounds/blackmoon-pixel.png"
# Fall back to the repo-independent copy if the layout differs.
if [ ! -f "$PNG" ]; then
    PNG="$HOME/workspace/jalos-push/distro/archiso/airootfs/usr/share/backgrounds/blackmoon-pixel.png"
fi
FAIL=0
fail() { echo "FAIL: $1"; FAIL=1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1

echo "== moon-gallery: two images =="
OUT="$(python3 "$FORGE" run "$APP" "$PNG" "$WORK/second-image.png" 2>&1)"
CODE=$?
echo "$OUT"
[ "$CODE" -eq 0 ] || fail "expected exit 0, got $CODE"
echo "$OUT" | grep -q "gallery: 2 images -> gallery.html" || fail "count line missing/wrong"
[ -f "$WORK/gallery.html" ] || fail "gallery.html not written"
grep -q "blackmoon-pixel.png" "$WORK/gallery.html" || fail "real PNG path missing from gallery.html"
grep -q "second-image.png" "$WORK/gallery.html" || fail "second path missing from gallery.html"
IMG_COUNT="$(grep -c "<img" "$WORK/gallery.html")"
[ "$IMG_COUNT" -eq 2 ] || fail "expected 2 <img> tags, got $IMG_COUNT"
head -1 "$WORK/gallery.html" | grep -q "<!DOCTYPE html>" || fail "gallery.html is not an HTML page"

echo "== moon-gallery: no args =="
OUT2="$(python3 "$FORGE" run "$APP" 2>&1)"
CODE2=$?
[ "$CODE2" -eq 1 ] || fail "no-args expected exit 1, got $CODE2"
echo "$OUT2" | grep -q "usage:" || fail "no-args usage message missing"

if [ "$FAIL" -eq 0 ]; then
    echo "moon-gallery-test: ALL PASS"
    exit 0
else
    echo "moon-gallery-test: FAILURES PRESENT"
    exit 1
fi
