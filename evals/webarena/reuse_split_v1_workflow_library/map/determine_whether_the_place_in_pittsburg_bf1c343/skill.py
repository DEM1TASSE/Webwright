# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --place ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['place', 'location', 'retrieved_data_format_spec']
    argv = sys.argv[1:]
    # A single positional, non-flag argument is a taskspec.json path -> original behaviour,
    # sys.argv left untouched. This is the path replay uses, so it must not change.
    if len(argv) == 1 and not argv[0].startswith("-"):
        return
    ap = argparse.ArgumentParser(
        prog="skill.py",
        description="Run this skill directly. Pass --flags, or a taskspec.json path.")
    for _p in _PARAMS:
        ap.add_argument("--" + _p.replace("_", "-"), dest=_p, default=None)
    ap.add_argument("taskspec", nargs="?", help="path to a taskspec.json (instead of --flags)")
    a = ap.parse_args(argv)
    # A taskspec path given alongside/without flags -> honour it, stay untouched.
    if a.taskspec and not any(getattr(a, _p) is not None for _p in _PARAMS):
        sys.argv = [sys.argv[0], a.taskspec]
        return
    params = {_p: getattr(a, _p) for _p in _PARAMS if getattr(a, _p) is not None}
    if not params:
        ap.print_help()
        ex = " ".join("--" + _p.replace("_", "-") + " <" + _p + ">" for _p in _PARAMS)
        print("\n  example:  python skill.py " + ex)
        print("  or:       python skill.py taskspec.json  "
              '(taskspec = {"params": {' + ", ".join('"' + _p + '": ...' for _p in _PARAMS)
              + "}})")
        raise SystemExit(0)
    spec = {"params": params}
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(spec, f)
    f.close()
    sys.argv = [sys.argv[0], f.name]
_skillfactory_cli()
# --- end CLI entry shim ---------------------------------------------------------------------

import json
import math
import os
import shutil
import ssl
import struct
import sys
import urllib.parse
import urllib.request
import zlib
from pathlib import Path


SITE_GEOCODER_BASE = "http://18.208.187.221:8085/"
GEOCODER_BASES = [
    SITE_GEOCODER_BASE,
    "https://nominatim.openstreetmap.org/",
    "https://geocode.maps.co/",
]

ROUTE_BASES = [
    "http://18.208.187.221:5000",
    "https://routing.openstreetmap.de/routed-car",
    "https://router.project-osrm.org",
]


def workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", Path.cwd())).resolve()


