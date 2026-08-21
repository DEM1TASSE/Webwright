#!/usr/bin/env python3.11
"""Download WebArena map-backend data from S3 with parallel range requests.

Chunks are written straight into a preallocated file at their offset, so there
is no cat-merge pass (which cost an extra full read+write on the image tars).
Per-chunk progress is checkpointed, so an interrupted run resumes where it left
off rather than restarting the file.
"""
import json
import os
import sys
import threading
import time
import urllib.request

BASE = "https://webarena-map-server-data.s3.amazonaws.com"
DIR = "/data/webarena/map"
LOG = "/data/webarena/dl_map.log"
FILES = [
    ("osm_dump.tar", 4),
    ("osrm_routing.tar", 12),
    ("osm_tile_server.tar", 12),
    ("nominatim_volumes.tar", 16),
]
CHUNK = 8 << 20  # 8 MiB per write


def log(msg):
    line = f"[{time.strftime('%F %T')}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def head_size(key):
    req = urllib.request.Request(f"{BASE}/{key}", method="HEAD")
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Length"])


def worker(key, path, start, end, idx, state, lock):
    """Fetch [start, end] inclusive, resuming from state[idx] bytes already done."""
    while True:
        done = state.get(str(idx), 0)
        if start + done > end:
            return
        req = urllib.request.Request(
            f"{BASE}/{key}", headers={"Range": f"bytes={start + done}-{end}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r, open(path, "r+b") as fh:
                fh.seek(start + done)
                while True:
                    buf = r.read(CHUNK)
                    if not buf:
                        break
                    fh.write(buf)
                    done += len(buf)
                    with lock:
                        state[str(idx)] = done
            if start + done > end:
                return
        except Exception as exc:  # transient S3/network failure -> retry the rest
            log(f"  chunk {idx} of {key} failed at {done} bytes ({exc}); retrying in 10s")
            time.sleep(10)


def fetch(key, nchunks):
    path = os.path.join(DIR, key)
    size = head_size(key)
    if os.path.exists(path) and os.path.getsize(path) == size:
        statef = os.path.join(DIR, f".{key}.state")
        if not os.path.exists(statef):
            log(f"SKIP {key} (complete, {size} bytes)")
            return
    log(f"START {key} ({size/1024**3:.1f} GB, {nchunks} chunks)")

    if not os.path.exists(path) or os.path.getsize(path) != size:
        with open(path, "wb") as fh:
            fh.truncate(size)

    statef = os.path.join(DIR, f".{key}.state")
    state = json.load(open(statef)) if os.path.exists(statef) else {}
    lock = threading.Lock()

    span = -(-size // nchunks)
    threads = []
    for i in range(nchunks):
        s = i * span
        e = min(s + span - 1, size - 1)
        if s > e:
            continue
        t = threading.Thread(target=worker, args=(key, path, s, e, i, state, lock))
        t.start()
        threads.append(t)

    last = time.time()
    while any(t.is_alive() for t in threads):
        time.sleep(15)
        with lock:
            got = sum(state.values())
            json.dump(state, open(statef, "w"))
        if time.time() - last >= 60:
            log(f"  {key}: {got/1024**3:.1f}/{size/1024**3:.1f} GB")
            last = time.time()
    for t in threads:
        t.join()

    got = os.path.getsize(path)
    if got == size:
        os.remove(statef) if os.path.exists(statef) else None
        log(f"DONE {key} ({got} bytes)")
    else:
        log(f"SIZE MISMATCH {key}: got {got} want {size}")


if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    for key, n in FILES:
        fetch(key, n)
    log("MAP DOWNLOADS FINISHED")
