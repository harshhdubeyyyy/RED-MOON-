#!/bin/bash
# moon-browser-test.sh — standalone test for examples/apps/moon-browser.fg.
# Serves a small HTML page from a LOCAL python http server only (no
# internet), runs the app for real, and verifies real outputs
# (grep, not echo-only checks). Exits non-zero on any failure.
set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$DIR/../.." && pwd)"
FORGE="$REPO/forge.py"
APP="$DIR/moon-browser.fg"
PORT=8139
FAIL=0
fail() { echo "FAIL: $1"; FAIL=1; }

WORK="$(mktemp -d)"
WWW="$WORK/www"
mkdir -p "$WWW"
cat > "$WWW/test.html" <<'HTML'
<html><head><title>Moon Test</title></head>
<body><h1>Hello Moon</h1><p>This is a <b>brave</b> test page.</p></body></html>
HTML

cd "$WWW" || exit 1
python3 -m http.server "$PORT" >"$WORK/server.log" 2>&1 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null; rm -rf "$WORK"' EXIT

READY=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -s -o /dev/null "http://127.0.0.1:$PORT/test.html"; then
        READY=1
        break
    fi
    sleep 1
done
[ "$READY" -eq 1 ] || { echo "FAIL: local test server did not start"; cat "$WORK/server.log"; exit 1; }

echo "== moon-browser: local page =="
OUT="$(python3 "$FORGE" run "$APP" "http://127.0.0.1:$PORT/test.html" 2>"$WORK/err.txt")"
CODE=$?
echo "$OUT"
[ "$CODE" -eq 0 ] || fail "expected exit 0, got $CODE"
echo "$OUT" | grep -q "Hello Moon" || fail "stripped text missing 'Hello Moon'"
echo "$OUT" | grep -q "brave test page" || fail "stripped text missing 'brave test page'"
echo "$OUT" | grep -q "<h1>\|<b>\|<html>" && fail "HTML tags were not stripped"

echo "== moon-browser: bad scheme =="
OUT2="$(python3 "$FORGE" run "$APP" "example.com" 2>&1)"
CODE2=$?
[ "$CODE2" -eq 1 ] || fail "bad-scheme expected exit 1, got $CODE2"
echo "$OUT2" | grep -q "must start with http://" || fail "bad-scheme error message missing"

echo "== moon-browser: no args =="
OUT3="$(python3 "$FORGE" run "$APP" 2>&1)"
CODE3=$?
[ "$CODE3" -eq 1 ] || fail "no-args expected exit 1, got $CODE3"
echo "$OUT3" | grep -q "usage:" || fail "no-args usage message missing"

echo "== moon-browser: refused connection =="
OUT4="$(python3 "$FORGE" run "$APP" "http://127.0.0.1:59999/nope.html" 2>&1)"
CODE4=$?
[ "$CODE4" -eq 1 ] || fail "refused-connection expected exit 1, got $CODE4"
echo "$OUT4" | grep -q "http_get: cannot connect" || fail "refused-connection error line missing"

if [ "$FAIL" -eq 0 ]; then
    echo "moon-browser-test: ALL PASS"
    exit 0
else
    echo "moon-browser-test: FAILURES PRESENT"
    exit 1
fi
