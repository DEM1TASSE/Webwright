#!/usr/bin/env python3
"""Decide whether a deployment is ready to be measured against, and whether a reset took.

A replay phase scores the scripts a batch left behind against a deployment that is supposed
to be back at its initial state. Both halves of that can fail quietly. A site that is still
coming up answers 500 or nothing, and every task that touches it fails for a reason that has
nothing to do with the script; Postmill's Postgres in particular replays its WAL for minutes
after the container starts, well past the fixed sleep the launch script waits. A reset that
did not take leaves the previous batch's writes in place, and the replay then scores against
a site that already contains what the script was supposed to create.

Neither shows up as an error. Both show up as a lower number.

The order these gates go in, and what else a batch needs around them, is in
references/lanes.md.

  --wait      block until every site in the deployment actually serves
  --snapshot  write a fingerprint of the counters that mutating tasks move
  --verify    take a fingerprint and diff it against a reference, non-zero on mismatch
"""
import argparse, json, subprocess, sys, time, urllib.error, urllib.request

# Counters chosen because mutating tasks move them: creating an issue, posting a comment,
# placing an order, changing a price. A pristine deployment reproduces them exactly, since
# the data lives in the image and a reset recreates the container from it.
QUERIES = {
    "shopping": ("mysql", "magentodb", [
        ("orders", "SELECT COUNT(*) FROM sales_order"),
        ("cart_items", "SELECT COUNT(*) FROM quote_item"),
        ("wishlist_items", "SELECT COUNT(*) FROM wishlist_item"),
        ("addresses", "SELECT COUNT(*) FROM customer_address_entity"),
        ("reviews", "SELECT COUNT(*) FROM review"),
    ]),
    "shopping_admin": ("mysql", "magentodb", [
        ("products", "SELECT COUNT(*) FROM catalog_product_entity"),
        ("price_sum", "SELECT ROUND(SUM(value),2) FROM catalog_product_entity_decimal WHERE "
                      "attribute_id=(SELECT attribute_id FROM eav_attribute WHERE "
                      "attribute_code='price' AND entity_type_id=4)"),
        ("cms_pages", "SELECT COUNT(*) FROM cms_page"),
        ("reviews", "SELECT COUNT(*) FROM review"),
        ("orders", "SELECT COUNT(*) FROM sales_order"),
    ]),
    "forum": ("psql", "postmill", [
        ("submissions", "SELECT COUNT(*) FROM submissions"),
        ("comments", "SELECT COUNT(*) FROM comments"),
        ("forums", "SELECT COUNT(*) FROM forums"),
        ("users", "SELECT COUNT(*) FROM users"),
    ]),
    "gitlab": ("gitlab-psql", None, [
        ("projects", "SELECT COUNT(*) FROM projects"),
        ("issues", "SELECT COUNT(*) FROM issues"),
        ("merge_requests", "SELECT COUNT(*) FROM merge_requests"),
        ("notes", "SELECT COUNT(*) FROM notes"),
        ("members", "SELECT COUNT(*) FROM members"),
    ]),
}


def container(site, instance):
    return site if instance == 0 else f"{site}_{instance}"


def query(site, instance, sql):
    kind, database, _ = QUERIES[site]
    name = container(site, instance)
    if kind == "mysql":
        cmd = ["docker", "exec", name, "mysql", "-u", "magentouser", "-pMyPassword",
               database, "-N", "-e", sql]
    elif kind == "psql":
        cmd = ["docker", "exec", name, "psql", "-U", "postgres", "-d", database,
               "-t", "-A", "-c", sql]
    else:
        cmd = ["docker", "exec", name, "gitlab-psql", "-t", "-A", "-c", sql]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if done.returncode != 0:
        return None
    text = done.stdout.strip().splitlines()
    return text[0].strip() if text else None


def fingerprint(instance):
    return {site: {label: query(site, instance, sql) for label, sql in columns}
            for site, (_, _, columns) in QUERIES.items()}


def serving(url):
    """A site is serving when it answers at all and does not answer with a server error."""
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status < 500
    except urllib.error.HTTPError as error:
        return error.code < 500
    except Exception:
        return False


def wait(deployment, timeout, interval=20):
    urls = {name: (value.get("urls") or [None])[0]
            for name, value in (deployment.get("environments") or {}).items()}
    urls = {name: url for name, url in urls.items() if url}
    deadline = time.time() + timeout
    pending = dict(urls)
    while pending and time.time() < deadline:
        for name, url in list(pending.items()):
            if serving(url):
                print(json.dumps({"event": "serving", "site": name}), flush=True)
                pending.pop(name)
        if pending:
            time.sleep(interval)
    for name, url in pending.items():
        print(json.dumps({"event": "not_serving", "site": name, "url": url}), flush=True)
    return not pending


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", type=int, required=True)
    ap.add_argument("--deployment-config")
    ap.add_argument("--wait", type=int, default=0,
                    help="seconds to wait for every site to serve before doing anything else")
    ap.add_argument("--snapshot")
    ap.add_argument("--verify")
    args = ap.parse_args()

    if args.wait:
        if not args.deployment_config:
            raise SystemExit("--wait needs --deployment-config")
        with open(args.deployment_config) as handle:
            deployment = json.load(handle)
        if not wait(deployment, args.wait):
            raise SystemExit("deployment is not serving; refusing to measure against it")

    if not (args.snapshot or args.verify):
        return
    taken = fingerprint(args.instance)
    missing = [f"{site}.{label}" for site, columns in taken.items()
               for label, value in columns.items() if value is None]
    if missing:
        raise SystemExit("could not read: " + ", ".join(missing))

    if args.snapshot:
        with open(args.snapshot, "w") as handle:
            json.dump(taken, handle, indent=2)
        print(json.dumps({"event": "snapshot", "path": args.snapshot, "state": taken}, indent=2))

    if args.verify:
        with open(args.verify) as handle:
            reference = json.load(handle)
        drift = {f"{site}.{label}": (reference.get(site, {}).get(label), value)
                 for site, columns in taken.items() for label, value in columns.items()
                 if reference.get(site, {}).get(label) != value}
        print(json.dumps({"event": "verify", "reference": args.verify,
                          "pristine": not drift, "drift": drift}, indent=2))
        if drift:
            raise SystemExit(f"{len(drift)} counters differ from pristine; the reset did not take")


main()
