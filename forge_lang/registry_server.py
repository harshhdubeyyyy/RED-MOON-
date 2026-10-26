"""Forge hosted registry server (simple HTTP, no auth).

Run:  python3 forge.py pkg serve --dir DIR --port 8765
  or: python3 -m forge_lang.registry_server --dir DIR --port 8765

Endpoints (all JSON unless noted):
  GET  /api/packages                        -> {"packages": [{name, versions}]}
  GET  /api/packages/<name>                 -> {"versions": [...]}
  GET  /api/packages/<name>/<version>       -> {"name":..., "version":..., "files": [...]}
  GET  /api/packages/<name>/<version>/<file> -> raw .fg text
  POST /api/publish  {"name":..., "version":..., "files": {name: text}}
       -> {"ok": true, "name":..., "version":...}

This is a local HTTP registry, not a public hosted service and
not authenticated: run it on your own machine or trusted network,
like a private Go module proxy. Clients are `forge pkg
publish-remote` and `forge pkg add-remote` in pkg.py.
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse


def safe_name(s):
    return re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", s) is not None


def make_handler(root):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            if parts == ["api", "packages"]:
                pkgs = []
                if os.path.isdir(root):
                    for name in sorted(os.listdir(root)):
                        base = os.path.join(root, name)
                        if os.path.isdir(base):
                            pkgs.append({"name": name,
                                         "versions": sorted(os.listdir(base))})
                self._json({"packages": pkgs})
                return
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "packages":
                name = parts[2]
                if not safe_name(name):
                    self._json({"error": "bad name"}, 400)
                    return
                if len(parts) == 3:
                    base = os.path.join(root, name)
                    versions = sorted(os.listdir(base)) if os.path.isdir(base) else []
                    self._json({"name": name, "versions": versions})
                    return
                version = parts[3]
                if not safe_name(version):
                    self._json({"error": "bad version"}, 400)
                    return
                pkg_dir = os.path.join(root, name, version)
                if len(parts) == 4:
                    if not os.path.isdir(pkg_dir):
                        self._json({"error": "not found"}, 404)
                        return
                    files = sorted(f for f in os.listdir(os.path.join(pkg_dir, "src"))
                                   if f.endswith(".fg")) if os.path.isdir(os.path.join(pkg_dir, "src")) else []
                    self._json({"name": name, "version": version, "files": files})
                    return
                fname = parts[4]
                if not safe_name(fname) or not fname.endswith(".fg"):
                    self._json({"error": "bad file"}, 400)
                    return
                path = os.path.join(pkg_dir, "src", fname)
                if not os.path.isfile(path):
                    self._json({"error": "not found"}, 404)
                    return
                with open(path, encoding="utf-8") as f:
                    body = f.read().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/publish":
                self._json({"error": "not found"}, 404)
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length).decode())
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            name, version, files = data.get("name"), data.get("version"), data.get("files")
            if not name or not safe_name(name) or not version or not safe_name(version) \
                    or not isinstance(files, dict) or not files:
                self._json({"error": "bad publish body"}, 400)
                return
            dest = os.path.join(root, name, version, "src")
            os.makedirs(dest, exist_ok=True)
            for fname, text in files.items():
                if not safe_name(fname) or not fname.endswith(".fg"):
                    continue
                with open(os.path.join(dest, fname), "w", encoding="utf-8") as f:
                    f.write(text)
            self._json({"ok": True, "name": name, "version": version})

    return Handler


def serve(root, port):
    os.makedirs(root, exist_ok=True)
    server = HTTPServer(("0.0.0.0", port), make_handler(root))
    print(f"forge registry serving {root} on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=os.path.expanduser("~/.forge_registry_server"))
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    serve(args.dir, args.port)
