#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GEOFABRIK_REGION_DEPARTEMENTS = {
    "alsace": ["67", "68"],
    "aquitaine": ["24", "33", "40", "47", "64"],
    "auvergne": ["03", "15", "43", "63"],
    "basse-normandie": ["14", "50", "61"],
    "bourgogne": ["21", "58", "71", "89"],
    "bretagne": ["22", "29", "35", "56"],
    "centre": ["18", "28", "36", "37", "41", "45"],
    "champagne-ardenne": ["08", "10", "51", "52"],
    "corse": ["2A", "2B"],
    "franche-comte": ["25", "39", "70", "90"],
    "guadeloupe": ["971"],
    "guyane": ["973"],
    "haute-normandie": ["27", "76"],
    "ile-de-france": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "languedoc-roussillon": ["11", "30", "34", "48", "66"],
    "limousin": ["19", "23", "87"],
    "lorraine": ["54", "55", "57", "88"],
    "martinique": ["972"],
    "mayotte": ["976"],
    "midi-pyrenees": ["09", "12", "31", "32", "46", "65", "81", "82"],
    "nord-pas-de-calais": ["59", "62"],
    "pays-de-la-loire": ["44", "49", "53", "72", "85"],
    "picardie": ["02", "60", "80"],
    "poitou-charentes": ["16", "17", "79", "86"],
    "provence-alpes-cote-d-azur": ["04", "05", "06", "13", "83", "84"],
    "reunion": ["974"],
    "rhone-alpes": ["01", "07", "26", "38", "42", "69", "73", "74"],
}

RT_PROTOCOLS = {"gtfs-rt": "gtfsrt", "siri": "siri", "siri-json": "siri_json"}
STATIC_SPECS = ("gtfs", "netex")
DAY = 24 * 3600
OSM_MAX_AGE = 6 * DAY
FEED_MAX_AGE = DAY // 2

CFG = {}


def log(*parts):
    print("motis-regions:", *parts, flush=True)


def state_dir():
    return Path(CFG["stateDir"])


def requests_dir():
    return state_dir() / "requests"


def read_meta(meta_path):
    try:
        return json.loads(meta_path.read_text())
    except (OSError, ValueError):
        return {}


