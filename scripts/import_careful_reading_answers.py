#!/usr/bin/env python3
"""Audit and optionally migrate careful-reading answers from cet4_db to cet4.

Only exact exam/question/option matches are eligible. Existing answer_keys rows
are never overwritten. Use --apply only after reviewing the audit output and
backing up answer_keys.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import unicodedata


def mysql(database: str, sql: str, *, input_sql: str | None = None) -> list[list[str]]:
    command = [
        "docker", "exec", "-i", "cet4_mysql", "sh", "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --default-character-set=utf8mb4 '
        f'-N -B -uroot {database}' + (f' -e "{sql}"' if input_sql is None else ""),
    ]
    result = subprocess.run(
        command,
        input=input_sql,
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


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = value.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"\s+", " ", value).strip().lower()
    return value


def old_select(table: str, first: int) -> str:
    fields = [
        "e.year", "e.month", "e.set_number", f"'{table}'", "HEX(t.source)", "HEX(t.passage_text)"
    ]
    for index in range(5):
        q = first + index
        prefix = "q" + str(q)
        fields.extend(
            [
                f"HEX(t.{prefix}_stem)",
                f"HEX(t.{prefix}_a)",
                f"HEX(t.{prefix}_b)",
                f"HEX(t.{prefix}_c)",
                f"HEX(t.{prefix}_d)",
                f"t.{prefix}_answer",
            ]
        )
    return (
        "SELECT " + ",".join(fields) + f" FROM {table} t "
        "JOIN exam_sections s ON s.id=t.section_id JOIN exams e ON e.id=s.exam_id "
        "ORDER BY e.year,e.month,e.set_number,t.sort_order,t.id"
    )


def load_old() -> dict[tuple[int, int, int, int], dict]:
    result: dict[tuple[int, int, int, int], dict] = {}
    for table, first, passage_index in (
        ("careful_reading_a", 1, 1),
        ("careful_reading_b", 6, 2),
    ):
        for row in mysql("cet4_db", old_select(table, first)):
            year, month, set_number = map(int, row[:3])
            source = dehex(row[4])
            passage = dehex(row[5])
            offset = 6
            questions = []
            for i in range(5):
                stem, a, b, c, d = [dehex(value) for value in row[offset:offset + 5]]
                answer = row[offset + 5].strip().upper()
                questions.append(
                    {
                        "position": i,
                        "number": 46 + i if passage_index == 1 else 51 + i,
                        "stem": stem,
                        "options": {"A": a, "B": b, "C": c, "D": d},
                        "answer": answer,
                    }
                )
                offset += 6
            result[(year, month, set_number, passage_index)] = {
                "table": table,
                "source": source,
                "passage": passage,
                "questions": questions,
            }
    return result


def load_new() -> dict[tuple[int, int, int, int], dict]:
    passage_rows = mysql(
        "cet4",
        "SELECT p.id,e.year,e.month,e.set_number,p.passage_index,HEX(p.content_text) "
        "FROM passages p JOIN exams e ON e.id=p.exam_id "
        "WHERE p.passage_type='careful_reading' ORDER BY e.year,e.month,e.set_number,p.passage_index",
    )
    question_rows = mysql(
        "cet4",
        "SELECT q.id,e.year,e.month,e.set_number,p.passage_index,q.question_number,HEX(q.stem_text),"
        "o.option_label,HEX(o.option_text),IF(a.id IS NULL,0,1) "
        "FROM questions q JOIN exams e ON e.id=q.exam_id JOIN passages p ON p.id=q.passage_id "
        "JOIN options o ON o.question_id=q.id LEFT JOIN answer_keys a ON a.question_id=q.id "
        "WHERE q.question_type='careful_reading' "
        "ORDER BY e.year,e.month,e.set_number,p.passage_index,q.question_number,o.sort_order",
    )
    result: dict[tuple[int, int, int, int], dict] = {}
    for passage_id, year, month, set_number, passage_index, passage_hex in passage_rows:
        key = (int(year), int(month), int(set_number), int(passage_index))
        result[key] = {"passage_id": int(passage_id), "passage": dehex(passage_hex), "questions": {}}
    for qid, year, month, set_number, passage_index, number, stem_hex, label, option_hex, has_answer in question_rows:
        key = (int(year), int(month), int(set_number), int(passage_index))
        question = result[key]["questions"].setdefault(
            int(number),
            {"id": int(qid), "number": int(number), "stem": dehex(stem_hex), "options": {}, "has_answer": bool(int(has_answer))},
        )
        question["options"][label] = dehex(option_hex)
    return result


def audit(old: dict, new: dict) -> tuple[list[dict], list[dict]]:
    eligible: list[dict] = []
    rejected: list[dict] = []
    for key, old_passage in old.items():
        if key not in new:
            continue
        new_passage = new[key]
        passage_exact = norm(old_passage["passage"]) == norm(new_passage["passage"])
        for old_q in old_passage["questions"]:
            new_q = new_passage["questions"].get(old_q["number"])
            reasons = []
            if new_q is None:
                reasons.append("missing_question")
            else:
                if norm(old_q["stem"]) != norm(new_q["stem"]):
                    reasons.append("stem_mismatch")
                if set(new_q["options"]) != {"A", "B", "C", "D"}:
                    reasons.append("option_count")
                for label in "ABCD":
                    if label in new_q["options"] and norm(old_q["options"][label]) != norm(new_q["options"][label]):
                        reasons.append("option_" + label + "_mismatch")
                if old_q["answer"] not in set("ABCD"):
                    reasons.append("invalid_answer")
                if new_q["has_answer"]:
                    reasons.append("already_answered")
            record = {
                "exam": key[:3],
                "passage_index": key[3],
                "question_number": old_q["number"],
                "passage_exact": passage_exact,
                "source_table": old_passage["table"],
                "source": old_passage["source"],
                "answer": old_q["answer"],
                "reasons": sorted(set(reasons)),
            }
            if not reasons:
                record["question_id"] = new_q["id"]
                record["answer_text"] = new_q["options"][old_q["answer"]]
                eligible.append(record)
            else:
                rejected.append(record)
    return eligible, rejected


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def apply_rows(rows: list[dict]) -> None:
    if not rows:
        return
    values = []
    for row in rows:
        source = f"cet4_db.{row['source_table']}::{row['source']}"
        note = "旧应用库迁移；题干及A-D选项逐项一致；passage_exact=" + str(row["passage_exact"]).lower()
        values.append(
            "(" + ",".join(
                [
                    str(row["question_id"]),
                    sql_quote(row["answer"]),
                    sql_quote(row["answer_text"]),
                    sql_quote(source[:255]),
                    "0.9800",
                    sql_quote(note),
                ]
            ) + ")"
        )
    sql = (
        "START TRANSACTION; INSERT INTO answer_keys"
        "(question_id,answer_value,answer_text,source,confidence,notes) VALUES "
        + ",".join(values)
        + "; COMMIT;"
    )
    mysql("cet4", "", input_sql=sql)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old = load_old()
    new = load_new()
    eligible, rejected = audit(old, new)
    summary = {
        "old_passages": len(old),
        "new_passages": len(new),
        "eligible_questions": len(eligible),
        "rejected_questions": len(rejected),
        "eligible_passages": len({(tuple(r["exam"]), r["passage_index"]) for r in eligible}),
        "passage_exact_questions": sum(r["passage_exact"] for r in eligible),
        "rejection_reasons": {},
    }
    for row in rejected:
        for reason in row["reasons"]:
            summary["rejection_reasons"][reason] = summary["rejection_reasons"].get(reason, 0) + 1
    if args.json:
        print(json.dumps({"summary": summary, "eligible": eligible, "rejected": rejected}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        for row in rejected[:30]:
            print("REJECT", row)
    if args.apply:
        apply_rows(eligible)
        print(f"INSERTED={len(eligible)}")
    return 0 if not rejected else 1


if __name__ == "__main__":
    raise SystemExit(main())
