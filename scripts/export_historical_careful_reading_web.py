#!/usr/bin/env python3
"""Merge the 2014-2019 careful-reading corpus into the static web trainer.

The current web corpus already contains curated/deduplicated 2020+ records.
This exporter keeps those records unchanged (and therefore preserves browser
progress IDs), rebuilds the historical slice from MySQL, and refreshes the
corpus totals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "web" / "careful-reading-locator" / "data" / "corpus.json"


def mysql(container: str, database: str, sql: str) -> list[list[str]]:
    command = [
        "docker",
        "exec",
        "-i",
        container,
        "sh",
        "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql '
        "--default-character-set=utf8mb4 -N -B -uroot "
        + database,
    ]
    result = subprocess.run(
        command,
        input=sql,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [line.split("\t") for line in result.stdout.splitlines() if line]


def dehex(value: str) -> str:
    if not value or value == "NULL":
        return ""
    return bytes.fromhex(value).decode("utf-8", errors="replace")


def paragraph_count(text: str) -> int:
    return len([block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()])


def load_historical(container: str, database: str) -> list[dict]:
    passage_rows = mysql(
        container,
        database,
        """
        SELECT p.id,e.year,e.month,e.set_number,p.passage_index,
               HEX(p.title),HEX(p.content_text)
        FROM passages p
        JOIN exams e ON e.id=p.exam_id
        WHERE p.passage_type='careful_reading' AND e.year BETWEEN 2014 AND 2019
        ORDER BY e.year DESC,e.month DESC,e.set_number,p.passage_index;
        """,
    )
    question_rows = mysql(
        container,
        database,
        """
        SELECT q.passage_id,q.id,q.question_number,HEX(q.stem_text),
               o.option_label,HEX(o.option_text),
               COALESCE(a.answer_value,''),HEX(COALESCE(a.answer_text,''))
        FROM questions q
        JOIN passages p ON p.id=q.passage_id
        JOIN exams e ON e.id=q.exam_id
        JOIN options o ON o.question_id=q.id
        LEFT JOIN answer_keys a ON a.question_id=q.id
        WHERE q.question_type='careful_reading' AND e.year BETWEEN 2014 AND 2019
        ORDER BY q.passage_id,q.question_number,o.sort_order;
        """,
    )

    questions_by_passage: dict[str, dict[str, dict]] = {}
    for passage_id, question_id, number, stem_hex, label, option_hex, answer, answer_text_hex in question_rows:
        questions = questions_by_passage.setdefault(passage_id, {})
        question = questions.setdefault(
            question_id,
            {
                "id": question_id,
                "number": int(number),
                "stem": dehex(stem_hex),
                "options": [],
                "answer": {"label": answer, "text": dehex(answer_text_hex)},
            },
        )
        question["options"].append({"label": label, "text": dehex(option_hex)})

    passages = []
    for passage_id, year, month, set_number, passage_index, title_hex, text_hex in passage_rows:
        text = dehex(text_hex)
        identity = f"{year}:{month}:{set_number}:{passage_index}:{text}"
        passages.append(
            {
                "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
                "sourceId": passage_id,
                "year": int(year),
                "month": int(month),
                "set": int(set_number),
                "passage": int(passage_index),
                "title": dehex(title_hex),
                "text": text,
                "paragraphCount": paragraph_count(text),
                "sources": [
                    {
                        "year": int(year),
                        "month": int(month),
                        "set": int(set_number),
                        "passage": int(passage_index),
                    }
                ],
                "questions": list(questions_by_passage.get(passage_id, {}).values()),
            }
        )
    return passages


def validate(passages: list[dict]) -> None:
    if len(passages) != 72:
        raise RuntimeError(f"expected 72 historical passages, got {len(passages)}")
    questions = [question for passage in passages for question in passage["questions"]]
    if len(questions) != 360:
        raise RuntimeError(f"expected 360 historical questions, got {len(questions)}")
    incomplete = [
        question["id"]
        for question in questions
        if len(question["options"]) != 4 or not question["answer"]["label"]
    ]
    if incomplete:
        raise RuntimeError(f"historical questions missing options/answers: {incomplete[:10]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="datamind-ai-mysql-1")
    parser.add_argument("--database", default="cet4")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    corpus = json.loads(args.output.read_text(encoding="utf-8"))
    historical = load_historical(args.container, args.database)
    validate(historical)

    current = [passage for passage in corpus["passages"] if int(passage["year"]) >= 2020]
    passages = sorted(
        current + historical,
        key=lambda item: (-item["year"], -item["month"], item["set"], item["passage"]),
    )
    corpus["passages"] = passages
    corpus["meta"]["passageCount"] = len(passages)
    corpus["meta"]["questionCount"] = sum(len(passage["questions"]) for passage in passages)
    args.output.write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {len(passages)} passages and {corpus['meta']['questionCount']} questions "
        f"to {args.output}"
    )


if __name__ == "__main__":
    main()