def next_run_dir(root: Path) -> Path:
    final_runs = root / "final_runs"
    final_runs.mkdir(parents=True, exist_ok=True)
    ids = []
    for p in final_runs.glob("run_*"):
        try:
            ids.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_id = max(ids, default=0) + 1
    run_dir = final_runs / f"run_{run_id:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def png_chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_placeholder_png(path: Path, bands):
    width, height = 1280, 1800
    colors = [
        (255, 255, 255),
        (235, 243, 255),
        (240, 255, 240),
        (255, 245, 235),
        (245, 245, 245),
        (255, 235, 245),
    ]
    rows = []
    band_h = max(1, height // max(1, len(bands) if bands else 1))
    for y in range(height):
        idx = min(len(bands) - 1, y // band_h) if bands else 0
        r, g, b = colors[idx % len(colors)]
        rows.append(bytes([0]) + bytes([r, g, b]) * width)
    raw = b"".join(rows)
    ihdr = struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IDAT", zlib.compress(raw, 9)) + png_chunk(b"IEND", b"")
    path.write_bytes(png)


def save_evidence(path: Path, lines):
    try:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (1280, 1800), "white")
        draw = ImageDraw.Draw(img)
        y = 30
        for line in lines:
            text = str(line)
            chunks = [text[i:i + 110] for i in range(0, len(text), 110)] or [""]
            for chunk in chunks:
                draw.text((30, y), chunk, fill="black")
                y += 24
            y += 8
        img.save(path)
    except Exception:
        try:
            write_placeholder_png(path, lines)
        except Exception:
            path.write_text("\n".join(map(str, lines)), encoding="utf-8")


class SkillContext:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.run_dir = next_run_dir(workdir)
        self.screenshot_dir = self.run_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.run_dir / "final_script_log.txt"
        self.log_path.write_text("", encoding="utf-8")

    def log(self, msg: str):
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
        print(msg)

    def snap(self, name: str, lines):
        save_evidence(self.screenshot_dir / name, lines)


def copy_self(run_dir: Path):
    try:
        src = Path(__file__)
        if src.exists():
            shutil.copy2(src, run_dir / "final_script.py")
    except Exception:
        pass


def http_get_json(url: str, timeout: int = 40):
    headers = {
        "User-Agent": "Mozilla/5.0 skill-osrm-reachability",
        "Accept": "application/json,text/plain,*/*",
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def tokenize(text: str):
    cleaned = text.lower().replace(",", " ").replace("-", " ").replace("/", " ")
    return [t for t in cleaned.split() if t]


def unique_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def build_origin_queries(location: str):
    loc = location.strip()
    lower = loc.lower()
    queries = [loc]
    if "pittsburgh" not in lower:
        queries += [
            f"{loc}, Pittsburgh",
            f"{loc}, Pittsburgh, PA",
        ]
    if "cmu" in lower or "carnegie mellon" in lower:
        queries += [
            f"{loc}, Carnegie Mellon University, Pittsburgh",
            f"{loc}, CMU, Pittsburgh",
        ]
    if "gates" in lower:
        queries += [
            "Gates-Hillman, Pittsburgh",
            "Gates Hillman Center Carnegie Mellon University Pittsburgh",
            "Gates Building at CMU Pittsburgh",
        ]
    return unique_preserve_order(queries)


def build_destination_queries(place: str):
    p = place.strip()
    lower = p.lower()
    queries = [
        f"{p}, Pittsburgh",
        f"{p}, Pittsburgh, PA",
        f"{p} Pittsburgh",
    ]
    if "walmart" in lower:
        queries += [
            "Walmart, Pittsburgh",
            "Walmart Pittsburgh PA",
        ]
    if "amc" in lower:
        queries += [
            "AMC theatre Pittsburgh PA",
            "AMC Waterfront 22 West Homestead PA",
            "AMC Loews Waterfront 22 West Homestead PA",
            "AMC South Hills Village Pittsburgh PA",
        ]
    if "police" in lower:
        queries += [
            "police station Pittsburgh PA",
            f"{p} Pittsburgh PA",
            "Carnegie Mellon Police Station Pittsburgh",
        ]
    return unique_preserve_order(queries)


def search_geocode(base: str, query: str, limit: int = 10):
    base_clean = base.rstrip("/")
    if "maps.co" in base_clean:
        url = base_clean + "/search?q=" + urllib.parse.quote(query)
    else:
        url = base_clean + "/search?" + urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": limit})
    data = http_get_json(url)
    if isinstance(data, list):
        return data, url
    return [], url


def candidate_text(item):
    return " ".join(str(item.get(k, "")) for k in ["display_name", "name", "type", "class"]).lower()


def choose_origin_candidate(candidates, location: str):
    loc_tokens = [t for t in tokenize(location) if t not in {"at", "the", "building"}]
    scored = []
    for item in candidates:
        text = candidate_text(item)
        score = 0
        for tok in loc_tokens:
            if tok in text:
                score += 5
        if "pittsburgh" in text or "allegheny county" in text:
            score += 3
        if any(t in text for t in ["carnegie mellon", "cmu"]) and any(t in " ".join(loc_tokens) for t in ["cmu", "carnegie", "mellon", "gates"]):
            score += 4
        if "gates" in " ".join(loc_tokens) and "gates" in text:
            score += 8
        if "hobart" in " ".join(loc_tokens) and "india" in text:
            score -= 10
        if item.get("lat") and item.get("lon"):
            score += 1
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return (scored[0][1] if scored else None), scored


def choose_destination_candidate(candidates, place: str, origin=None):
    place_lower = place.lower()
    place_tokens = [t for t in tokenize(place) if t not in {"the", "a", "an", "in", "of", "at"}]
    scored = []
    for item in candidates:
        text = candidate_text(item)
        score = 0

        for tok in place_tokens:
            if tok in text:
                score += 4

        if "pittsburgh" in text or "allegheny county" in text or "west homestead" in text:
            score += 2

        if item.get("lat") and item.get("lon"):
            score += 1

        if "walmart" in place_lower:
            if "walmart" in text:
                score += 8

        if "amc" in place_lower:
            if "amc" in text:
                score += 8
            if "waterfront" in text or "west homestead" in text:
                score += 5
            if "hotel" in text:
                score -= 8

        if "police" in place_lower:
            if "police" in text:
                score += 8
            if "carnegie mellon" in text or "cmu" in text:
                score += 12

        if origin is not None and item.get("lat") and item.get("lon"):
            try:
                dist = haversine_km(origin["lat"], origin["lon"], float(item["lat"]), float(item["lon"]))
                if "walmart" in place_lower:
                    score += max(0.0, 20.0 - min(dist, 20.0))
                elif "amc" in place_lower:
                    score += max(0.0, 18.0 - min(dist, 18.0))
                elif "police" in place_lower:
                    score += max(0.0, 25.0 - min(dist, 25.0))
                else:
                    score += max(0.0, 15.0 - min(dist, 15.0))
            except Exception:
                pass

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return (scored[0][1] if scored else None), scored


def geocode_with_fallback(ctx: SkillContext, label: str, queries, chooser):
    all_candidates = []
    used_urls = []
    for q in queries:
        for base in GEOCODER_BASES:
            try:
                results, url = search_geocode(base, q, limit=10)
                used_urls.append(url)
                all_candidates.extend(results)
                ctx.log(f"{label}: geocode success query={q!r} url={url} results={len(results)}")
            except Exception as e:
                ctx.log(f"{label}: geocode failure query={q!r} base={base} error={e}")
    chosen, scored = chooser(all_candidates)
    if not chosen:
        raise RuntimeError(f"Unable to geocode {label}")
    return chosen, scored, used_urls, all_candidates


def route_with_fallback(ctx: SkillContext, origin, destination):
    olon, olat = origin["lon"], origin["lat"]
    dlon, dlat = destination["lon"], destination["lat"]
    tried = []
    last = None
    for base in ROUTE_BASES:
        url = (
            base.rstrip("/")
            + f"/route/v1/driving/{olon},{olat};{dlon},{dlat}?"
            + urllib.parse.urlencode({"overview": "false", "steps": "true", "alternatives": "false"})
        )
        tried.append(url)
        try:
            data = http_get_json(url)
            if data.get("code") == "Ok" and data.get("routes"):
                return data, url, tried
            last = data
            ctx.log(f"Routing non-Ok via {url}: {json.dumps(data)[:300]}")
        except Exception as e:
            last = e
            ctx.log(f"Routing failure via {url}: {e}")
    raise RuntimeError(f"Unable to retrieve route; last={last}")


def validate_output_schema(taskspec, retrieved_data):
    schema = taskspec.get("output_schema", {})
    if schema.get("type") != "array":
        raise RuntimeError("Unsupported output_schema: expected top-level array")
    if not isinstance(retrieved_data, list):
        raise RuntimeError("retrieved_data must be a list")
    item_schema = schema.get("items", {})
    if item_schema.get("type") == "boolean":
        if len(retrieved_data) != 1 or not isinstance(retrieved_data[0], bool):
            raise RuntimeError("retrieved_data must be exactly one boolean")
    return True


def write_agent_response(workdir: Path, status: str, retrieved_data, error_details):
    response = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (workdir / "agent_response.json").write_text(json.dumps(response), encoding="utf-8")
    return response


def solve_reachability(ctx: SkillContext, place: str, location: str):
    origin_queries = build_origin_queries(location)
    origin, origin_scored, origin_urls, _ = geocode_with_fallback(
        ctx,
        "origin",
        origin_queries,
        chooser=lambda candidates: choose_origin_candidate(candidates, location),
    )
    origin_anchor = {"lat": float(origin["lat"]), "lon": float(origin["lon"])}

    ctx.snap(
        "final_execution_2_origin_geocoded.png",
        [
            f"Origin queries: {json.dumps(origin_queries)}",
            f"Chosen origin: {origin.get('display_name')}",
            f"Origin lat/lon: {origin.get('lat')}, {origin.get('lon')}",
            "Top origin candidates:",
        ] + [
            f"score={round(score, 2)} | {item.get('display_name', '')}"
            for score, item in origin_scored[:8]
        ] + [
            f"Used geocoder URLs: {json.dumps(origin_urls[:15])}",
        ],
    )

    destination_queries = build_destination_queries(place)
    destination, destination_scored, destination_urls, _ = geocode_with_fallback(
        ctx,
        "destination",
        destination_queries,
        chooser=lambda candidates: choose_destination_candidate(candidates, place, origin_anchor),
    )

    ctx.snap(
        "final_execution_3_destination_geocoded.png",
        [
            f"Destination queries: {json.dumps(destination_queries)}",
            f"Chosen destination: {destination.get('display_name')}",
            f"Destination lat/lon: {destination.get('lat')}, {destination.get('lon')}",
            "Top destination candidates:",
        ] + [
            f"score={round(score, 2)} | {item.get('display_name', '')}"
            for score, item in destination_scored[:8]
        ] + [
            f"Used geocoder URLs: {json.dumps(destination_urls[:15])}",
        ],
    )

    route_data, route_url, route_tried = route_with_fallback(ctx, origin, destination)
    route0 = route_data["routes"][0]
    duration_seconds = float(route0["duration"])
    distance_meters = float(route0["distance"])
    within_hour = bool(duration_seconds <= 3600)

    ctx.snap(
        "final_execution_4_route_result.png",
        [
            f"Chosen route URL: {route_url}",
            f"Tried route URLs: {json.dumps(route_tried)}",
            f"Origin: {origin.get('display_name')}",
            f"Destination: {destination.get('display_name')}",
            f"Duration seconds: {duration_seconds}",
            f"Duration minutes: {round(duration_seconds / 60.0, 2)}",
            f"Distance meters: {distance_meters}",
            f"Within one hour: {within_hour}",
        ],
    )

    return [within_hour], {
        "origin": origin,
        "destination": destination,
        "duration_seconds": duration_seconds,
        "distance_meters": distance_meters,
        "route_url": route_url,
    }


def main():
    workdir = workspace_dir()
    ctx = SkillContext(workdir)
    copy_self(ctx.run_dir)

    taskspec_path = sys.argv[1]
    with open(taskspec_path, "r", encoding="utf-8") as f:
        taskspec = json.load(f)

    params = taskspec.get("params", {})
    place = str(params.get("place", "")).strip()
    location = str(params.get("location", "")).strip()

    try:
        if not place or not location:
            raise RuntimeError("Missing required params: place and location")

        ctx.log("step 1 action: read task spec and prepare OSRM reachability workflow")
        ctx.snap(
            "final_execution_1_task_context.png",
            [
                f"start_url: {taskspec.get('start_url')}",
                f"place: {place}",
                f"location: {location}",
                f"output_schema: {json.dumps(taskspec.get('output_schema'))}",
            ],
        )

        ctx.log("step 2 action: geocode origin and destination with reusable fallback logic")
        retrieved_data, details = solve_reachability(ctx, place, location)

        ctx.log("step 3 action: validate one-item boolean output against requested schema")
        validate_output_schema(taskspec, retrieved_data)

        response = write_agent_response(workdir, "SUCCESS", retrieved_data, None)
        ctx.log("step 4 action: write final agent_response.json")
        ctx.log("Final response: " + json.dumps(response))
        ctx.snap(
            "final_execution_5_final_response.png",
            [
                json.dumps(response),
                f"Origin chosen: {details['origin'].get('display_name')}",
                f"Destination chosen: {details['destination'].get('display_name')}",
                f"Duration seconds: {details['duration_seconds']}",
            ],
        )
    except Exception as e:
        response = write_agent_response(workdir, "FAILURE", [], str(e))
        ctx.log("ERROR: " + str(e))
        ctx.log("Failure response: " + json.dumps(response))
        ctx.snap(
            "final_execution_error.png",
            [
                "Execution failed",
                str(e),
                json.dumps(response),
            ],
        )


if __name__ == "__main__":
    main()
