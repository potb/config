#!/usr/bin/env python3
"""Validate a generated OpenClaw config against the gateway's own JSON schema.

Usage: validate-openclaw-config.py <config.json> <schema.json>

The gateway prints its schema with `openclaw config schema`. Checking against
it here turns a failed service start on the server into a failed evaluation on
the machine making the change.
"""
import json
import re
import sys


def check(node, sch, path, errors):
    if isinstance(node, dict):
        props = sch.get("properties", {})
        extra = sch.get("additionalProperties")

        for required in sch.get("required", []):
            if required not in node:
                errors.append(f"missing required key: {path}.{required}".lstrip("."))

        for key, value in node.items():
            here = f"{path}.{key}" if path else key
            sub = props.get(key) or (extra if isinstance(extra, dict) else None)

            if sub is None:
                if extra is False:
                    errors.append(f"unknown key: {here}")
                continue

            scalar = not isinstance(value, (dict, list))

            if scalar and "enum" in sub and value not in sub["enum"]:
                errors.append(f"{here}: {value!r} not in {sub['enum']}")

            if scalar and "anyOf" in sub:
                consts = [a["const"] for a in sub["anyOf"] if "const" in a]
                if consts and value not in consts:
                    errors.append(f"{here}: {value!r} not in {consts}")

            if isinstance(value, str) and "pattern" in sub:
                if not re.match(sub["pattern"], value):
                    errors.append(f"{here}: {value!r} does not match {sub['pattern']}")

            check(value, sub, here, errors)

    elif isinstance(node, list):
        items = sch.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(node):
                check(value, items, f"{path}[{index}]", errors)


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    config = json.load(open(sys.argv[1]))
    schema = json.load(open(sys.argv[2]))

    errors = []
    check(config, schema, "", errors)

    if errors:
        print(f"{len(errors)} problem(s) in the OpenClaw config:", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1

    print("OpenClaw config matches the gateway schema")
    return 0


if __name__ == "__main__":
    sys.exit(main())