def fetch(url, dest, *, max_age=0, insecure=False, attempts=3):
    dest = Path(dest)
    meta_path = dest.with_name(dest.name + ".meta")
    meta = read_meta(meta_path) if dest.exists() else {}
    if max_age and meta.get("url") == url and time.time() - meta.get("checked", 0) < max_age:
        return dest

    headers = {"User-Agent": CFG["userAgent"]}
    if meta.get("url") == url:
        if meta.get("etag"):
            headers["If-None-Match"] = meta["etag"]
        if meta.get("last_modified"):
            headers["If-Modified-Since"] = meta["last_modified"]
    context = ssl._create_unverified_context() if insecure else None

    last_error = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120, context=context) as response:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                    shutil.copyfileobj(response, tmp, 1 << 20)
                os.replace(tmp.name, dest)
                meta = {
                    "url": url,
                    "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
            last_error = None
            break
        except urllib.error.HTTPError as e:
            if e.code == 304:
                last_error = None
                break
            last_error = e
            if 400 <= e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_error = e
        if attempt + 1 < attempts:
            time.sleep(5 * (attempt + 1))
    if last_error is not None:
        raise last_error

    meta["checked"] = time.time()
    meta_path.write_text(json.dumps(meta))
    return dest


def fetch_json(url, name, max_age):
    path = state_dir() / "cache" / "catalog" / name
    try:
        fetch(url, path, max_age=max_age)
    except Exception as e:  # noqa: BLE001
        if not path.exists():
            raise
        log(f"{url} unavailable ({e}), using the cached copy")
    return json.loads(path.read_text())


def group(rows, key, value):
    out = {}
    for row in rows:
        out.setdefault(row[key], []).append(row[value])
    return out


def load_catalog():
    urls = CFG["catalogUrls"]
    geofabrik = fetch_json(urls["geofabrik"], "geofabrik-index.json", DAY)
    feeds = fetch_json(urls["transitous"], "transitous-fr.json", DAY)["sources"]
    pan = fetch_json(urls["pan"], "pan-datasets.json", DAY)
    epcis = fetch_json(urls["epcis"], "epcis.json", 30 * DAY)
    departements = fetch_json(urls["departements"], "departements.json", 30 * DAY)

    regions = {}
    for feature in geofabrik["features"]:
        props = feature["properties"]
        if props.get("parent") != "france" or props["id"] not in GEOFABRIK_REGION_DEPARTEMENTS:
            continue
        geometry = feature["geometry"]
        polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        regions[props["id"]] = {
            "id": props["id"],
            "name": props["name"],
            "pbf": props["urls"]["pbf"],
            "departements": GEOFABRIK_REGION_DEPARTEMENTS[props["id"]],
            "polygons": polygons,
        }

    return {
        "regions": regions,
        "feeds": feeds,
        "pan": {d["datagouv_id"]: d for d in pan},
        "epci_departements": {e["code"]: e["codesDepartements"] for e in epcis},
        "region_departements": group(departements, "codeRegion", "code"),
    }


def publish_regions(catalog):
    out = state_dir() / "catalog" / "regions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    data = [{"id": r["id"], "name": r["name"], "polygons": r["polygons"]} for r in catalog["regions"].values()]
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.chmod(tmp, 0o644)
    tmp.replace(out)


def dataset_departements(catalog, dataset):
    out = set()
    for area in dataset.get("covered_area") or []:
        kind, code = area.get("type"), area.get("insee") or ""
        if kind == "pays" and code == "FR":
            out.add("*")
        elif kind == "region":
            out.update(catalog["region_departements"].get(code, []))
        elif kind == "departement":
            out.add(code)
        elif kind == "epci":
            out.update(catalog["epci_departements"].get(code, []))
        elif kind == "commune":
            out.add(code[:3] if code.startswith("97") else code[:2])
    return out


def select_feeds(catalog, region_ids):
    wanted = set()
    for rid in region_ids:
        wanted.update(catalog["regions"][rid]["departements"])
    national = set(CFG["nationalFeeds"])

    static, live, seen = [], {}, set()
    for source in catalog["feeds"]:
        if source.get("skip"):
            continue
        spec = source.get("spec", "gtfs")
        if spec in RT_PROTOCOLS:
            live.setdefault(source["name"], []).append(source)
            continue
        if spec not in STATIC_SPECS or source.get("type") not in ("http", "url") or source["name"] in seen:
            continue
        dataset = catalog["pan"].get(source.get("x-data-gov-fr-dataset-id"))
        area = dataset_departements(catalog, dataset) if dataset else set()
        if source["name"] in national or "*" in area or area & wanted:
            seen.add(source["name"])
            static.append(source)
    return static, live


def pinned_regions():
    try:
        return Path(CFG["pinnedFile"]).read_text().split()
    except OSError as e:
        log(f"no pinned regions ({e})")
        return []


def wanted_regions(catalog):
    pinned = [r for r in pinned_regions() if r in catalog["regions"]]
    ttl = CFG["requestTtlDays"] * DAY
    requested = []
    entries = list(requests_dir().iterdir()) if requests_dir().exists() else []
    for entry in entries:
        if entry.name not in catalog["regions"]:
            log(f"dropping request for unknown region {entry.name}")
            entry.unlink(missing_ok=True)
        elif time.time() - entry.stat().st_mtime > ttl:
            log(f"request for {entry.name} expired")
            entry.unlink(missing_ok=True)
        elif entry.name not in pinned:
            requested.append((entry.stat().st_mtime, entry.name))
    requested.sort(reverse=True)
    room = max(CFG["maxRegions"] - len(pinned), 0)
    if requested[room:]:
        log(f"over the {CFG['maxRegions']}-region cap, not loading: {', '.join(n for _, n in requested[room:])}")
    return pinned, sorted(n for _, n in requested[:room])


def current_manifest():
    try:
        return json.loads((state_dir() / "current" / "manifest.json").read_text())
    except (OSError, ValueError):
        return None


def link_into(src, dest):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)


