#!/usr/bin/env python3
"""Audit and import careful-reading answers/annotations from a public analysis page.

The importer is deliberately conservative:

* every remote stem and A-D option must match the local corpus exactly or pass
  a high-threshold typo-only alignment check;
* existing answer keys are checked and never silently changed;
* analysis rows are written only for fully matched questions;
* --apply is required for database writes.

The source pages expose the answer, question subtype, evidence paragraph,
evidence sentence, and explicit paraphrase pairs.  Full page HTML is not saved.
"""

from __future__ import annotations

import argparse
import difflib
import itertools
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter

import requests
from bs4 import BeautifulSoup


BASE_URL = (
    "https://english-exam.lazynote.cn/cet4/sections/"
    "{year:04d}-{month:02d}-{set_number}/part3-section-c-{passage_index}/"
)
SOURCE_NAME = "english-exam.lazynote.cn careful-reading analysis"


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


def soft_norm(value: str) -> str:
    """Normalize accents, blanks, and punctuation while retaining word content."""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def similarity(left: str, right: str) -> float:
    return difflib.SequenceMatcher(None, soft_norm(left), soft_norm(right)).ratio()


def align_options(local: dict[str, str], remote: dict[str, str]) -> tuple[dict[str, str], list[float]]:
    """Map remote labels to local labels, tolerating source option reordering."""
    labels = "ABCD"
    best: tuple[float, float, tuple[int, ...], list[float]] | None = None
    for permutation in itertools.permutations(range(4)):
        scores = [
            similarity(local[labels[permutation[index]]], remote[labels[index]])
            for index in range(4)
        ]
        candidate = (min(scores), sum(scores), permutation, scores)
        if best is None or candidate[:2] > best[:2]:
            best = candidate
    assert best is not None
    mapping = {labels[index]: labels[best[2][index]] for index in range(4)}
    return mapping, best[3]


