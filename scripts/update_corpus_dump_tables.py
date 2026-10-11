#!/usr/bin/env python3
"""Replace selected table blocks in the tracked corpus dump.

This keeps generated lexical rows local while allowing verified answer and
careful-reading analysis tables to be synchronized from a full local dump.
"""

from __future__ import annotations

import argparse
from pathlib import Path


HEADER = "--\n-- Table structure for table `{table}`\n--\n"
NEXT_TABLE = "--\n-- Table structure for table `"
TAIL_MARKERS = ("--\n-- Dumping routines for database", "-- Dump completed on")


def bounds(content: str, table: str) -> tuple[int, int] | None:
    start = content.find(HEADER.format(table=table))
    if start < 0:
        return None
    candidates = [content.find(NEXT_TABLE, start + 1)]
    candidates.extend(content.find(marker, start + 1) for marker in TAIL_MARKERS)
    ends = [value for value in candidates if value >= 0]
    return start, min(ends) if ends else len(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("tables", nargs="+")
    args = parser.parse_args()

    target = args.target.read_text(encoding="utf-8")
    source = args.source.read_text(encoding="utf-8")
    for table in args.tables:
        source_bounds = bounds(source, table)
        if source_bounds is None:
            raise SystemExit(f"Source table block not found: {table}")
        block = source[source_bounds[0]:source_bounds[1]]
        target_bounds = bounds(target, table)
        if target_bounds is None:
            insert_at = next(
                (target.find(marker) for marker in TAIL_MARKERS if target.find(marker) >= 0),
                len(target),
            )
            target = target[:insert_at] + block + target[insert_at:]
        else:
            target = target[:target_bounds[0]] + block + target[target_bounds[1]:]
    with args.target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(target)


if __name__ == "__main__":
    main()
