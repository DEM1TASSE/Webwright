# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --origin ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['origin', 'waypoint', 'destination']
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

#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_GEOCODER_BASE = "http://18.208.187.221:8085"
DEFAULT_FOOT_OSRM_BASE = "http://18.208.187.221:5002"
DEFAULT_CAR_OSRM_BASE = "http://18.208.187.221:5000"


def workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


def read_taskspec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def http_get_json(url: str, timeout: int = 60) -> dict | list:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def hhmmss_from_seconds(seconds: float) -> str:
    total = round(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def geocode_query(query: str, geocoder_base: str) -> tuple[str, dict]:
    url = f"{geocoder_base.rstrip('/')}/search?format=json&limit=5&q={urllib.parse.quote(query)}"
    data = http_get_json(url)
    if not data:
        raise RuntimeError(f"No geocoding results for query: {query}")
    top = data[0]
    required = ["lat", "lon", "display_name"]
    for key in required:
        if key not in top:
            raise RuntimeError(f"Geocode result missing {key} for query: {query}")
    return url, top


def route_duration_seconds(
    origin_point: dict,
    destination_point: dict,
    osrm_base: str,
) -> tuple[str, float, float]:
    url = (
        f"{osrm_base.rstrip('/')}/route/v1/driving/"
        f"{origin_point['lon']},{origin_point['lat']};"
        f"{destination_point['lon']},{destination_point['lat']}"
        f"?overview=false&steps=true"
    )
    data = http_get_json(url)
    if data.get("code") != "Ok":
        raise RuntimeError(f"Routing failed for {url}: {data}")
    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError(f"No routes returned for {url}")
    route = routes[0]
    duration = route.get("duration")
    distance = route.get("distance")
    if duration is None or distance is None:
        raise RuntimeError(f"Route missing duration/distance for {url}: {route}")
    return url, float(duration), float(distance)


def compute_walk_then_drive_total(
    origin: str,
    waypoint: str,
    destination: str,
    geocoder_base: str,
    foot_osrm_base: str,
    car_osrm_base: str,
    log_path: Path,
) -> str:
    append_log(log_path, f"Origin query: {origin}")
    origin_url, origin_point = geocode_query(origin, geocoder_base)
    append_log(log_path, f"Origin geocode url: {origin_url}")
    append_log(log_path, f"Origin matched: {origin_point['display_name']} ({origin_point['lat']}, {origin_point['lon']})")

    append_log(log_path, f"Waypoint query: {waypoint}")
    waypoint_url, waypoint_point = geocode_query(waypoint, geocoder_base)
    append_log(log_path, f"Waypoint geocode url: {waypoint_url}")
    append_log(log_path, f"Waypoint matched: {waypoint_point['display_name']} ({waypoint_point['lat']}, {waypoint_point['lon']})")

    append_log(log_path, f"Destination query: {destination}")
    destination_url, destination_point = geocode_query(destination, geocoder_base)
    append_log(log_path, f"Destination geocode url: {destination_url}")
    append_log(log_path, f"Destination matched: {destination_point['display_name']} ({destination_point['lat']}, {destination_point['lon']})")

    foot_url, foot_seconds, foot_distance = route_duration_seconds(origin_point, waypoint_point, foot_osrm_base)
    append_log(log_path, f"Walk route url: {foot_url}")
    append_log(log_path, f"Walk duration seconds: {foot_seconds}")
    append_log(log_path, f"Walk distance meters: {foot_distance}")

    car_url, car_seconds, car_distance = route_duration_seconds(waypoint_point, destination_point, car_osrm_base)
    append_log(log_path, f"Drive route url: {car_url}")
    append_log(log_path, f"Drive duration seconds: {car_seconds}")
    append_log(log_path, f"Drive distance meters: {car_distance}")

    total_seconds = foot_seconds + car_seconds
    total_hms = hhmmss_from_seconds(total_seconds)
    append_log(log_path, f"Total duration seconds: {total_seconds}")
    append_log(log_path, f"Total duration HH:MM:SS: {total_hms}")
    return total_hms


def validate_output_schema(taskspec: dict, retrieved_data) -> None:
    schema = taskspec.get("output_schema")
    if schema != {"type": "array", "items": {"type": "string"}}:
        raise RuntimeError(f"Unsupported or unexpected output schema: {schema}")
    if not isinstance(retrieved_data, list) or not all(isinstance(x, str) for x in retrieved_data):
        raise RuntimeError("retrieved_data does not match required schema")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: skill.py /path/to/taskspec.json")

    ws = workspace_dir()
    log_path = ws / "logs.txt"
    response_path = ws / "agent_response.json"

    taskspec = read_taskspec(sys.argv[1])
    params = taskspec.get("params", {})

    origin = params["origin"]
    waypoint = params["waypoint"]
    destination = params["destination"]

    geocoder_base = params.get("geocoder_base", DEFAULT_GEOCODER_BASE)
    foot_osrm_base = params.get("foot_osrm_base", DEFAULT_FOOT_OSRM_BASE)
    car_osrm_base = params.get("car_osrm_base", DEFAULT_CAR_OSRM_BASE)

    try:
        total_hms = compute_walk_then_drive_total(
            origin=origin,
            waypoint=waypoint,
            destination=destination,
            geocoder_base=geocoder_base,
            foot_osrm_base=foot_osrm_base,
            car_osrm_base=car_osrm_base,
            log_path=log_path,
        )
        retrieved_data = [total_hms]
        validate_output_schema(taskspec, retrieved_data)
        response = {
            "task_type": "RETRIEVE",
            "status": "SUCCESS",
            "retrieved_data": retrieved_data,
            "error_details": None,
        }
    except Exception as e:
        append_log(log_path, f"ERROR: {e}")
        response = {
            "task_type": "RETRIEVE",
            "status": "ERROR",
            "retrieved_data": [],
            "error_details": str(e),
        }

    write_json(response_path, response)


if __name__ == "__main__":
    main()
