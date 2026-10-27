#!/bin/bash
# moon-notes-test.sh — standalone test for examples/apps/moon-notes.fg.
# Runs the app for real and verifies real outputs (grep on real output,
# exit codes, and the notes.txt file itself). Exits non-zero on failure.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
FORGE="$REPO/forge.py"
APP="$DIR/moon-notes.fg"
FAIL=0
fail() { echo "FAIL: $1"; FAIL=1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1

run() { python3 "$FORGE" run "$APP" "$@" 2>&1; }

echo "== list on empty dir (no notes.txt yet) =="
OUT="$(run list)"; CODE=$?
echo "$OUT"
[ "$CODE" -eq 0 ] || fail "list on empty: expected exit 0, got $CODE"
echo "$OUT" | grep -q "no notes yet" || fail "list on empty should print 'no notes yet'"

echo "== add two notes =="
OUT="$(run add Shopping buy milk and eggs)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "add Shopping: exit $CODE"
echo "$OUT" | grep -q "saved Shopping" || fail "add should confirm 'saved Shopping'"
OUT="$(run add Ideas build a treehouse)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "add Ideas: exit $CODE"
[ -f notes.txt ] || fail "notes.txt not created"
grep -q "Shopping buy milk and eggs" notes.txt || fail "notes.txt missing Shopping line"
grep -q "Ideas build a treehouse" notes.txt || fail "notes.txt missing Ideas line"

echo "== list shows both =="
OUT="$(run list)"
echo "$OUT" | grep -q "^Shopping$" || fail "list missing Shopping"
echo "$OUT" | grep -q "^Ideas$" || fail "list missing Ideas"

echo "== show =="
OUT="$(run show Shopping)"
echo "$OUT" | grep -q "buy milk and eggs" || fail "show Shopping missing body"

echo "== search =="
OUT="$(run search milk)"
echo "$OUT" | grep -q "^Shopping$" || fail "search milk should find Shopping"
echo "$OUT" | grep -q "^Ideas$" && fail "search milk should not find Ideas"
OUT="$(run search treehouse)"
echo "$OUT" | grep -q "^Ideas$" || fail "search treehouse should find Ideas"
OUT="$(run search zebra)"
echo "$OUT" | grep -q "no matches" || fail "search zebra should print 'no matches'"

echo "== add with no body + upsert =="
OUT="$(run add Reminder)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "add Reminder (no body): exit $CODE"
OUT="$(run show Reminder)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "show Reminder: exit $CODE"
OUT="$(run add Shopping buy bread)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "upsert Shopping: exit $CODE"
OUT="$(run show Shopping)"
echo "$OUT" | grep -q "buy bread" || fail "upsert: new body missing"
echo "$OUT" | grep -q "milk" && fail "upsert: old body still present"
OUT="$(run list)"
echo "$OUT" | grep -q "^Shopping$" || fail "list after upsert missing Shopping"
[ "$(echo "$OUT" | grep -c "^Shopping$")" -eq 1 ] || fail "upsert duplicated Shopping"

echo "== remove =="
OUT="$(run remove Ideas)"; CODE=$?
[ "$CODE" -eq 0 ] || fail "remove Ideas: exit $CODE"
echo "$OUT" | grep -q "removed Ideas" || fail "remove should confirm"
OUT="$(run list)"
echo "$OUT" | grep -q "^Ideas$" && fail "list after remove still shows Ideas"
echo "$OUT" | grep -q "^Shopping$" || fail "list after remove lost Shopping"

echo "== errors exit nonzero =="
run show Ideas >/dev/null 2>&1; CODE=$?
[ "$CODE" -ne 0 ] || fail "show of missing note should exit nonzero"
run remove Ideas >/dev/null 2>&1; CODE=$?
[ "$CODE" -ne 0 ] || fail "remove of missing note should exit nonzero"
OUT="$(run frobnicate)"; CODE=$?
[ "$CODE" -ne 0 ] || fail "unknown command should exit nonzero"
echo "$OUT" | grep -q "usage: moon-notes" || fail "unknown command should print usage"
OUT="$(run)"; CODE=$?
[ "$CODE" -ne 0 ] || fail "no args should exit nonzero"
echo "$OUT" | grep -q "usage: moon-notes" || fail "no args should print usage"

echo "== remove last notes, back to empty =="
run remove Shopping >/dev/null 2>&1
run remove Reminder >/dev/null 2>&1
OUT="$(run list)"
echo "$OUT" | grep -q "no notes yet" || fail "list after removing all should print 'no notes yet'"

if [ "$FAIL" -ne 0 ]; then echo "moon-notes-test: FAILED"; exit 1; fi
echo "moon-notes-test: ALL PASSED"
