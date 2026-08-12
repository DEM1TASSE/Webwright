import asyncio, threading, http.server


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><form method=post action=/save>"
                         b"<input name=price value=32><button>Save</button></form></body></html>")

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html>You saved the product.</html>")

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
        await pg.goto(B + "/edit", wait_until="domcontentloaded")
        await pg.fill("input[name=price]", "27")
        await pg.click("button")
        await pg.wait_for_load_state("domcontentloaded")
        print("playwright done, url =", pg.url)
        await b.close()


asyncio.run(main())
