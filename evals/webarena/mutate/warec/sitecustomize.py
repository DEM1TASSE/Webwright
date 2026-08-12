"""Auto-imported by every Python subprocess Webwright spawns (via PYTHONPATH).

Records every HTTP request the agent makes, whether it uses raw urllib/requests
or drives Playwright. Writes HAR-shaped JSONL to $WA_REC_DIR.

Enable:  export WA_REC_DIR=/path/to/rec   PYTHONPATH=/path/to/warec:$PYTHONPATH
Disable: unset WA_REC_DIR  (module then does nothing)
"""
import os

_DIR = os.environ.get("WA_REC_DIR")

if _DIR:
    import json
    import time
    import threading
    from pathlib import Path

    _OUT = Path(_DIR) / f"http_{os.getpid()}.jsonl"
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _LOCK = threading.Lock()

    # Only record the site under test. Without this the model gateway's traffic
    # lands in the HAR too -- that is most of the volume, and its request bodies
    # are full prompts carrying an API key header.
    _HOSTS = tuple(h.strip() for h in os.environ.get("WA_REC_HOSTS", "").split(",") if h.strip())

    def _wanted(url):
        if not _HOSTS:
            return True
        try:
            netloc = str(url).split("//", 1)[-1].split("/", 1)[0]
        except Exception:
            return True
        host = netloc.split("@")[-1]
        return any(host == h or host.split(":")[0] == h.split(":")[0] for h in _HOSTS)

    def _emit(rec):
        if not _wanted(rec.get("url", "")):
            return
        rec["ts"] = time.time()
        rec["pid"] = os.getpid()
        rec["cwd"] = os.getcwd()
        try:
            with _LOCK, _OUT.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass  # recording must never break the run

    # ---- 1. raw HTTP: covers urllib, requests, and anything on http.client ----
    try:
        import http.client as _hc

        _orig_request = _hc.HTTPConnection.request
        _orig_getresponse = _hc.HTTPConnection.getresponse

        def _request(self, method, url, body=None, headers=None, **kw):
            try:
                scheme = "https" if self.port == 443 or _hc.HTTPSConnection in type(self).__mro__ else "http"
                full = url if url.startswith("http") else f"{scheme}://{self.host}:{self.port}{url}"
                if isinstance(body, bytes):
                    try:
                        body_s = body.decode("utf-8", "replace")
                    except Exception:
                        body_s = f"<{len(body)} bytes>"
                elif body is None or isinstance(body, str):
                    body_s = body
                else:
                    body_s = "<stream>"
                self._wa_pending = {
                    "source": "http.client", "method": method, "url": full,
                    "post_data": body_s if method not in ("GET", "HEAD") else None,
                    "req_headers": dict(headers or {}),
                }
            except Exception:
                self._wa_pending = None
            return _orig_request(self, method, url, body, headers, **kw)

        def _getresponse(self, *a, **kw):
            resp = _orig_getresponse(self, *a, **kw)
            pending = getattr(self, "_wa_pending", None)
            if pending:
                pending["status"] = getattr(resp, "status", None)
                pending["resp_headers"] = dict(getattr(resp, "headers", {}) or {})
                _emit(pending)
                self._wa_pending = None
            return resp

        _hc.HTTPConnection.request = _request
        _hc.HTTPConnection.getresponse = _getresponse
    except Exception:
        pass

    # ---- 1b. urllib3 / requests -------------------------------------------
    # urllib3 v2 overrides HTTPConnection.request AND getresponse, so the
    # http.client patch above never fires for `requests`. One hook on the pool
    # covers requests, urllib3 direct, and anything else built on it.
    def _patch_urllib3(mod):
        cls = getattr(getattr(mod, "connectionpool", None), "HTTPConnectionPool", None)
        if cls is None or getattr(cls.urlopen, "_wa_patched", False):
            return
        orig = cls.urlopen

        def urlopen(self, method, url, body=None, headers=None, **kw):
            resp = orig(self, method, url, body=body, headers=headers, **kw)
            try:
                full = url if str(url).startswith("http") else f"{self.scheme}://{self.host}:{self.port}{url}"
                if isinstance(body, (bytes, bytearray)):
                    body_s = body.decode("utf-8", "replace")
                elif body is None or isinstance(body, str):
                    body_s = body
                else:
                    body_s = "<stream>"
                _emit({"source": "urllib3", "method": method, "url": full,
                       "post_data": body_s if method not in ("GET", "HEAD") else None,
                       "req_headers": dict(headers or {}),
                       "status": getattr(resp, "status", None),
                       "resp_headers": dict(getattr(resp, "headers", {}) or {})})
            except Exception:
                pass
            return resp

        urlopen._wa_patched = True
        try:
            cls.urlopen = urlopen
        except Exception:
            pass

    # ---- 1c. httpx --------------------------------------------------------
    def _patch_httpx(mod):
        for cls_name in ("Client", "AsyncClient"):
            cls = getattr(mod, cls_name, None)
            if cls is None or getattr(getattr(cls, "send", None), "_wa_patched", False):
                continue
            orig = cls.send
            is_async = cls_name.startswith("Async")

            def make(orig=orig, is_async=is_async):
                def record(request, resp):
                    body = None
                    try:
                        raw = request.read() if hasattr(request, "read") else None
                        body = raw.decode("utf-8", "replace") if raw else None
                    except Exception:
                        pass
                    _emit({"source": "httpx", "method": request.method,
                           "url": str(request.url), "post_data": body,
                           "req_headers": dict(request.headers or {}),
                           "status": getattr(resp, "status_code", None),
                           "resp_headers": dict(getattr(resp, "headers", {}) or {})})

                if is_async:
                    async def wrapper(self, request, **kw):
                        resp = await orig(self, request, **kw)
                        try:
                            record(request, resp)
                        except Exception:
                            pass
                        return resp
                else:
                    def wrapper(self, request, **kw):
                        resp = orig(self, request, **kw)
                        try:
                            record(request, resp)
                        except Exception:
                            pass
                        return resp
                wrapper._wa_patched = True
                return wrapper

            try:
                cls.send = make()
            except Exception:
                pass

    # ---- 2. Playwright: attach listeners to every context that gets created ----
    def _wire_context(ctx, is_async):
        # request.headers omits what the browser adds (accept, sec-fetch-*), and
        # WebArena decides whether an event counts as a *navigation* from exactly
        # those. all_headers() is the complete set; it is awaitable on the async
        # API, so the handler has to be a coroutine there.
        def record(resp, req_headers, resp_headers):
            _emit({"source": "playwright", "method": resp.request.method, "url": resp.url,
                   "post_data": resp.request.post_data,
                   "req_headers": req_headers, "status": resp.status,
                   "resp_headers": resp_headers})

        async def on_response_async(resp):
            try:
                try:
                    rh = dict(await resp.request.all_headers())
                except Exception:
                    rh = dict(resp.request.headers or {})
                try:
                    sh = dict(await resp.all_headers())
                except Exception:
                    sh = dict(resp.headers or {})
                record(resp, rh, sh)
            except Exception:
                pass

        def on_response_sync(resp):
            try:
                try:
                    rh = dict(resp.request.all_headers())
                except Exception:
                    rh = dict(resp.request.headers or {})
                try:
                    sh = dict(resp.all_headers())
                except Exception:
                    sh = dict(resp.headers or {})
                record(resp, rh, sh)
            except Exception:
                pass

        try:
            ctx.on("response", on_response_async if is_async else on_response_sync)
        except Exception:
            pass

    def _patch_api_request(mod, is_async):
        """page.request / context.request bypass context 'response' events entirely.

        Agents reach for these to replay a site's own form payloads
        (e.g. Magento data-post), so without this the write is invisible.
        """
        cls = getattr(mod, "APIRequestContext", None)
        if cls is None:
            return
        for meth in ("fetch", "get", "post", "put", "patch", "delete", "head"):
            orig = getattr(cls, meth, None)
            if orig is None or getattr(orig, "_wa_patched", False):
                continue

            def make(orig=orig, meth=meth):
                def record(url, resp, kw):
                    body = kw.get("data") or kw.get("form") or kw.get("multipart")
                    if isinstance(body, dict):
                        body = "&".join(f"{k}={v}" for k, v in body.items())
                    elif isinstance(body, (bytes, bytearray)):
                        body = body.decode("utf-8", "replace")
                    _emit({"source": "pw.api", "method": meth.upper(),
                           "url": str(url), "post_data": body if body else None,
                           "req_headers": dict(kw.get("headers") or {}),
                           "status": getattr(resp, "status", None), "resp_headers": {}})

                if is_async:
                    async def wrapper(self, url, **kw):
                        resp = await orig(self, url, **kw)
                        try:
                            record(url, resp, kw)
                        except Exception:
                            pass
                        return resp
                else:
                    def wrapper(self, url, **kw):
                        resp = orig(self, url, **kw)
                        try:
                            record(url, resp, kw)
                        except Exception:
                            pass
                        return resp
                wrapper._wa_patched = True
                return wrapper

            try:
                setattr(cls, meth, make())
            except Exception:
                pass

    def _patch_playwright():
        for mod_name in ("playwright.sync_api", "playwright.async_api"):
            try:
                mod = __import__(mod_name, fromlist=["*"])
            except Exception:
                continue
            is_async = mod_name.endswith("async_api")
            _patch_api_request(mod, is_async)
            for cls_name, meth in (("Browser", "new_context"),
                                   ("BrowserType", "launch_persistent_context")):
                cls = getattr(mod, cls_name, None)
                if cls is None or not hasattr(cls, meth):
                    continue
                orig = getattr(cls, meth)
                if getattr(orig, "_wa_patched", False):
                    continue
                if is_async:
                    async def wrapper(self, *a, _orig=orig, **kw):
                        ctx = await _orig(self, *a, **kw)
                        _wire_context(ctx, True)
                        return ctx
                else:
                    def wrapper(self, *a, _orig=orig, **kw):
                        ctx = _orig(self, *a, **kw)
                        _wire_context(ctx, False)
                        return ctx
                wrapper._wa_patched = True
                try:
                    setattr(cls, meth, wrapper)
                except Exception:
                    pass

    # playwright is usually imported after us -> patch on first import.
    # _busy guards against re-entry: _patch_playwright imports playwright itself.
    _busy = [False]

    try:
        import builtins
        _orig_import = builtins.__import__

        def _apply(name):
            import sys as _sys
            if name.startswith("playwright"):
                _patch_playwright()
            elif name.split(".")[0] in ("urllib3", "requests"):
                m = _sys.modules.get("urllib3")
                if m is not None:
                    try:                       # connectionpool may be lazy
                        _orig_import("urllib3.connectionpool")
                    except Exception:
                        pass
                    _patch_urllib3(m)
            elif name.split(".")[0] == "httpx":
                m = _sys.modules.get("httpx")
                if m is not None:
                    _patch_httpx(m)

        def _import(name, *a, **kw):
            mod = _orig_import(name, *a, **kw)
            if not _busy[0]:
                _busy[0] = True
                try:
                    _apply(name)
                except Exception:
                    pass
                finally:
                    _busy[0] = False
            return mod

        builtins.__import__ = _import
        for _already in ("urllib3", "httpx"):   # imported before us?
            try:
                _apply(_already)
            except Exception:
                pass
    except Exception:
        pass