def sql_quote(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def load_local() -> dict[tuple[int, int, int, int], dict]:
    rows = mysql(
        "cet4",
        "SELECT q.id,e.year,e.month,e.set_number,p.passage_index,q.question_number,"
        "HEX(q.stem_text),o.option_label,HEX(o.option_text),"
        "COALESCE(a.answer_value,''),HEX(COALESCE(a.answer_text,'')) "
        "FROM questions q JOIN exams e ON e.id=q.exam_id "
        "JOIN passages p ON p.id=q.passage_id JOIN options o ON o.question_id=q.id "
        "LEFT JOIN answer_keys a ON a.question_id=q.id "
        "WHERE q.question_type='careful_reading' "
        "ORDER BY e.year,e.month,e.set_number,p.passage_index,q.question_number,o.sort_order",
    )
    result: dict[tuple[int, int, int, int], dict] = {}
    for (
        qid, year, month, set_number, passage_index, number, stem_hex,
        label, option_hex, old_answer, old_answer_text_hex,
    ) in rows:
        key = (int(year), int(month), int(set_number), int(passage_index))
        passage = result.setdefault(key, {"questions": {}})
        question = passage["questions"].setdefault(
            int(number),
            {
                "id": int(qid),
                "stem": dehex(stem_hex),
                "options": {},
                "old_answer": old_answer,
                "old_answer_text": dehex(old_answer_text_hex),
            },
        )
        question["options"][label] = dehex(option_hex)
    return result


def text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def parse_question(block, number: int) -> dict:
    paper = block.select_one(".lqp-paper")
    stem_node = paper.select_one("[data-pdh-stem]") if paper else None
    options = {
        node.get("data-pdh-letter", "").upper(): text(node)
        for node in (paper.select("[data-pdh-letter]") if paper else [])
    }
    answer_line = text(block.select_one(".rp-row--answer"))
    answer_match = re.search(r"【答案】\s*([A-D])", answer_line)
    qtype = text(block.select_one(".rp-qtype")).strip("（）() ")
    paragraph_label = text(block.select_one(".rp-locate-p"))
    paragraph_numbers = [int(x) for x in re.findall(r"\d+", paragraph_label)]
    evidence = text(block.select_one(".rp-locate-en"))
    pairs = []
    for pair in block.select(".rp-pair"):
        original = text(pair.select_one(".rp-pair-orig"))
        option = text(pair.select_one(".rp-pair-opt"))
        if original or option:
            pairs.append({"original": original, "option": option})
    return {
        "number": number,
        "stem": text(stem_node),
        "options": options,
        "answer": answer_match.group(1) if answer_match else "",
        "question_subtype": qtype,
        "evidence_paragraph_start": min(paragraph_numbers) if paragraph_numbers else None,
        "evidence_paragraph_end": max(paragraph_numbers) if paragraph_numbers else None,
        "evidence_text": evidence,
        "paraphrase_pairs": pairs,
    }


def fetch_passage(session: requests.Session, key: tuple[int, int, int, int]) -> tuple[str, dict[int, dict]]:
    year, month, set_number, passage_index = key
    url = BASE_URL.format(
        year=year, month=month, set_number=set_number, passage_index=passage_index
    )
    response = session.get(url, timeout=30)
    if response.status_code == 404 and passage_index == 1:
        url = url.replace("part3-section-c-1/", "part3-section-c/")
        response = session.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    first = 46 if passage_index == 1 else 51
    parsed = {}
    for number in range(first, first + 5):
        block = soup.select_one(f"#q-{number}")
        if block is not None:
            parsed[number] = parse_question(block, number)
    return url, parsed


def question_identity(local_question: dict, remote_question: dict | None) -> tuple[bool, float, dict[str, str], list[float]]:
    if remote_question is None or set(remote_question["options"]) != set("ABCD"):
        return False, 0.0, {}, []
    stem_score = similarity(local_question["stem"], remote_question["stem"])
    option_mapping, option_scores = align_options(local_question["options"], remote_question["options"])
    return stem_score >= 0.95 and min(option_scores) >= 0.95, stem_score, option_mapping, option_scores


def passage_identity_score(local_passage: dict, remote_questions: dict[int, dict]) -> int:
    return sum(
        question_identity(question, remote_questions.get(number))[0]
        for number, question in local_passage["questions"].items()
    )


def audit(local: dict, delay: float) -> tuple[list[dict], list[dict]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "CET-local-corpus-audit/1.0"})
    eligible: list[dict] = []
    rejected: list[dict] = []
    cache: dict[tuple[int, int, int, int], tuple[str, dict[int, dict]] | Exception] = {}

    def cached_fetch(fetch_key: tuple[int, int, int, int]):
        if fetch_key not in cache:
            if cache:
                time.sleep(delay)
            try:
                cache[fetch_key] = fetch_passage(session, fetch_key)
            except Exception as exc:  # retain failures for the audit
                cache[fetch_key] = exc
        return cache[fetch_key]

    for key in sorted(local):
        candidates = []
        exact_result = cached_fetch(key)
        if not isinstance(exact_result, Exception):
            exact_url, exact_questions = exact_result
            candidates.append((passage_identity_score(local[key], exact_questions), key, exact_url, exact_questions))
        # Some publishers number the same CET paper sets differently.  Identify
        # the paper by all five stems/options, never by set number alone.
        if not candidates or candidates[0][0] < 5:
            for candidate_set in (1, 2, 3):
                candidate_key = (key[0], key[1], candidate_set, key[3])
                if candidate_key == key:
                    continue
                candidate_result = cached_fetch(candidate_key)
                if isinstance(candidate_result, Exception):
                    continue
                candidate_url, candidate_questions = candidate_result
                candidates.append(
                    (
                        passage_identity_score(local[key], candidate_questions),
                        candidate_key,
                        candidate_url,
                        candidate_questions,
                    )
                )
        if not candidates:
            rejected.append(
                {
                    "exam": key[:3],
                    "passage_index": key[3],
                    "reason": "fetch_error",
                    "detail": str(exact_result),
                }
            )
            continue
        match_count, source_key, url, remote_questions = max(candidates, key=lambda item: item[0])
        for number, question in local[key]["questions"].items():
            remote = remote_questions.get(number)
            reasons = []
            warnings = []
            if remote is None:
                reasons.append("missing_remote_question")
            else:
                if set(remote["options"]) != set("ABCD"):
                    reasons.append("remote_option_count")
                identity_ok, stem_score, option_mapping, option_scores = question_identity(question, remote)
                if stem_score < 0.95:
                    reasons.append("stem_identity_failed")
                if not option_scores or min(option_scores) < 0.95:
                    reasons.append("option_identity_failed")
                if remote["answer"] not in set("ABCD"):
                    reasons.append("missing_remote_answer")
                mapped_answer = option_mapping.get(remote["answer"], "")
                if not remote["question_subtype"]:
                    warnings.append("missing_question_subtype")
                if remote["evidence_paragraph_start"] is None or not remote["evidence_text"]:
                    warnings.append("missing_evidence")
                if question["old_answer"] and mapped_answer and question["old_answer"] != mapped_answer:
                    reasons.append("existing_answer_conflict")
            record = {
                "exam": key[:3],
                "passage_index": key[3],
                "question_number": number,
                "question_id": question["id"],
                "source_url": url,
                "source_exam": source_key[:3],
                "passage_match_count": match_count,
                "reasons": sorted(set(reasons)),
                "warnings": sorted(set(warnings)),
            }
            if reasons:
                if remote is not None:
                    record["remote"] = remote
                    record["local_stem"] = question["stem"]
                    record["local_options"] = question["options"]
                rejected.append(record)
            else:
                record.update(remote)
                record["remote_answer"] = remote["answer"]
                record["answer"] = mapped_answer
                record["option_mapping"] = option_mapping
                record["stem_similarity"] = round(stem_score, 6)
                record["option_similarities"] = [round(score, 6) for score in option_scores]
                record["answer_text"] = question["options"][mapped_answer]
                record["has_existing_answer"] = bool(question["old_answer"])
                record["analysis_eligible"] = not warnings
                eligible.append(record)
    return eligible, rejected


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS careful_reading_analysis (
  question_id BIGINT UNSIGNED NOT NULL,
  question_subtype VARCHAR(50) NOT NULL,
  evidence_paragraph_start SMALLINT UNSIGNED NOT NULL,
  evidence_paragraph_end SMALLINT UNSIGNED NOT NULL,
  evidence_text LONGTEXT NOT NULL,
  paraphrase_pairs_json JSON NOT NULL,
  source_url VARCHAR(500) NOT NULL,
  confidence DECIMAL(5,4) NOT NULL,
  notes TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (question_id),
  KEY idx_careful_subtype (question_subtype),
  KEY idx_careful_evidence_paragraph (evidence_paragraph_start,evidence_paragraph_end),
  CONSTRAINT fk_careful_analysis_question FOREIGN KEY (question_id)
    REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def apply_rows(rows: list[dict]) -> None:
    answer_values = []
    analysis_values = []
    for row in rows:
        if not row["has_existing_answer"]:
            answer_values.append(
                "(" + ",".join(
                    [
                        str(row["question_id"]),
                        sql_quote(row["answer"]),
                        sql_quote(row["answer_text"]),
                        sql_quote(row["source_url"][:255]),
                        "0.9900",
                        sql_quote("题干及A-D选项与本地题库逐项一致；网页解析答案"),
                    ]
                ) + ")"
            )
        if row["analysis_eligible"]:
            analysis_values.append(
                "(" + ",".join(
                [
                    str(row["question_id"]),
                    sql_quote(row["question_subtype"]),
                    str(row["evidence_paragraph_start"]),
                    str(row["evidence_paragraph_end"]),
                    sql_quote(row["evidence_text"]),
                    sql_quote(json.dumps(row["paraphrase_pairs"], ensure_ascii=False)),
                    sql_quote(row["source_url"]),
                    "0.9900",
                    sql_quote("题干、选项、答案和定位信息经本地题库逐项校验"),
                ]
                ) + ")"
            )
    sql = "START TRANSACTION;\n" + SCHEMA_SQL
    if answer_values:
        sql += (
            "INSERT INTO answer_keys(question_id,answer_value,answer_text,source,confidence,notes) VALUES\n"
            + ",\n".join(answer_values)
            + ";\n"
        )
    if analysis_values:
        sql += (
            "INSERT INTO careful_reading_analysis"
            "(question_id,question_subtype,evidence_paragraph_start,evidence_paragraph_end,evidence_text,"
            "paraphrase_pairs_json,source_url,confidence,notes) VALUES\n"
            + ",\n".join(analysis_values)
            + "\nON DUPLICATE KEY UPDATE "
            "question_subtype=VALUES(question_subtype),"
            "evidence_paragraph_start=VALUES(evidence_paragraph_start),"
            "evidence_paragraph_end=VALUES(evidence_paragraph_end),"
            "evidence_text=VALUES(evidence_text),"
            "paraphrase_pairs_json=VALUES(paraphrase_pairs_json),"
            "source_url=VALUES(source_url),confidence=VALUES(confidence),notes=VALUES(notes);\n"
        )
    sql += "COMMIT;\n"
    mysql("cet4", "", input_sql=sql)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delay", type=float, default=0.35)
    parser.add_argument("--output", default="data/careful_reading_web_audit.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local = load_local()
    eligible, rejected = audit(local, args.delay)
    reasons = Counter(reason for row in rejected for reason in row.get("reasons", [row.get("reason", "unknown")]))
    summary = {
        "local_passages": len(local),
        "local_questions": sum(len(x["questions"]) for x in local.values()),
        "eligible_questions": len(eligible),
        "analysis_eligible_questions": sum(x["analysis_eligible"] for x in eligible),
        "answer_only_questions": sum(not x["analysis_eligible"] for x in eligible),
        "new_answer_questions": sum(not x["has_existing_answer"] for x in eligible),
        "existing_answer_questions": sum(x["has_existing_answer"] for x in eligible),
        "rejected_records": len(rejected),
        "rejection_reasons": dict(sorted(reasons.items())),
        "source": SOURCE_NAME,
    }
    report = {"summary": summary, "eligible": eligible, "rejected": rejected}
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"AUDIT={args.output}")
    if args.apply:
        apply_rows(eligible)
        print(f"APPLIED={len(eligible)}")
    return 0 if not rejected else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
