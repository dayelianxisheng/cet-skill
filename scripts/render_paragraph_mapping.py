#!/usr/bin/env python3
"""Render an option-first paragraph-matching review skeleton from the CET corpus.

This script reads answer_keys and must only be used after the workflow enters the
answer/review state. It preserves paragraph and question text and intentionally
does not add semantic markers; the agent adds those after applying the marking
standard.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys


SAFE_NAME = re.compile(r"^[A-Za-z0-9_]+$")


def run_query(container: str, database: str, sql: str) -> list[list[str]]:
    if not SAFE_NAME.fullmatch(container) or not SAFE_NAME.fullmatch(database):
        raise ValueError("container and database names may contain only letters, digits, and underscores")
    command = [
        "docker",
        "exec",
        container,
        "sh",
        "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" '
        f'mysql --default-character-set=utf8mb4 -N -B -uroot {database} -e "{sql}"',
    ]
    result = subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [line.split("\t") for line in result.stdout.splitlines() if line.strip()]


def dehex(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8", errors="strict")


def load_mapping(args) -> dict:
    exam_rows = run_query(
        args.container,
        args.database,
        "SELECT id,HEX(title) FROM exams "
        f"WHERE year={args.year} AND month={args.month} AND set_number={args.set_number} "
        "AND exam_type='CET4' ORDER BY id;",
    )
    if len(exam_rows) != 1:
        raise RuntimeError(f"expected one exam, found {len(exam_rows)}")
    exam_id = int(exam_rows[0][0])
    title = dehex(exam_rows[0][1])

    passage_rows = run_query(
        args.container,
        args.database,
        "SELECT p.id,HEX(p.title) FROM passages p "
        f"WHERE p.exam_id={exam_id} AND p.passage_type='matching' ORDER BY p.sort_order,p.id;",
    )
    if len(passage_rows) != 1:
        raise RuntimeError(f"expected one matching passage, found {len(passage_rows)}")
    passage_id = int(passage_rows[0][0])
    passage_title = dehex(passage_rows[0][1])

    paragraph_rows = run_query(
        args.container,
        args.database,
        "SELECT paragraph_label,HEX(content_text),sort_order FROM matching_paragraphs "
        f"WHERE passage_id={passage_id} ORDER BY sort_order,id;",
    )
    if not paragraph_rows:
        raise RuntimeError("matching passage has no paragraph rows")

    question_rows = run_query(
        args.container,
        args.database,
        "SELECT a.answer_value,q.question_number,HEX(q.stem_text) "
        "FROM questions q JOIN answer_keys a ON a.question_id=q.id "
        f"WHERE q.exam_id={exam_id} AND q.question_type='matching' "
        "ORDER BY q.question_number,q.id;",
    )
    if not question_rows:
        raise RuntimeError("answer mappings are unavailable; do not use review rendering in blind mode")

    by_letter: dict[str, list[dict]] = {}
    for letter, number, stem_hex in question_rows:
        by_letter.setdefault(letter, []).append(
            {"number": int(number), "stem": dehex(stem_hex)}
        )

    paragraphs = []
    labels = set()
    for letter, content_hex, sort_order in paragraph_rows:
        if letter in labels:
            raise RuntimeError(f"duplicate paragraph label: {letter}")
        labels.add(letter)
        paragraphs.append(
            {
                "label": letter,
                "sort_order": int(sort_order),
                "content": dehex(content_hex),
                "questions": by_letter.get(letter, []),
            }
        )

    missing_labels = sorted(set(by_letter) - labels)
    if missing_labels:
        raise RuntimeError(f"answer letters missing from passage: {','.join(missing_labels)}")

    return {
        "exam": {
            "id": exam_id,
            "year": args.year,
            "month": args.month,
            "set_number": args.set_number,
            "title": title,
        },
        "passage": {"id": passage_id, "title": passage_title},
        "paragraphs": paragraphs,
    }


def render_markdown(data: dict) -> str:
    lines = ["模式：选项反向对应（已读取答案）", ""]
    for paragraph in data["paragraphs"]:
        lines.extend(
            [
                f"### {paragraph['label']}",
                "",
                "原文：",
                "",
                paragraph["content"],
                "",
                "对应题目：",
                "",
            ]
        )
        for question in paragraph["questions"]:
            lines.append(f"{question['number']}. {question['stem']}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args():
    parser = argparse.ArgumentParser(description="Render paragraph-matching option-first review")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--set", dest="set_number", type=int, required=True)
    parser.add_argument("--container", default="cet4_mysql")
    parser.add_argument("--database", default="cet4")
    parser.add_argument("--json", action="store_true", help="emit structured JSON instead of Markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        data = load_mapping(args)
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(data), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
