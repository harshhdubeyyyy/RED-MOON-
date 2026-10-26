"""End-to-end LSP smoke test: drives `forge.py lsp` over stdio with
framed JSON-RPC and asserts real behaviour (not just importability).

Covers: initialize capabilities, diagnostics for a good program
(empty) and a broken program (the did-you-mean diagnostic from
the checker), and completions containing the current keywords
and builtins (scope, break, http_listen, alloc_count).
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(ROOT, "forge.py")

GOOD = """fn worker(n: int) {
    println("worker done", n);
}

fn main() -> int {
    scope {
        spawn worker(1);
    }
    let mut i: int = 0;
    while i < 3 {
        i = i + 1;
        if i == 2 {
            break;
        }
    }
    return 0;
}
"""

BROKEN = """fn main() -> int {
    let count: int = 5;
    println(coutn);
    return 0;
}
"""


def send(proc, obj):
    body = json.dumps(obj).encode()
    proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    proc.stdin.flush()


def read_msg(proc):
    headers = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("LSP process closed the stream")
        line = line.decode().strip()
        if not line:
            break
        k, _, v = line.partition(":")
        headers[k.strip()] = v.strip()
    n = int(headers["Content-Length"])
    return json.loads(proc.stdout.read(n))


def wait_for(proc, pred, timeout_msgs=20):
    for _ in range(timeout_msgs):
        msg = read_msg(proc)
        if pred(msg):
            return msg
    raise RuntimeError("expected LSP message did not arrive")


def main():
    proc = subprocess.Popen([sys.executable, FORGE, "lsp"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            cwd=ROOT)
    try:
        send(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"capabilities": {}}})
        init = wait_for(proc, lambda m: m.get("id") == 1)
        caps = init["result"]["capabilities"]
        assert "completionProvider" in caps, f"no completionProvider in {caps}"
        send(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})

        uri = "file:///test.fg"
        send(proc, {"jsonrpc": "2.0", "method": "textDocument/didOpen",
                    "params": {"textDocument": {"uri": uri, "languageId": "forge",
                                                "version": 1, "text": GOOD}}})
        diag = wait_for(proc, lambda m: m.get("method") == "textDocument/publishDiagnostics")
        assert diag["params"]["diagnostics"] == [], \
            f"good program produced diagnostics: {diag['params']['diagnostics']}"

        send(proc, {"jsonrpc": "2.0", "method": "textDocument/didChange",
                    "params": {"textDocument": {"uri": uri, "version": 2},
                               "contentChanges": [{"text": BROKEN}]}})
        diag = wait_for(proc, lambda m: m.get("method") == "textDocument/publishDiagnostics")
        diags = diag["params"]["diagnostics"]
        assert len(diags) == 1, f"expected 1 diagnostic, got {diags}"
        assert "Did you mean 'count'?" in diags[0]["message"], \
            f"diagnostic lacks the fix hint: {diags[0]['message']}"

        send(proc, {"jsonrpc": "2.0", "id": 2, "method": "textDocument/completion",
                    "params": {"textDocument": {"uri": uri},
                               "position": {"line": 0, "character": 0}}})
        comp = wait_for(proc, lambda m: m.get("id") == 2)
        labels = {item["label"] for item in comp["result"]["items"]}
        for want in ("scope", "break", "http_listen", "alloc_count",
                     "parallel_dot", "read_bytes"):
            assert want in labels, f"completion missing {want!r}"

        send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown", "params": None})
        wait_for(proc, lambda m: m.get("id") == 3)
        send(proc, {"jsonrpc": "2.0", "method": "exit"})
        rc = proc.wait(timeout=10)
        assert rc == 0, f"LSP exited with {rc}"
    finally:
        if proc.poll() is None:
            proc.kill()
    print("PASS: LSP smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
