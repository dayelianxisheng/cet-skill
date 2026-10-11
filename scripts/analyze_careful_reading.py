#!/usr/bin/env python3
"""Measure careful-reading patterns from the verified local corpus snapshot."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from import_careful_reading_web_analysis import dehex, mysql


ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "data" / "cet4_with_answers.sql"
AUDIT = ROOT / "data" / "careful_reading_web_audit.json"
OUTPUT = ROOT / "data" / "careful_reading_statistics.json"

STOP = set("what which who whom whose when where why how does do did is are was were has have had can could would should may might the a an passage author according say says said learn about from following most likely probably tell tells us we infer conclude imply suggest regarding of in on to for and or that this these those it its be been being".split())


def load_insert(table: str) -> list[tuple]:
    marker = "INSERT INTO "
    with SQL.open(encoding="utf-8") as handle:
        line = next(row for row in handle if row.startswith(marker) and table in row[:80])
    payload = line.split(" VALUES ", 1)[1].rstrip().rstrip(";")
    payload = re.sub(r"(?<![A-Za-z0-9_])NULL(?![A-Za-z0-9_])", "None", payload)
    return ast.literal_eval("[" + payload + "]")


def soft(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def tokens(value: str) -> list[str]:
    return [token for token in soft(value).split() if token not in STOP and len(token) > 1]


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])(?:[\"'”’)]*)\s+(?=[A-Z0-9\"'“‘(])", text.strip())
    return [part.strip() for part in parts if part.strip()]


def evidence_index(all_sentences: list[str], evidence: str) -> int | None:
    target = soft(evidence)
    if not target:
        return None
    best = (-1.0, None)
    target_tokens = set(target.split())
    for index, sentence in enumerate(all_sentences):
        candidate = soft(sentence)
        overlap = len(target_tokens & set(candidate.split())) / max(1, len(target_tokens))
        if target in candidate or candidate in target:
            overlap += 2
        if overlap > best[0]:
            best = (overlap, index)
    return best[1] if best[0] >= 0.35 else None


def locator_index(all_sentences: list[str], stem: str) -> tuple[int | None, float]:
    query = tokens(stem)
    if not query:
        return None, 0.0
    document_frequency = Counter()
    sentence_tokens = []
    for sentence in all_sentences:
        current = set(tokens(sentence))
        sentence_tokens.append(current)
        document_frequency.update(current)
    scored = []
    for index, current in enumerate(sentence_tokens):
        matched = set(query) & current
        score = sum(math.log((len(all_sentences) + 1) / (document_frequency[word] + 0.5)) for word in matched)
        scored.append((score, len(matched), index))
    scored.sort(reverse=True)
    best = scored[0]
    if best[1] == 0:
        return None, 0.0
    second = scored[1][0] if len(scored) > 1 else 0.0
    confidence = min(1.0, 0.25 * best[1] + max(0.0, best[0] - second) / max(1.0, best[0]))
    return best[2], confidence


def solver_type(stem: str) -> str:
    value = soft(stem)
    rules = [
        ("主旨目的题", r"mainly (about|discuss)|main idea|best title|purpose of the passage|passage (mainly|primarily)"),
        ("推断判断题", r"\b(infer|conclude|imply|suggest)\b|most likely|probably"),
        ("词义指代题", r"\b(word|phrase|term)\b.*\bmean|refer to|closest in meaning"),
        ("态度观点题", r"attitude|tone|view of|think of"),
        ("例证目的题", r"mention|cite|example|illustrate|quote|quotation"),
        ("原因题", r"^why\b|reason|account for"),
        ("方式过程题", r"^how\b|in what way|by what means"),
    ]
    for name, pattern in rules:
        if re.search(pattern, value):
            return name
    return "事实细节题"


def main() -> None:
    raw_rows = mysql(
        "cet4",
        "SELECT p.id,HEX(p.content_text),q.id,HEX(q.stem_text),a.question_subtype,"
        "a.evidence_paragraph_start,a.evidence_paragraph_end "
        "FROM passages p JOIN questions q ON q.passage_id=p.id "
        "JOIN careful_reading_analysis a ON a.question_id=q.id "
        "WHERE p.passage_type='careful_reading' ORDER BY p.id,q.question_number",
    )
    rows = [
        {
            "passage_id": int(row[0]), "passage": dehex(row[1]), "question_id": int(row[2]),
            "stem": dehex(row[3]), "source_type": row[4],
            "evidence_span": (int(row[5]), int(row[6])),
        }
        for row in raw_rows
    ]
    by_passage = defaultdict(list)
    for row in rows:
        by_passage[row["passage_id"]].append(row)

    def paragraph_metrics(passage_ids: list[int]) -> dict:
        question_total = unique_questions = all_distinct = 0
        for passage_id in passage_ids:
            current = by_passage[passage_id]
            counts = Counter(row["evidence_span"] for row in current)
            question_total += len(current)
            unique_questions += sum(counts[row["evidence_span"]] == 1 for row in current)
            all_distinct += len(current) == 5 and len(counts) == 5
        return {
            "passages": len(passage_ids), "questions": question_total,
            "question_level_unique": unique_questions,
            "question_level_probability": round(unique_questions / question_total, 4),
            "five_distinct_passages": all_distinct,
            "passage_level_probability": round(all_distinct / len(passage_ids), 4),
        }

    passage_ids = list(by_passage)
    fingerprints = {}
    for passage_id in passage_ids:
        normalized = soft(by_passage[passage_id][0]["passage"])
        fingerprints.setdefault(hashlib.sha256(normalized.encode("utf-8")).hexdigest(), passage_id)
    locator_stats = json.loads((ROOT / "data" / "careful_reading_locator_statistics.json").read_text(encoding="utf-8"))
    source_types = Counter(row["source_type"] for row in rows)
    solver_types = Counter(solver_type(row["stem"]) for row in rows)
    result = {
        "corpus": {
            "exams": 42, "passage_records": len(passage_ids), "unique_passages": len(fingerprints),
            "question_records": len(rows), "unique_questions_by_passage_and_stem": locator_stats["deduplicated_by_passage_and_stem"]["questions"],
            "answer_coverage": 420, "evidence_annotation_coverage": len(rows),
        },
        "one_paragraph_one_question": {
            "record_weighted": paragraph_metrics(passage_ids),
            "deduplicated": paragraph_metrics(list(fingerprints.values())),
        },
        "locator_analysis": locator_stats,
        "source_question_types": dict(source_types),
        "solver_question_types": {key: {"count": value, "share": round(value / len(rows), 4)} for key, value in solver_types.most_common()},
        "markers": {
            "主旨目的题": ["mainly about/discuss", "main idea", "best title", "purpose of the passage"],
            "推断判断题": ["infer", "conclude", "imply", "suggest", "most likely", "probably"],
            "词义指代题": ["word/phrase/term ... mean", "refer to", "closest in meaning"],
            "态度观点题": ["attitude", "tone", "view of", "think of"],
            "例证目的题": ["mention", "cite", "example", "illustrate", "quote"],
            "原因题": ["why", "reason", "account for"],
            "方式过程题": ["how", "in what way", "by what means"],
            "事实细节题": ["what/which/who/when/where", "according to", "what does ... say/learn"],
        },
        "method_notes": [
            "定位锚点只由同篇五个题干、题号顺序和本地词性信息选择，不读取选项或答案。",
            "答案证据段和证据句来自careful_reading_analysis；15个原缺失项由解析页显式原文改写对回配文章后补齐。",
            "本句/前后句统计覆盖396题；24题无可靠硬定位，不强行制造定位句。",
            "词典产生28个同义候选，逐条人工复核后仅8题存在关系词同义改写；8题仍保留可直接扫描的主体/对象/专名/限定词。",
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
