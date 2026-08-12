# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --hotel ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['hotel', 'place', 'retrieved_data_format_spec']
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
import os
import re
import ssl
import shutil
import urllib.parse
import urllib.request
import http.cookiejar
from pathlib import Path
from datetime import datetime
import sys


WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
TASKSPEC_PATH = Path(sys.argv[1])


# -----------------------------
# Files / logging
# -----------------------------

def load_taskspec(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_run_dir(workspace: Path) -> tuple[Path, Path, Path]:
    final_runs = workspace / "final_runs"
    final_runs.mkdir(parents=True, exist_ok=True)
    nums = []
    for p in final_runs.glob("run_*"):
        try:
            nums.append(int(p.name.split("_")[1]))
        except Exception:
            pass
    run_dir = final_runs / f"run_{max(nums, default=0) + 1:03d}"
    screenshots = run_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    log_path = run_dir / "final_script_log.txt"
    log_path.write_text("", encoding="utf-8")
    return run_dir, screenshots, log_path


RUN_DIR, SCREENSHOTS_DIR, LOG_PATH = ensure_run_dir(WORKSPACE)


def log(msg: str) -> None:
    line = f"[{datetime.utcnow().isoformat()}Z] {msg}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_text_artifact(name: str, content: str) -> None:
    (SCREENSHOTS_DIR / name).write_text(content, encoding="utf-8")


def copy_self_if_possible() -> None:
    try:
        src = Path(__file__)
        if src.exists():
            shutil.copy2(src, RUN_DIR / "final_script.py")
    except Exception as e:
        log(f"Non-fatal: could not copy script artifact: {e!r}")


def write_agent_response(status: str, retrieved_data, error_details):
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    text = json.dumps(payload, indent=2)
    (WORKSPACE / "agent_response.json").write_text(text, encoding="utf-8")
    (RUN_DIR / "agent_response.json").write_text(text, encoding="utf-8")


# -----------------------------
# HTTP helpers
# -----------------------------

def make_ssl_context():
    ctx = ssl.create_default_context()
    try:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    except Exception:
        pass
    return ctx


SSL_CTX = make_ssl_context()
DEFAULT_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "*/*"}


