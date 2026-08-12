"""Regression test: urllib3 v2 overrides HTTPConnection.request/getresponse, so
the http.client patch never fires for `requests`. Four WebArena runs recorded
nothing at all because of this.
"""
import threading, http.server


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302); self.send_header("Location", "/"); self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{srv.server_port}"

try:
    import requests
except ImportError:
    raise SystemExit("requests not installed in this interpreter - skipping")

r = requests.post(B + "/wishlist/index/add/", data={"product": "85498"},
                  allow_redirects=False)
print("requests POST ->", r.status_code)

import urllib.request
print("urllib GET ->", urllib.request.urlopen(B + "/x").status)
print("expect 2 records: one source=urllib3 (POST, post_data=product=85498), "
      "one source=http.client (GET)")
