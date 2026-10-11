#!/usr/bin/env python3
"""Recover missing careful-reading evidence from verified article pages.

The 15 unresolved items are global/ending questions whose analysis pages omit
the normal ``rp-locate`` field.  Their explicit source-to-answer paraphrase
pairs are mapped back to the article paragraphs and sentences.  The script
audits by default and writes only with ``--apply``.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from import_careful_reading_web_analysis import mysql, sql_quote


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "data" / "careful_reading_web_audit.json"
CACHE = ROOT / "data" / "careful_reading_articles.json"
REPORT = ROOT / "data" / "careful_reading_evidence_recovery.json"


def soft(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def token_overlap(left: str, right: str) -> float:
    a, b = set(soft(left).split()), set(soft(right).split())
    return len(a & b) / max(1, len(a))


def split_sentences(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])(?:[\"'”’)]*)\s+(?=[A-Z0-9\"'“‘(])", value.strip())
        if part.strip()
    ]


def article_url(section_url: str) -> str:
    return section_url.replace("/sections/", "/articles/")


def fetch_article(session: requests.Session, url: str) -> list[str]:
    response = session.get(article_url(url), timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = [" ".join(node.get_text(" ", strip=True).split()) for node in soup.select("article p")]
    paragraphs = [paragraph for paragraph in paragraphs if len(soft(paragraph).split()) >= 8]
    if not paragraphs:
        raise RuntimeError(f"No article paragraphs: {response.url}")
    return paragraphs


def best_paragraph(phrase: str, paragraphs: list[str]) -> tuple[int, float]:
    scored = []
    for index, paragraph in enumerate(paragraphs, 1):
        normalized_phrase, normalized_paragraph = soft(phrase), soft(paragraph)
        score = token_overlap(phrase, paragraph)
        if normalized_phrase and normalized_phrase in normalized_paragraph:
            score += 2.0
        score += 0.25 * difflib.SequenceMatcher(None, normalized_phrase, normalized_paragraph).ratio()
        scored.append((score, index))
    return max(scored)


def best_sentence(phrase: str, paragraph: str) -> tuple[float, str]:
    scored = []
    for sentence in split_sentences(paragraph):
        score = token_overlap(phrase, sentence)
        if soft(phrase) in soft(sentence):
            score += 2.0
        scored.append((score, sentence))
    return max(scored) if scored else (0.0, paragraph)


def recover(rows: list[dict], delay: float) -> tuple[list[dict], dict[str, list[str]]]:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    session = requests.Session()
    session.headers.update({"User-Agent": "CET-local-evidence-recovery/1.0"})
    recovered = []
    for row in rows:
        url = row["source_url"]
        if url not in cache:
            if cache:
                time.sleep(delay)
            cache[url] = fetch_article(session, url)
        paragraphs = cache[url]
        matches = []
        for pair in row.get("paraphrase_pairs", []):
            phrase = pair.get("original", "")
            if not phrase:
                continue
            paragraph_score, paragraph_number = best_paragraph(phrase, paragraphs)
            sentence_score, sentence = best_sentence(phrase, paragraphs[paragraph_number - 1])
            matches.append(
                {
                    "original": phrase,
                    "paragraph": paragraph_number,
                    "paragraph_score": round(paragraph_score, 4),
                    "sentence_score": round(sentence_score, 4),
                    "sentence": sentence,
                }
            )
        if not matches or min(match["paragraph_score"] for match in matches) < 0.55:
            raise RuntimeError(f"Weak evidence recovery for question {row['question_id']}: {matches}")
        paragraph_numbers = [match["paragraph"] for match in matches]
        evidence_sentences = list(dict.fromkeys(match["sentence"] for match in matches))
        recovered.append(
            {
                "question_id": row["question_id"],
                "exam": row["exam"],
                "passage_index": row["passage_index"],
                "question_number": row["question_number"],
                "question_subtype": row["question_subtype"],
                "evidence_paragraph_start": min(paragraph_numbers),
                "evidence_paragraph_end": max(paragraph_numbers),
                "evidence_text": " ".join(evidence_sentences),
                "paraphrase_pairs": row["paraphrase_pairs"],
                "source_url": url,
                "matches": matches,
            }
        )
    return recovered, cache


def apply_rows(rows: list[dict]) -> None:
    values = []
    for row in rows:
        confidence = min(match["paragraph_score"] for match in row["matches"])
        confidence = max(0.85, min(0.97, confidence / 2.25))
        values.append(
            "(" + ",".join(
                [
                    str(row["question_id"]), sql_quote(row["question_subtype"]),
                    str(row["evidence_paragraph_start"]), str(row["evidence_paragraph_end"]),
                    sql_quote(row["evidence_text"]),
                    sql_quote(json.dumps(row["paraphrase_pairs"], ensure_ascii=False)),
                    sql_quote(row["source_url"]), f"{confidence:.4f}",
                    sql_quote("解析页未提供定位字段；由显式原文改写对回配文章段落和句子"),
                ]
            ) + ")"
        )
    sql = (
        "INSERT INTO careful_reading_analysis"
        "(question_id,question_subtype,evidence_paragraph_start,evidence_paragraph_end,evidence_text,"
        "paraphrase_pairs_json,source_url,confidence,notes) VALUES\n"
        + ",\n".join(values)
        + "\nON DUPLICATE KEY UPDATE question_subtype=VALUES(question_subtype),"
        "evidence_paragraph_start=VALUES(evidence_paragraph_start),"
        "evidence_paragraph_end=VALUES(evidence_paragraph_end),evidence_text=VALUES(evidence_text),"
        "paraphrase_pairs_json=VALUES(paraphrase_pairs_json),source_url=VALUES(source_url),"
        "confidence=VALUES(confidence),notes=VALUES(notes);"
    )
    mysql("cet4", "", input_sql=sql)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    missing = [row for row in audit["eligible"] if not row.get("analysis_eligible")]
    recovered, cache = recover(missing, args.delay)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(json.dumps(recovered, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(recovered, ensure_ascii=False, indent=2))
    if args.apply:
        apply_rows(recovered)
        print(f"APPLIED={len(recovered)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