def fetch_street_map(catalog, regions, build_dir):
    parts = []
    for rid in regions:
        path = state_dir() / "cache" / "osm" / f"{rid}.osm.pbf"
        log(f"street map {rid}")
        fetch(catalog["regions"][rid]["pbf"], path, max_age=OSM_MAX_AGE)
        parts.append(path)
    if len(parts) == 1:
        link_into(parts[0], build_dir / "osm.pbf")
    else:
        subprocess.run(["osmium", "merge", *map(str, parts), "-o", str(build_dir / "osm.pbf")], check=True)


def fetch_timetable(source, build_dir):
    mirror = CFG["mirror"].rstrip("/")
    spec = source.get("spec", "gtfs")
    filename = f"fr_{source['name']}.{spec}.zip"
    path = state_dir() / "cache" / "feeds" / filename
    try:
        fetch(f"{mirror}/{filename}", path, max_age=FEED_MAX_AGE)
    except Exception as e:  # noqa: BLE001
        log(f"{source['name']}: mirror failed ({e}), trying the producer")
        insecure = source.get("http-options", {}).get("ignore-tls-errors", False)
        fetch(source["url"], path, max_age=FEED_MAX_AGE, insecure=insecure)
    link_into(path, build_dir / filename)
    return filename


def fetch_script(name, build_dir):
    path = state_dir() / "cache" / "feeds" / "scripts" / name
    fetch(f"{CFG['mirror'].rstrip('/')}/scripts/{name}", path, max_age=FEED_MAX_AGE)
    link_into(path, build_dir / "scripts" / name)
    return f"scripts/{name}"


def dataset_entry(source, filename, live, build_dir):
    entry = {"path": filename, "extend_calendar": bool(source.get("extend-calendar", False))}
    if source.get("default-timezone"):
        entry["default_timezone"] = source["default-timezone"]
    if source.get("script"):
        try:
            entry["script"] = fetch_script(source["script"], build_dir)
        except Exception as e:  # noqa: BLE001
            log(f"{source['name']}: script {source['script']} unavailable ({e}), importing without it")
    rt = []
    for rt_source in live.get(source["name"], []):
        feed = {"url": rt_source["url"], "protocol": RT_PROTOCOLS[rt_source["spec"]]}
        if rt_source.get("headers"):
            feed["headers"] = rt_source["headers"]
        rt.append(feed)
    if rt:
        entry["rt"] = rt
    return entry


def build(catalog, pinned, on_demand):
    build_dir = state_dir() / "builds" / datetime.now().strftime("%Y%m%dT%H%M%S")
    build_dir.mkdir(parents=True)
    try:
        return assemble_and_import(catalog, build_dir, pinned, on_demand)
    except BaseException:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise


