"""Reproduce the blind spot: page.request.post() must now be recorded."""
import asyncio, threading, http.server


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
        self.wfile.write(b"<html><a class=towishlist>add</a></html>")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(302); self.send_header("Location", "/"); self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
B = f"http://127.0.0.1:{srv.server_port}"


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        b = await p.chromium.launch()
        c = await b.new_context()
        pg = await c.new_page()
        await pg.goto(B + "/product", wait_until="domcontentloaded")
        # this is exactly what the agent did
        r = await pg.request.post(B + "/wishlist/index/add/",
                                  form={"product": "22787", "form_key": "abc"})
        print("page.request.post ->", r.status)
        await b.close()


asyncio.run(main())
