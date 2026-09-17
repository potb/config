#!/usr/bin/env python3
"""Fail when the pinned OpenClaw config schema drifts from the gateway's own.

Usage: compare-openclaw-schema.py <pinned.json> <live.json>

The config check validates against a schema committed to the repository so it
can run on macOS, where the Linux gateway cannot be built. This guard runs
wherever the gateway is buildable and fails if the pinned copy is stale, so the
convenience of a vendored schema cannot silently outlive its accuracy.
"""
import gzip
import json
import sys


def load(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rb") as handle:
        return json.load(handle)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    pinned_path, live_path = sys.argv[1], sys.argv[2]
    pinned, live = load(pinned_path), load(live_path)

    if pinned == live:
        return 0

    print("The pinned OpenClaw schema is out of date.", file=sys.stderr)
    print(file=sys.stderr)
    print("Refresh it with:", file=sys.stderr)
    print("  ./scripts/update-openclaw-schema.sh", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
