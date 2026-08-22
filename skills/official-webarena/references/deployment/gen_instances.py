#!/usr/bin/env python3.11
"""Generate /data/webarena/instances.json -- the single source of truth for
every WebArena endpoint on this host.

Ports follow base + 100*k per instance. The map stack deliberately sits outside
that grid and is shared by all instances (its data is read-only, and all 128
map tasks are read-only too). Tile lives on 6080 rather than the upstream 8080
because 7780+300 collides with it, which broke instance 3.

Regenerate after adding or removing an instance:  python3.11 gen_instances.py
"""
import json
import subprocess

HOST = "GCRSANDBOX410.redmond.corp.microsoft.com"
IP = "10.209.224.120"
# Port on the Azure VM (GCRAZGDL1704) differs only for the map frontend,
# whose 3000 is already taken there by an unrelated python process.
VM_MAP_FRONTEND_PORT = 13000

BASE = {
    "homepage": (4399, ""),
    "shopping": (7770, ""),
    "shopping_admin": (7780, "/admin"),
    "reddit": (9999, ""),
    "gitlab": (8023, "/explore"),
    "wikipedia": (8888, ""),
}


def running_instances():
    """Instance numbers with a live shopping container (0 = the base set)."""
    out = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
    ).stdout.split()
    found = set()
    for name in out:
        if name == "shopping":
            found.add(0)
        elif name.startswith("shopping_") and name.split("_")[-1].isdigit():
            found.add(int(name.split("_")[-1]))
    return sorted(found)


def main():
    ks = running_instances()
    doc = {
        "host": HOST,
        "ip": IP,
        "note": "map is a single shared deployment; every instance points at the same map URLs",
        "instances": {},
        "map": {
            "frontend": f"http://{HOST}:3000",
            "tile": f"http://{HOST}:6080/tile/{{z}}/{{x}}/{{y}}.png",
            "nominatim": f"http://{HOST}:8085",
            "osrm_car": f"http://{HOST}:5000",
            "osrm_bike": f"http://{HOST}:5001",
            "osrm_foot": f"http://{HOST}:5002",
        },
        "tunnel": {
            "target": "GCRAZGDL1704 (72.154.168.97)",
            "note": (
                "reverse tunnel initiated from this host; the VM needs "
                f"'127.0.0.1 {HOST.lower()}' in /etc/hosts. Ports match except "
                f"the map frontend, which is {VM_MAP_FRONTEND_PORT} there."
            ),
            "map_frontend_port": VM_MAP_FRONTEND_PORT,
        },
    }

    for k in ks:
        off = k * 100
        inst = {
            name: f"http://{HOST}:{port + off}{path}"
            for name, (port, path) in BASE.items()
        }
        inst["map"] = doc["map"]["frontend"]
        doc["instances"][str(k)] = inst

    with open("/data/webarena/instances.json", "w") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"wrote /data/webarena/instances.json with instances {ks}")


if __name__ == "__main__":
    main()
