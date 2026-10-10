#!/usr/bin/env python3
"""Measure careful-reading patterns from the verified local corpus snapshot."""

from __future__ import annotations

import ast
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


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
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    passages = {row[0]: row for row in load_insert("passages") if row[3] == "careful_reading"}
    questions = {row[0]: row for row in load_insert("questions") if row[6] == "careful_reading"}
    eligible = audit["eligible"]
    annotated = [row for row in eligible if row.get("analysis_eligible")]

    by_passage = defaultdict(list)
    for row in annotated:
        passage_id = questions[row["question_id"]][4]
        by_passage[passage_id].append(row)

    unique_question_count = 0
    all_unique_passages = 0
    for rows in by_passage.values():
        counts = Counter((r["evidence_paragraph_start"], r["evidence_paragraph_end"]) for r in rows)
        unique_question_count += sum(counts[(r["evidence_paragraph_start"], r["evidence_paragraph_end"])] == 1 for r in rows)
        all_unique_passages += len(rows) == 5 and len(counts) == 5

    offsets = Counter()
    locator_confidences = []
    pair_classes = Counter()
    question_with_replacement = 0
    type_counts = Counter(solver_type(row["stem"]) for row in eligible)
    type_annotated_counts = Counter()
    type_replacements = Counter()
    source_types = Counter(row["question_subtype"] for row in annotated)
    for row in annotated:
        question = questions[row["question_id"]]
        passage = passages[question[4]][6]
        all_sentences = sentences(passage)
        locator, confidence = locator_index(all_sentences, row["stem"])
        evidence = evidence_index(all_sentences, row["evidence_text"])
        if locator is None or evidence is None or confidence < 0.35:
            offsets["不可可靠定位"] += 1
        else:
            locator_confidences.append(confidence)
            delta = evidence - locator
            offsets[{0: "本句", -1: "前一句", 1: "后一句"}.get(delta, "相隔两句及以上")] += 1
        replaced = False
        for pair in row.get("paraphrase_pairs", []):
            left, right = soft(pair.get("original", "")), soft(pair.get("option", ""))
            if not left or not right:
                continue
            if left == right:
                pair_classes["字面一致"] += 1
            else:
                overlap = len(set(left.split()) & set(right.split())) / max(1, len(set(left.split()) | set(right.split())))
                pair_classes["部分词面重合" if overlap >= 0.35 else "低词面同义改写"] += 1
                replaced = True
        if replaced:
            question_with_replacement += 1
        kind = solver_type(row["stem"])
        type_annotated_counts[kind] += 1
        if replaced:
            type_replacements[kind] += 1

    reliable_total = sum(value for key, value in offsets.items() if key != "不可可靠定位")
    result = {
        "corpus": {
            "exams": 42, "passages": 84, "questions": 420,
            "answer_coverage": len(eligible), "annotation_coverage": len(annotated),
        },
        "one_paragraph_one_question": {
            "question_level_count": unique_question_count,
            "question_level_total": len(annotated),
            "question_level_probability": round(unique_question_count / len(annotated), 4),
            "passage_level_count": all_unique_passages,
            "passage_level_total": sum(len(rows) == 5 for rows in by_passage.values()),
            "passage_level_probability": round(all_unique_passages / max(1, sum(len(rows) == 5 for rows in by_passage.values())), 4),
        },
        "evidence_relative_to_locator": {
            "method": "题干非停用实词按段内IDF定位；证据句由来源标注回配；置信度<0.35不计概率",
            "counts": dict(offsets),
            "reliable_total": reliable_total,
            "probabilities": {key: round(value / reliable_total, 4) for key, value in offsets.items() if key != "不可可靠定位"},
            "mean_locator_confidence": round(sum(locator_confidences) / max(1, len(locator_confidences)), 4),
        },
        "paraphrase": {
            "questions_with_nonliteral_answer_mapping": question_with_replacement,
            "questions_with_mapping_total": len(annotated),
            "probability": round(question_with_replacement / len(annotated), 4),
            "pair_classes": dict(pair_classes),
            "note": "这是正确选项与证据短语的改写率；不是题干定位锚点本身的同义替换率。",
        },
        "source_question_types": dict(source_types),
        "solver_question_types": {
            key: {
                "count": value,
                "share": round(value / len(eligible), 4),
                "annotated_count": type_annotated_counts[key],
                "nonliteral_answer_mapping_rate": round(type_replacements[key] / max(1, type_annotated_counts[key]), 4),
            }
            for key, value in type_counts.most_common()
        },
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
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
