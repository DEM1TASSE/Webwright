# --- CLI entry shim (auto-added by skill_factory; do not edit) -------------------------------
# Lets this skill run two ways with IDENTICAL results:
#   python skill.py taskspec.json                       (what replay/programs use)
#   python skill.py --location1 ...   (convenience for humans)
def _skillfactory_cli():
    import sys, json, argparse, tempfile
    _PARAMS = ['location1', 'location2', 'retrieved_data_format_spec']
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
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path


NOMINATIM_URL = "http://18.208.187.221:8085/search"
OSRM_ROUTE_BASE = "http://18.208.187.221:5000/route/v1/driving/"
DEFAULT_TIMEOUT = 30


def get_workspace_dir() -> Path:
    return Path(os.environ.get("WORKSPACE_DIR", os.getcwd())).resolve()


def ensure_workspace(workspace: Path):
    workspace.mkdir(parents=True, exist_ok=True)
    screenshots = workspace / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    log_path = workspace / "skill_log.txt"
    if not log_path.exists():
        log_path.write_text("", encoding="utf-8")
    return screenshots, log_path


def log(log_path: Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")


def save_artifact(path: Path, title: str, data_lines) -> None:
    lines = [title, ""]
    for item in data_lines:
        if isinstance(item, (dict, list)):
            lines.append(json.dumps(item, indent=2, ensure_ascii=False))
        else:
            lines.append(str(item))
    path.write_text("\n".join(lines), encoding="utf-8")


def write_agent_response(workspace: Path, status: str, retrieved_data, error_details) -> None:
    payload = {
        "task_type": "RETRIEVE",
        "status": status,
        "retrieved_data": retrieved_data,
        "error_details": error_details,
    }
    (workspace / "agent_response.json").write_text(json.dumps(payload), encoding="utf-8")


def load_taskspec(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def extract_locations(taskspec):
    params = taskspec.get("params", {}) or {}
    origin = params.get("location1")
    destination = params.get("location2")
    if not origin or not destination:
        raise ValueError("taskspec.params.location1 and taskspec.params.location2 are required")
    return str(origin), str(destination)


def http_get_json(url: str, params=None, timeout: int = DEFAULT_TIMEOUT):
    if params:
        query = urllib.parse.urlencode(params, doseq=True)
        full_url = url + ("&" if "?" in url else "?") + query
    else:
        full_url = url
    req = urllib.request.Request(
        full_url,
        headers={
            "User-Agent": "Mozilla/5.0 skill-agent",
            "Accept": "application/json,*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body), full_url


def geocode_location(query: str, timeout: int = DEFAULT_TIMEOUT):
    data, full_url = http_get_json(
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "limit": 5},
        timeout=timeout,
    )
    if not isinstance(data, list) or not data:
        raise LookupError(f"No geocoding results found for query: {query}")
    top = data[0]
    if "lat" not in top or "lon" not in top:
        raise LookupError(f"Geocoding result missing coordinates for query: {query}")
    return top, data, full_url


def build_osrm_route_url(origin, destination):
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    return OSRM_ROUTE_BASE + coords


def route_driving_duration(origin, destination, timeout: int = DEFAULT_TIMEOUT):
    route_url = build_osrm_route_url(origin, destination)
    data, full_url = http_get_json(
        route_url,
        params={"overview": "false", "steps": "true", "geometries": "polyline"},
        timeout=timeout,
    )
    if data.get("code") != "Ok" or not data.get("routes"):
        raise LookupError(f"OSRM routing failed: {json.dumps(data)[:500]}")
    route = data["routes"][0]
    if "duration" not in route:
        raise LookupError("OSRM route missing duration")
    return float(route["duration"]), data, full_url


def format_hhmmss(seconds: float) -> str:
    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def validate_duration_string(value: str) -> None:
    parts = value.split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Duration must be a string in HH:MM:SS format")


def validate_output_schema(taskspec, retrieved_data) -> None:
    schema = taskspec.get("output_schema", {}) or {}
    if schema.get("type") != "array":
        raise ValueError("Unsupported output_schema: top-level type must be array")
    items = schema.get("items", {}) or {}
    if items.get("type") != "string" or items.get("format") != "duration":
        raise ValueError("Unsupported output_schema: items must be string format duration")
    if not isinstance(retrieved_data, list):
        raise ValueError("retrieved_data must be a list")
    for item in retrieved_data:
        if not isinstance(item, str):
            raise ValueError("retrieved_data items must be strings")
        validate_duration_string(item)


def retrieve_min_car_travel_time(taskspec, workspace: Path, screenshots: Path, log_path: Path):
    origin_query, destination_query = extract_locations(taskspec)
    log(log_path, f"Geocoding origin: {origin_query}")
    origin, origin_candidates, origin_url = geocode_location(origin_query)

    save_artifact(
        screenshots / "01_origin_geocode.txt",
        "Origin geocode evidence",
        [
            f"query={origin_query}",
            f"request_url={origin_url}",
            f"top_display_name={origin.get('display_name')}",
            f"top_lat={origin.get('lat')}",
            f"top_lon={origin.get('lon')}",
            {"candidates_preview": origin_candidates[:3]},
        ],
    )

    log(log_path, f"Geocoding destination: {destination_query}")
    destination, destination_candidates, destination_url = geocode_location(destination_query)

    save_artifact(
        screenshots / "02_destination_geocode.txt",
        "Destination geocode evidence",
        [
            f"query={destination_query}",
            f"request_url={destination_url}",
            f"top_display_name={destination.get('display_name')}",
            f"top_lat={destination.get('lat')}",
            f"top_lon={destination.get('lon')}",
            {"candidates_preview": destination_candidates[:3]},
        ],
    )

    log(log_path, "Requesting OSRM driving route")
    duration_seconds, route_json, route_request_url = route_driving_duration(origin, destination)
    duration_value = format_hhmmss(duration_seconds)

    save_artifact(
        screenshots / "03_route_result.txt",
        "OSRM route evidence",
        [
            f"request_url={route_request_url}",
            f"origin_display_name={origin.get('display_name')}",
            f"destination_display_name={destination.get('display_name')}",
            f"raw_duration_seconds={route_json['routes'][0].get('duration')}",
            f"distance_meters={route_json['routes'][0].get('distance')}",
            f"formatted_duration={duration_value}",
            {
                "route_summary": {
                    "code": route_json.get("code"),
                    "duration": route_json["routes"][0].get("duration"),
                    "distance": route_json["routes"][0].get("distance"),
                }
            },
        ],
    )

    retrieved_data = [duration_value]
    validate_output_schema(taskspec, retrieved_data)

    save_artifact(
        screenshots / "04_final_output.txt",
        "Final output evidence",
        [
            {"retrieved_data": retrieved_data},
        ],
    )
    return retrieved_data


def main():
    workspace = get_workspace_dir()
    screenshots, log_path = ensure_workspace(workspace)

    if len(sys.argv) < 2:
        write_agent_response(workspace, "ERROR", None, "Missing taskspec.json path argument")
        return

    try:
        taskspec = load_taskspec(sys.argv[1])
        retrieved_data = retrieve_min_car_travel_time(taskspec, workspace, screenshots, log_path)
        write_agent_response(workspace, "SUCCESS", retrieved_data, None)
    except LookupError as e:
        log(log_path, f"NOT_FOUND_ERROR: {e}")
        write_agent_response(workspace, "NOT_FOUND_ERROR", None, str(e))
    except urllib.error.HTTPError as e:
        msg = f"HTTP error {e.code}: {e.reason}"
        log(log_path, msg)
        write_agent_response(workspace, "ERROR", None, msg)
    except urllib.error.URLError as e:
        msg = f"URL error: {e.reason}"
        log(log_path, msg)
        write_agent_response(workspace, "ERROR", None, msg)
    except Exception as e:
        log(log_path, f"ERROR: {e}")
        write_agent_response(workspace, "ERROR", None, str(e))


if __name__ == "__main__":
    main()
