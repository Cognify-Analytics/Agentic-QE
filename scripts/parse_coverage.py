#!/usr/bin/env python3
"""Parse a Cobertura-style coverage.xml into the clean JSON shape
skills need for .qa/test-inventory.json's "coverage" fields.

Cobertura XML is produced by pytest-cov (--cov-report=xml) and by
coverage tooling for several other languages/frameworks, which is why
it's the one format this script standardizes on for Phase 1.

Usage:
    python scripts/parse_coverage.py [path/to/coverage.xml] [--out out.json]

With no arguments, reads ./coverage.xml and prints JSON to stdout:

    {
      "total": 67.4,
      "measured_at": "coverage.xml",
      "files": [
        {"path": "src/orders.py", "coverage": 82.1},
        {"path": "src/users.py", "coverage": 45.2}
      ]
    }
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET


def _source_prefix(root):
    """Cobertura records class filenames relative to the <source> root
    (e.g. "orders.py" when --cov=src was used), not the repo root. Recover
    a repo-relative prefix (e.g. "src") from the last path component of
    the first <source> entry, so output paths match the "src/orders.py"
    convention used elsewhere (e.g. .qa/test-inventory.json).
    """
    source_el = root.find("./sources/source")
    if source_el is None or not source_el.text:
        return ""
    source_path = source_el.text.strip().replace("\\", "/").rstrip("/")
    return source_path.rsplit("/", 1)[-1] if source_path else ""


def parse_coverage_xml(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    total_line_rate = float(root.attrib.get("line-rate", 0.0))
    prefix = _source_prefix(root)

    files = []
    for cls in root.iter("class"):
        filename = cls.attrib.get("filename")
        line_rate = cls.attrib.get("line-rate")
        if filename is None or line_rate is None:
            continue
        clean_filename = filename.replace("\\", "/")
        path = f"{prefix}/{clean_filename}" if prefix else clean_filename
        files.append(
            {
                "path": path,
                "coverage": round(float(line_rate) * 100, 1),
            }
        )

    # Cobertura can list the same file more than once across packages;
    # keep the highest reported figure for each path.
    by_path = {}
    for entry in files:
        existing = by_path.get(entry["path"])
        if existing is None or entry["coverage"] > existing["coverage"]:
            by_path[entry["path"]] = entry

    return {
        "total": round(total_line_rate * 100, 1),
        "files": sorted(by_path.values(), key=lambda f: f["path"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "xml_path", nargs="?", default="coverage.xml",
        help="path to the Cobertura-style coverage.xml (default: ./coverage.xml)",
    )
    parser.add_argument(
        "--out", default=None,
        help="write JSON to this file instead of stdout",
    )
    args = parser.parse_args()

    try:
        result = parse_coverage_xml(args.xml_path)
    except FileNotFoundError:
        print(
            json.dumps({"error": f"coverage file not found: {args.xml_path}"}),
            file=sys.stderr,
        )
        sys.exit(1)
    except ET.ParseError as exc:
        print(
            json.dumps({"error": f"could not parse {args.xml_path}: {exc}"}),
            file=sys.stderr,
        )
        sys.exit(1)

    result["measured_at"] = args.xml_path
    output = json.dumps(result, indent=2)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
