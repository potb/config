import json
import logging
import os
import re
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
DIMENSION = 256
MATCH_COSINE = 0.6
MATCH_MARGIN = 0.15


class VoiceError(RuntimeError):
    pass


def slug(name):
    text = unicodedata.normalize("NFKD", name)
    text = "".join(char for char in text if not unicodedata.combining(char)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        raise VoiceError(f"name {name!r} has no letters or digits")
    return text


def _unit(vector):
    import numpy as np

    vector = np.asarray(vector, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if vector.shape[0] != DIMENSION or not np.isfinite(norm) or norm == 0.0:
        raise VoiceError(f"a voice print is a non-zero {DIMENSION}-d vector, got shape {vector.shape}")
    return vector / norm


def path_for(directory, name):
    return Path(directory) / f"{slug(name)}.json"


def _iso(now):
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write(directory, record):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    target = path_for(directory, record["name"])
    handle, tmp = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(record, out, ensure_ascii=False, indent=1)
        os.replace(tmp, target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return target


def read(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("name"):
        raise VoiceError(f"{path} has no name")
    data["vector"] = _unit(data.get("vector")).tolist()
    return data


def load(directory):
    directory = Path(directory) if directory else None
    if directory is None or not directory.is_dir():
        return []
    records = []
    for entry in sorted(directory.glob("*.json")):
        try:
            records.append(read(entry))
        except (OSError, ValueError, VoiceError) as error:
            LOG.warning("ignoring voice print %s: %s", entry.name, error)
    return records


def find(directory, name):
    path = path_for(directory, name)
    if not path.is_file():
        return None
    return read(path)


def record(name, vector, seconds, meetings, now=None):
    return {
        "name": name,
        "vector": [float(value) for value in _unit(vector)],
        "seconds": round(float(seconds), 1),
        "meetings": list(meetings),
        "confirmed_at": _iso(now or datetime.now(timezone.utc)),
    }


def merge(existing, name, vector, seconds, meeting, now=None):
    if existing is None:
        return record(name, vector, seconds, [meeting] if meeting else [], now)
    if meeting and meeting in existing.get("meetings", []):
        raise VoiceError(f"{existing['name']} already holds meeting {meeting}")
    old_seconds = float(existing.get("seconds") or 0.0)
    new = _unit(vector)
    if old_seconds <= 0 and seconds <= 0:
        combined = _unit(existing["vector"]) + new
    else:
        combined = _unit(existing["vector"]) * old_seconds + new * float(seconds)
    meetings = list(existing.get("meetings", [])) + ([meeting] if meeting else [])
    return record(existing["name"], combined, old_seconds + float(seconds), meetings, now)


def match(centroids, prints, threshold=MATCH_COSINE, margin=MATCH_MARGIN):
    import numpy as np

    results = [{"name": None, "cosine": None, "margin": None} for _ in centroids]
    if not prints or not len(centroids):
        return results
    matrix = np.stack([_unit(p["vector"]) for p in prints])
    candidates = []
    for index, centroid in enumerate(centroids):
        scores = matrix @ _unit(centroid)
        order = np.argsort(-scores)
        best = float(scores[order[0]])
        second = float(scores[order[1]]) if len(order) > 1 else 0.0
        gap = best - max(second, 0.0)
        results[index]["cosine"] = round(best, 3)
        results[index]["margin"] = round(gap, 3)
        results[index]["best"] = prints[order[0]]["name"]
        if best >= threshold and gap >= margin:
            candidates.append((best, index, prints[order[0]]["name"]))
    used = set()
    for best, index, name in sorted(candidates, key=lambda item: -item[0]):
        if name in used:
            continue
        used.add(name)
        results[index]["name"] = name
    return results


def load_vector(path, key):
    path = Path(path)
    if path.suffix == ".npz":
        import numpy as np

        with np.load(path, allow_pickle=False) as data:
            if key not in data.files:
                raise VoiceError(f"{path.name} has no array {key!r}, found {', '.join(data.files)}")
            return _unit(data[key])
    data = json.loads(path.read_text(encoding="utf-8"))
    for holder in (data, data.get("prints") if isinstance(data, dict) else None):
        if isinstance(holder, dict) and key in holder:
            value = holder[key]
            if isinstance(value, dict) and "vector" in value:
                value = value["vector"]
            return _unit(value)
    if isinstance(data, dict) and "vector" in data and data.get("name") == key:
        return _unit(data["vector"])
    raise VoiceError(f"{path.name} has no vector under {key!r}")
