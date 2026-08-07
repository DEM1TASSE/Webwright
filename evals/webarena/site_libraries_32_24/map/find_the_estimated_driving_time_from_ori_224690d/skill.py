# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --origin ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['origin', 'destination']
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
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


WORKSPACE = get_workspace_dir()
WORKSPACE.mkdir(parents=True, exist_ok=True)

LOG_PATH = WORKSPACE / "skill.log"
RESPONSE_PATH = WORKSPACE / "agent_response.json"
ARTIFACTS_DIR = WORKSPACE / "artifacts"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_taskspec(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def http_get_json(
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> Any:
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def geocode_place(
    query: str,
    *,
    user_agent: str,
    limit: int = 5,
    countrycodes: Optional[str] = None,
    viewbox: Optional[str] = None,
    bounded: Optional[int] = None,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "q": query,
        "format": "jsonv2",
        "limit": limit,
    }
    if countrycodes:
        params["countrycodes"] = countrycodes
    if viewbox:
        params["viewbox"] = viewbox
    if bounded is not None:
        params["bounded"] = bounded

    results = http_get_json(
        "https://nominatim.openstreetmap.org/search",
        params=params,
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    if not results:
        raise ValueError(f"No geocoding results for query: {query}")
    return results[0]


def request_driving_route(
    origin_lon: str,
    origin_lat: str,
    dest_lon: str,
    dest_lat: str,
    *,
    user_agent: str,
) -> Dict[str, Any]:
    url = (
        f"https://router.project-osrm.org/route/v1/driving/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
    )
    route = http_get_json(
        url,
        params={"overview": "false"},
        headers={"User-Agent": user_agent},
        timeout=30,
    )
    if route.get("code") != "Ok":
        raise ValueError(f"OSRM route request failed: {route}")
    routes = route.get("routes") or []
    if not routes:
        raise ValueError("OSRM returned no routes")
    return route


def seconds_to_hhmmss(total_seconds: float) -> str:
    secs = int(round(total_seconds))
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def estimate_driving_time(
    origin: str,
    destination: str,
    *,
    geocode_origin_query: Optional[str] = None,
    geocode_destination_query: Optional[str] = None,
    user_agent: str = "Mozilla/5.0 web-skill-driving-time",
    countrycodes: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    origin_query = geocode_origin_query or origin
    destination_query = geocode_destination_query or destination

    log(f"Geocoding origin query: {origin_query}")
    origin_result = geocode_place(
        origin_query,
        user_agent=user_agent,
        countrycodes=countrycodes,
    )
    write_json(ARTIFACTS_DIR / "origin_geocode.json", origin_result)

    log(f"Geocoding destination query: {destination_query}")
    destination_result = geocode_place(
        destination_query,
        user_agent=user_agent,
        countrycodes=countrycodes,
    )
    write_json(ARTIFACTS_DIR / "destination_geocode.json", destination_result)

    log(
        "Requesting driving route between "
        f"origin=({origin_result['lat']}, {origin_result['lon']}) and "
        f"destination=({destination_result['lat']}, {destination_result['lon']})"
    )
    route = request_driving_route(
        origin_result["lon"],
        origin_result["lat"],
        destination_result["lon"],
        destination_result["lat"],
        user_agent=user_agent,
    )
    write_json(ARTIFACTS_DIR / "route_response.json", route)

    duration_seconds = route["routes"][0]["duration"]
    duration_str = seconds_to_hhmmss(duration_seconds)
    log(f"Computed driving duration: {duration_seconds} seconds -> {duration_str}")

    debug_payload = {
        "origin_input": origin,
        "destination_input": destination,
        "origin_query_used": origin_query,
        "destination_query_used": destination_query,
        "origin_match": origin_result,
        "destination_match": destination_result,
        "duration_seconds": duration_seconds,
        "duration_hhmmss": duration_str,
    }
    write_json(ARTIFACTS_DIR / "debug_summary.json", debug_payload)
    return duration_str, debug_payload


def validate_output_schema(output: Any, schema: Dict[str, Any]) -> None:
    if schema.get("type") != "array":
        raise ValueError("Only array output_schema is supported by this skill")
    if not isinstance(output, list):
        raise ValueError("retrieved_data must be a list")
    item_schema = schema.get("items", {})
    if item_schema.get("type") == "string":
        if not all(isinstance(x, str) for x in output):
            raise ValueError("retrieved_data items must all be strings")


def build_success_response(retrieved_data: List[str]) -> Dict[str, Any]:
    return {
        "task_type": "RETRIEVE",
        "status": "SUCCESS",
        "retrieved_data": retrieved_data,
        "error_details": None,
    }


def build_error_response(message: str) -> Dict[str, Any]:
    return {
        "task_type": "RETRIEVE",
        "status": "ERROR",
        "retrieved_data": [],
        "error_details": message,
    }


def run_task(taskspec: Dict[str, Any]) -> Dict[str, Any]:
    params = taskspec.get("params", {}) or {}
    output_schema = taskspec.get("output_schema", {})

    origin = params.get("origin")
    destination = params.get("destination")
    if not origin or not destination:
        raise ValueError("taskspec.params must include non-empty 'origin' and 'destination'")

    geocode_origin_query = params.get("geocode_origin_query")
    geocode_destination_query = params.get("geocode_destination_query")
    countrycodes = params.get("countrycodes")

    duration_str, _debug = estimate_driving_time(
        origin=origin,
        destination=destination,
        geocode_origin_query=geocode_origin_query,
        geocode_destination_query=geocode_destination_query,
        countrycodes=countrycodes,
    )

    retrieved_data = [duration_str]
    validate_output_schema(retrieved_data, output_schema)
    return build_success_response(retrieved_data)


def main() -> None:
    LOG_PATH.write_text("", encoding="utf-8")
    try:
        if len(sys.argv) < 2:
            raise ValueError("Expected taskspec.json path as sys.argv[1]")

        taskspec = load_taskspec(sys.argv[1])
        write_json(ARTIFACTS_DIR / "taskspec.json", taskspec)

        response = run_task(taskspec)
        write_json(RESPONSE_PATH, response)
        log(f"Wrote successful response to {RESPONSE_PATH}")
    except Exception as e:
        log(f"ERROR: {e}")
        response = build_error_response(str(e))
        write_json(RESPONSE_PATH, response)


if __name__ == "__main__":
    main()
