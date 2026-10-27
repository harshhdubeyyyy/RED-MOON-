#!/bin/bash
# Moon Code scripted test: pipes fixed command sessions into
# moon-code.fg, then checks the saved files byte-for-byte (diff)
# and the printed output (grep for key lines). No network, no
# repo changes outside the temp dir.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || exit 1
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0

fail() { echo "FAIL: $1"; FAIL=1; }
ok() { echo "PASS: $1"; }

check_grep() { # file, fixed-string, label
    if grep -Fq "$2" "$1"; then ok "$3"; else fail "$3 (missing: $2)"; fi
}
check_file() { # got, expected, label
    if diff -u "$2" "$1" > "$TMP/diff.txt" 2>&1; then ok "$3";
    else fail "$3"; cat "$TMP/diff.txt"; fi
}

# --- Session 1: open via startup arg, edit, save back, quit ---
printf 'line one\nline two\nline three\n' > "$TMP/in.txt"
{
    printf '%s\n' "list" "insert 2 inserted line" "delete 1" \
        "print 9" "print xx" "save" "quit"
} | python3 forge.py run examples/apps/moon-code.fg "$TMP/in.txt" > "$TMP/out1.txt"
[ $? -eq 0 ] && ok "session 1 exit 0" || fail "session 1 exit code"
check_grep "$TMP/out1.txt" "opened $TMP/in.txt" "session 1 opened"
check_grep "$TMP/out1.txt" "1 line one" "session 1 list"
check_grep "$TMP/out1.txt" "print: no line 9" "session 1 bad line number"
check_grep "$TMP/out1.txt" "print: no line -1" "session 1 non-numeric line"
check_grep "$TMP/out1.txt" "saved $TMP/in.txt" "session 1 saved"
check_grep "$TMP/out1.txt" "bye" "session 1 bye"
printf 'inserted line\nline two\nline three\n' > "$TMP/expected1.txt"
check_file "$TMP/in.txt" "$TMP/expected1.txt" "session 1 file content"

# --- Session 2: fresh buffer, save to a new file, EOF quits ---
{
    printf '%s\n' "append hello moon" "append second" "save $TMP/new.txt"
} | python3 forge.py run examples/apps/moon-code.fg > "$TMP/out2.txt"
[ $? -eq 0 ] && ok "session 2 exit 0 (EOF quit)" || fail "session 2 exit code"
check_grep "$TMP/out2.txt" "saved $TMP/new.txt" "session 2 saved"
check_grep "$TMP/out2.txt" "bye" "session 2 bye"
printf 'hello moon\nsecond\n' > "$TMP/expected2.txt"
check_file "$TMP/new.txt" "$TMP/expected2.txt" "session 2 file content"

if [ "$FAIL" -ne 0 ]; then
    echo "MOON-CODE TEST: FAILURES PRESENT"
    exit 1
fi
echo "MOON-CODE TEST: ALL PASSED"