def http_get_text(url: str, headers: dict | None = None, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return resp.read().decode("utf-8", "ignore")


def http_get_json(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as resp:
        return json.load(resp)


def http_post_form_text(opener, url: str, data: dict, headers: dict | None = None, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        headers={**DEFAULT_HEADERS, **(headers or {})},
        method="POST",
    )
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


# -----------------------------
# Formatting / validation
# -----------------------------

def format_duration_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def validate_output_schema(taskspec: dict, retrieved_data) -> None:
    schema = taskspec.get("output_schema", {})
    if schema.get("type") != "array":
        raise ValueError("Only array output_schema=array is supported")
    if not isinstance(retrieved_data, list):
        raise ValueError("retrieved_data must be a list")
    item_schema = schema.get("items", {})
    if item_schema.get("type") != "string":
        raise ValueError("retrieved_data items must be strings")
    duration_re = re.compile(r"^\d{2}:\d{2}:\d{2}$")
    for item in retrieved_data:
        if not isinstance(item, str) or not duration_re.match(item):
            raise ValueError(f"Invalid duration item: {item!r}")


# -----------------------------
# Query generation primitives
# -----------------------------

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def build_query_variants(label: str, kind: str, taskspec: dict) -> list[str]:
    params = taskspec.get("params", {})
    city_hint = normalize_space(params.get("city_hint", ""))
    country_hint = normalize_space(params.get("country_hint", ""))

    if kind == "origin":
        base = normalize_space(params.get("origin_query") or label)
    else:
        base = normalize_space(params.get("destination_query") or label)

    variants = []

    def add(q: str):
        q = normalize_space(q)
        if q and q not in variants:
            variants.append(q)

    add(base)

    if city_hint:
        add(f"{base} {city_hint}")
    if city_hint and country_hint:
        add(f"{base} {city_hint} {country_hint}")
    if country_hint:
        add(f"{base} {country_hint}")

    lower = base.lower()

    # Template-specific robustness learned from successful instances:
    # hotel/place names are often colloquial. Add soft expansions but keep them generic.
    if kind == "origin":
        if "hotel" not in lower and "inn" in lower:
            if city_hint:
                add(f"{base} hotel {city_hint}")
            add(f"{base} hotel")
        if city_hint:
            add(f"{base} near the airport {city_hint}") if "airport" in lower and city_hint not in lower else None
            add(f"{base} {city_hint}")
    else:
        # "science museum" commonly maps to named science centers; add city-qualified version.
        if city_hint and city_hint.lower() not in lower:
            add(f"{base} {city_hint}")

    return variants


# -----------------------------
# Geocoding primitives
# -----------------------------

def geocode_via_site_search(base_url: str, query: str) -> dict:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    search_path = "/search?query=" + urllib.parse.quote(query)
    search_url = base_url.rstrip("/") + search_path

    req = urllib.request.Request(
        search_url,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html,*/*"},
    )
    with opener.open(req, timeout=30) as r:
        html = r.read().decode("utf-8", "ignore")

    csrf_param_m = re.search(r'<meta name="csrf-param" content="([^"]+)"', html)
    csrf_token_m = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    href_m = re.search(r'data-href="([^"]+)"', html)
    if not (csrf_param_m and csrf_token_m and href_m):
        raise RuntimeError("Could not parse site search shell metadata")

    csrf_param = csrf_param_m.group(1)
    csrf_token = csrf_token_m.group(1)
    geocoder_path = href_m.group(1)
    geocoder_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", geocoder_path.lstrip("/"))

    # Use a broad bbox; previous narrow/global choices can fail depending on app behavior.
    result_html = http_post_form_text(
        opener,
        geocoder_url,
        {
            csrf_param: csrf_token,
            "zoom": "17",
            "minlon": "-180",
            "minlat": "-90",
            "maxlon": "180",
            "maxlat": "90",
        },
        headers={
            "Accept": "text/html, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": search_url,
            "Origin": base_url.rstrip("/"),
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
    )

    # Parse all candidate rows, not just one.
    candidates = []
    pattern = re.compile(
        r'data-lat="([^"]+)"[^>]*data-lon="([^"]+)"[\s\S]*?data-name="([^"]+)"[\s\S]*?href="([^"]+)"',
        re.I,
    )
    for m in pattern.finditer(result_html):
        lat, lon, name, href_obj = m.groups()
        try:
            candidates.append(
                {
                    "name": name,
                    "lat": float(lat),
                    "lon": float(lon),
                    "href": href_obj,
                }
            )
        except Exception:
            pass

    if not candidates:
        raise RuntimeError(f"No site geocoder candidates parsed for query={query!r}")

    chosen = candidates[0]
    return {
        "provider": "site_search",
        "query": query,
        "name": chosen["name"],
        "lat": chosen["lat"],
        "lon": chosen["lon"],
        "raw": {
            "search_html_excerpt": html[:5000],
            "result_html_excerpt": result_html[:5000],
            "candidate_count": len(candidates),
            "candidates": candidates[:5],
        },
        "request_url": search_url,
        "geocoder_url": geocoder_url,
        "result_count": len(candidates),
    }


def geocode_via_nominatim_like(base_url: str, query: str, limit: int = 10) -> dict:
    sep = "&" if "?" in base_url else "?"
    url = f"{base_url}{sep}format=jsonv2&limit={limit}&q={urllib.parse.quote(query)}" if "q=" not in base_url else f"{base_url}{urllib.parse.quote(query)}"
    data = http_get_json(url, headers={"Accept": "application/json"})
    if not isinstance(data, list) or not data:
        raise RuntimeError(f"No geocoding results for query={query!r} via Nominatim-like service")
    first = data[0]
    return {
        "provider": "nominatim_like",
        "query": query,
        "name": first.get("display_name") or first.get("name") or query,
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
        "raw": first,
        "request_url": url,
        "result_count": len(data),
    }


def geocode_via_photon(base_url: str, query: str, limit: int = 10) -> dict:
    url = f"{base_url.rstrip('/')}/?q={urllib.parse.quote(query)}&limit={limit}"
    data = http_get_json(url, headers={"Accept": "application/json"})
    features = data.get("features", [])
    if not features:
        raise RuntimeError(f"No geocoding results for query={query!r} via Photon")
    feat = features[0]
    coords = feat["geometry"]["coordinates"]
    props = feat.get("properties", {})
    name = (
        props.get("name")
        or props.get("housename")
        or props.get("street")
        or props.get("city")
        or query
    )
    return {
        "provider": "photon",
        "query": query,
        "name": name,
        "lat": float(coords[1]),
        "lon": float(coords[0]),
        "raw": feat,
        "request_url": url,
        "result_count": len(features),
    }


def geocode_with_method(method: str, query: str, taskspec: dict) -> dict:
    params = taskspec.get("params", {})
    start_url = taskspec.get("start_url") or params.get("site_base_url")
    geocoder_base = params.get("geocoder_base_url")

    if method == "site_search":
        if not start_url:
            raise RuntimeError("site_search requires start_url")
        return geocode_via_site_search(start_url, query)

    if method == "nominatim_like":
        base = geocoder_base or "http://18.208.187.221:8085/search"
        return geocode_via_nominatim_like(base, query)

    if method == "photon":
        base = geocoder_base or "https://photon.komoot.io/api"
        return geocode_via_photon(base, query)

    raise ValueError(f"Unsupported geocoding method {method!r}")


def geocode_place(label: str, kind: str, taskspec: dict) -> dict:
    params = taskspec.get("params", {})

    preferred = params.get("geocoder", "auto")
    if preferred == "auto":
        # Prefer the site search first when available, then the task's configured service,
        # then public Photon as fallback.
        method_order = []
        if taskspec.get("start_url") or params.get("site_base_url"):
            method_order.append("site_search")
        if params.get("geocoder_type") in ("nominatim_like", "photon"):
            method_order.append(params["geocoder_type"])
        method_order.extend(["nominatim_like", "photon"])
    else:
        method_order = [preferred]

    dedup_methods = []
    for m in method_order:
        if m not in dedup_methods:
            dedup_methods.append(m)

    query_variants = build_query_variants(label, kind, taskspec)
    errors = []

    for query in query_variants:
        for method in dedup_methods:
            try:
                result = geocode_with_method(method, query, taskspec)
                log(f"Geocoded {kind} via {method}: query={query!r} -> {result['name']} ({result['lat']}, {result['lon']})")
                result["effective_query"] = query
                result["effective_method"] = method
                return result
            except Exception as e:
                errors.append(f"{method}({query!r}): {e!r}")

    raise RuntimeError(f"All geocoding attempts failed for {kind}={label!r}. Details: {' | '.join(errors)}")


# -----------------------------
# Routing primitives
# -----------------------------

def route_duration_osrm(origin: dict, destination: dict, taskspec: dict) -> dict:
    params = taskspec.get("params", {})
    osrm_base = params.get("osrm_base_url", "https://router.project-osrm.org/route/v1/driving")
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    url = osrm_base.rstrip("/") + "/" + coords + "?overview=false"
    data = http_get_json(url, headers={"Accept": "application/json"})
    routes = data.get("routes", [])
    if not routes:
        raise RuntimeError("OSRM response contained no routes")
    route0 = routes[0]
    seconds = float(route0["duration"])
    return {
        "request_url": url,
        "duration_seconds": seconds,
        "duration_hhmmss": format_duration_hhmmss(seconds),
        "distance_meters": route0.get("distance"),
        "raw": data,
    }


# -----------------------------
# Thin task layer
# -----------------------------

def retrieve_driving_duration(taskspec: dict) -> list[str]:
    params = taskspec.get("params", {})
    hotel = params["hotel"]
    place = params["place"]

    log(f"Hotel label: {hotel}")
    log(f"Destination label: {place}")

    origin = geocode_place(hotel, "origin", taskspec)
    destination = geocode_place(place, "destination", taskspec)

    save_text_artifact(
        "final_execution_1_origin_geocode.txt",
        json.dumps(
            {
                "hotel": hotel,
                "query_variants": build_query_variants(hotel, "origin", taskspec),
                "selected_origin": {
                    "provider": origin["provider"],
                    "method": origin.get("effective_method"),
                    "query": origin.get("effective_query"),
                    "name": origin["name"],
                    "lat": origin["lat"],
                    "lon": origin["lon"],
                    "request_url": origin.get("request_url"),
                    "result_count": origin.get("result_count"),
                },
            },
            indent=2,
        ),
    )

    save_text_artifact(
        "final_execution_2_destination_geocode.txt",
        json.dumps(
            {
                "place": place,
                "query_variants": build_query_variants(place, "destination", taskspec),
                "selected_destination": {
                    "provider": destination["provider"],
                    "method": destination.get("effective_method"),
                    "query": destination.get("effective_query"),
                    "name": destination["name"],
                    "lat": destination["lat"],
                    "lon": destination["lon"],
                    "request_url": destination.get("request_url"),
                    "result_count": destination.get("result_count"),
                },
            },
            indent=2,
        ),
    )

    route = route_duration_osrm(origin, destination, taskspec)

    save_text_artifact(
        "final_execution_3_osrm_route.txt",
        json.dumps(
            {
                "osrm_url": route["request_url"],
                "origin": {
                    "name": origin["name"],
                    "lat": origin["lat"],
                    "lon": origin["lon"],
                },
                "destination": {
                    "name": destination["name"],
                    "lat": destination["lat"],
                    "lon": destination["lon"],
                },
                "duration_seconds": route["duration_seconds"],
                "distance_meters": route["distance_meters"],
                "duration_hhmmss": route["duration_hhmmss"],
            },
            indent=2,
        ),
    )

    result = [route["duration_hhmmss"]]
    validate_output_schema(taskspec, result)
    return result


def main():
    copy_self_if_possible()
    taskspec = load_taskspec(TASKSPEC_PATH)
    try:
        retrieved_data = retrieve_driving_duration(taskspec)
        write_agent_response("SUCCESS", retrieved_data, None)
        log(f"SUCCESS: retrieved_data={retrieved_data}")
    except Exception as e:
        log(f"ERROR: {e!r}")
        write_agent_response("NOT_FOUND_ERROR", None, str(e))


if __name__ == "__main__":
    main()
