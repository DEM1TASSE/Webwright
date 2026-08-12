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

    def _emit(rec):
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

    # ---- 2. Playwright: attach listeners to every context that gets created ----
    def _wire_context(ctx, is_async):
        def on_request_finished(req):
            try:
                _emit({"source": "playwright", "method": req.method, "url": req.url,
                       "post_data": req.post_data, "req_headers": dict(req.headers or {}),
                       "status": None, "resp_headers": {}})
            except Exception:
                pass

        def on_response(resp):
            try:
                _emit({"source": "playwright", "method": resp.request.method, "url": resp.url,
                       "post_data": resp.request.post_data,
                       "req_headers": dict(resp.request.headers or {}),
                       "status": resp.status, "resp_headers": dict(resp.headers or {})})
            except Exception:
                pass

        try:
            ctx.on("response", on_response)
        except Exception:
            try:
                ctx.on("requestfinished", on_request_finished)
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

        def _import(name, *a, **kw):
            mod = _orig_import(name, *a, **kw)
            if name.startswith("playwright") and not _busy[0]:
                _busy[0] = True
                try:
                    _patch_playwright()
                except Exception:
                    pass
                finally:
                    _busy[0] = False
            return mod

        builtins.__import__ = _import
    except Exception:
        pass
