import sys, threading, http.server, urllib.request, urllib.parse

print("sitecustomize loaded:", "sitecustomize" in sys.modules)


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.end_headers(); self.wfile.write(b"posted")

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{srv.server_port}"

print("GET :", urllib.request.urlopen(B + "/hello", timeout=5).status)
req = urllib.request.Request(
    B + "/wishlist/index/add/",
    data=urllib.parse.urlencode({"product": "71337"}).encode(), method="POST")
print("POST:", urllib.request.urlopen(req, timeout=5).status)

try:
    import requests
    print("requests:", requests.get(B + "/via-requests", timeout=5).status_code)
except ImportError:
    print("requests: not installed")