def assemble_and_import(catalog, build_dir, pinned, on_demand):
    regions = pinned + on_demand
    fetch_street_map(catalog, regions, build_dir)

    static, live = select_feeds(catalog, regions)
    datasets, feeds, skipped = {}, [], []
    for source in static:
        try:
            filename = fetch_timetable(source, build_dir)
        except Exception as e:  # noqa: BLE001
            log(f"{source['name']}: skipped, no copy available ({e})")
            skipped.append(source["name"])
            continue
        tag = "fr-" + source["name"].replace("_", "-")
        datasets[tag] = dataset_entry(source, filename, live, build_dir)
        feeds.append({"tag": tag, "spec": source.get("spec", "gtfs"), "realtime": "rt" in datasets[tag]})

    if not datasets or len(skipped) > len(static) / 2:
        raise RuntimeError(f"{len(skipped)} of {len(static)} timetables unavailable, keeping the current import")

    config = json.loads(json.dumps(CFG["motisConfig"]))
    config["osm"] = "osm.pbf"
    config["timetable"]["datasets"] = datasets
    (build_dir / "config.yml").write_text(json.dumps(config, indent=1))

    log(f"importing {', '.join(regions)}: {len(datasets)} timetables, {sum(f['realtime'] for f in feeds)} with live data")
    started = time.time()
    subprocess.run(["motis", "import", "-c", "config.yml", "-d", "data"], cwd=build_dir, check=True)

    (build_dir / "osm.pbf").unlink()
    for f in build_dir.glob("*.zip"):
        f.unlink()

    manifest = {
        "regions": regions,
        "pinned": pinned,
        "on_demand": on_demand,
        "feeds": feeds,
        "skipped_feeds": skipped,
        "built_at": int(time.time()),
        "import_seconds": round(time.time() - started),
    }
    (build_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    swap_current(build_dir)
    return manifest


def swap_current(build_dir):
    current = state_dir() / "current"
    staged = state_dir() / "current.new"
    staged.unlink(missing_ok=True)
    staged.symlink_to(build_dir)
    staged.replace(current)
    (state_dir() / "switched").touch()
    log(f"switched to {build_dir.name}")


def prune_builds():
    builds = sorted((state_dir() / "builds").iterdir())
    live = (state_dir() / "current").resolve()
    for old in builds[:-2]:
        if old.resolve() != live:
            shutil.rmtree(old, ignore_errors=True)


def newest_request_mtime():
    if not requests_dir().exists():
        return 0
    return max((e.stat().st_mtime for e in requests_dir().iterdir()), default=0)


def cmd_sync(args):
    force = args.force
    while True:
        started = time.time()
        catalog = load_catalog()
        publish_regions(catalog)
        pinned, on_demand = wanted_regions(catalog)
        manifest = current_manifest()
        stale = manifest is None or time.time() - manifest["built_at"] > CFG["rebuildAfterDays"] * DAY
        changed = manifest is None or sorted(manifest["regions"]) != sorted(pinned + on_demand)
        if force or stale or changed:
            build(catalog, pinned, on_demand)
            prune_builds()
        else:
            log(f"up to date: {', '.join(manifest['regions'])}")
        force = False
        if newest_request_mtime() < started:
            return


def cmd_status(_args):
    manifest = current_manifest() or {}
    requests = {}
    if requests_dir().exists():
        for entry in requests_dir().iterdir():
            requests[entry.name] = datetime.fromtimestamp(entry.stat().st_mtime, timezone.utc).isoformat()
    print(json.dumps({
        "loaded": manifest.get("regions", []),
        "pinned": manifest.get("pinned", []),
        "requested": requests,
        "max_regions": CFG["maxRegions"],
        "built_at": manifest.get("built_at"),
        "timetables": len(manifest.get("feeds", [])),
        "with_live_data": sum(1 for f in manifest.get("feeds", []) if f.get("realtime")),
        "skipped_feeds": manifest.get("skipped_feeds", []),
    }, indent=1))


def cmd_request(args):
    if args.region not in GEOFABRIK_REGION_DEPARTEMENTS:
        sys.exit(f"unknown region {args.region!r}; known: {', '.join(sorted(GEOFABRIK_REGION_DEPARTEMENTS))}")
    path = requests_dir() / args.region
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    print(f"requested {args.region}")


def main():
    global CFG
    parser = argparse.ArgumentParser(prog="motis-regions", description="Keep the local MOTIS import in line with the regions in use.")
    parser.add_argument("--config", default=os.environ.get("MOTIS_REGIONS_CONFIG"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="rebuild if the wanted regions changed or the import is old")
    s.add_argument("--force", action="store_true", help="rebuild even if nothing changed")
    s.set_defaults(fn=cmd_sync)
    sub.add_parser("status", help="loaded and requested regions").set_defaults(fn=cmd_status)
    s = sub.add_parser("request", help="ask for a region to be loaded")
    s.add_argument("region")
    s.set_defaults(fn=cmd_request)
    args = parser.parse_args()
    if not args.config:
        parser.error("--config or MOTIS_REGIONS_CONFIG is required")
    CFG = json.loads(Path(args.config).read_text())
    args.fn(args)


if __name__ == "__main__":
    main()
