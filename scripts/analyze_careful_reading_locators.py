#!/usr/bin/env python3
"""Analyze question-stem locator behavior against verified article evidence.

The locator is selected from the five stems in a passage before article text,
options, or answers are consulted.  It is then mapped to article paragraphs by
surface form, simple word-family normalization, and the pinned local dictionary
synonym/related-word tables.  Evidence paragraph labels provide an independent
target for train/test evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from import_careful_reading_web_analysis import dehex, mysql, sql_quote


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "careful_reading_articles.json"
ROWS_OUTPUT = ROOT / "data" / "careful_reading_locator_rows.json"
STATS_OUTPUT = ROOT / "data" / "careful_reading_locator_statistics.json"
ALGORITHM_VERSION = "locator-v1.1"

# Every dictionary-only candidate was reviewed in article context.  True means
# a secondary relation word is genuinely paraphrased; none of these removes all
# usable surface-form subject/object cues from the question.
MANUAL_SYNONYM_REVIEW = {
    47: False, 105: False, 108: False, 161: True, 384: False, 542: False,
    547: False, 602: False, 706: True, 818: False, 877: False, 929: True,
    981: False, 1037: False, 1092: False, 1147: False, 1205: False,
    1209: True, 1258: True, 1317: False, 1482: False, 1538: False,
    1589: True, 1809: False, 2137: False, 2141: False, 2255: True, 2302: True,
}

STOP = set("""
a an the this that these those it its they them their he she his her we us our you your s
what which who whom whose when where why how does do did is are was were be been being
has have had can could would should may might will shall about regarding concerning from
in on at by for to of with as and or but if according following passage paragraph author
learn tell tells told say says said think thinks thought mean means infer inferred imply
implied suggest suggested conclude conclusion concluded probably likely mainly discuss
message opinion view attitude finding findings study studies research researcher researchers
show shows showed indicate indicates indicated advise advised want wants wanted try tries
emphasise emphasize first last final end make makes made one some many most much more
""".split())
GENERIC = set("people person persons thing things way ways world today now time times effect effects result results idea ideas life recent own advice american numerous disadvantage".split())
BRIDGES = {"of", "from", "to", "in", "on", "for", "with", "and", "or", "at", "by"}


def soft(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def words(value: str) -> list[str]:
    return soft(value).split()


def lemma(word: str) -> str:
    irregular = {"women": "woman", "men": "man", "children": "child", "people": "person", "better": "good", "best": "good", "worse": "bad", "worst": "bad"}
    if word in irregular:
        return irregular[word]
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        base = word[:-3]
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if len(word) > 4 and word.endswith("ed"):
        base = word[:-2]
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s"):
        return word[:-1]
    return word


def split_sentences(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])(?:[\"'”’)]*)\s+(?=[A-Z0-9\"'“‘(])", value.strip()) if part.strip()]


def load_questions() -> list[dict]:
    rows = mysql(
        "cet4",
        "SELECT q.id,p.id,e.year,e.month,e.set_number,p.passage_index,q.question_number,"
        "HEX(q.stem_text),HEX(p.content_text),a.question_subtype,a.evidence_paragraph_start,"
        "a.evidence_paragraph_end,HEX(a.evidence_text),a.source_url "
        "FROM questions q JOIN exams e ON e.id=q.exam_id JOIN passages p ON p.id=q.passage_id "
        "JOIN careful_reading_analysis a ON a.question_id=q.id "
        "WHERE q.question_type='careful_reading' "
        "ORDER BY e.year,e.month,e.set_number,p.passage_index,q.question_number",
    )
    result = [
        {
            "question_id": int(row[0]), "passage_id": int(row[1]), "year": int(row[2]),
            "month": int(row[3]), "set_number": int(row[4]), "passage_index": int(row[5]),
            "question_number": int(row[6]), "stem": dehex(row[7]), "passage_text": dehex(row[8]),
            "question_subtype": row[9], "evidence_start": int(row[10]), "evidence_end": int(row[11]),
            "evidence_text": dehex(row[12]), "source_url": row[13],
        }
        for row in rows
    ]
    for row in result:
        raw = soft(row["passage_text"]) + "\x1f" + soft(row["stem"])
        row["question_fingerprint"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return result


def load_lexicon() -> tuple[dict[str, set[str]], dict[str, set[str]], dict[str, set[str]]]:
    synonym_rows = mysql(
        "cet4", "SELECT w.normalized_word,HEX(s.synonym) FROM vocabulary_words w "
        "JOIN vocabulary_synonyms s ON s.word_id=w.id"
    )
    relation_rows = mysql(
        "cet4", "SELECT w.normalized_word,HEX(r.related_word) FROM vocabulary_words w "
        "JOIN vocabulary_relations r ON r.word_id=w.id"
    )
    pos_rows = mysql(
        "cet4", "SELECT w.normalized_word,t.pos FROM vocabulary_words w "
        "JOIN vocabulary_translations t ON t.word_id=w.id WHERE t.pos<>''"
    )
    synonyms: dict[str, set[str]] = defaultdict(set)
    relations: dict[str, set[str]] = defaultdict(set)
    parts_of_speech: dict[str, set[str]] = defaultdict(set)
    for word, value in synonym_rows:
        normalized = soft(dehex(value))
        if normalized:
            synonyms[word].add(normalized)
    for word, value in relation_rows:
        normalized = soft(dehex(value))
        if normalized:
            relations[word].add(normalized)
    for word, pos in pos_rows:
        parts_of_speech[word].add(pos.lower())
    return synonyms, relations, parts_of_speech


def article_url(section_url: str) -> str:
    return section_url.replace("/sections/", "/articles/")


def load_articles(rows: list[dict], delay: float) -> dict[str, list[str]]:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    session = requests.Session()
    session.headers.update({"User-Agent": "CET-local-locator-analysis/1.0"})
    for url in sorted({row["source_url"] for row in rows}):
        if url in cache:
            continue
        response = session.get(article_url(url), timeout=30)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = [" ".join(node.get_text(" ", strip=True).split()) for node in soup.select("article p")]
        paragraphs = [paragraph for paragraph in paragraphs if len(words(paragraph)) >= 8]
        if not paragraphs:
            raise RuntimeError(f"No article paragraphs: {url}")
        cache[url] = paragraphs
        time.sleep(delay)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache


def content_runs(stem: str) -> list[list[str]]:
    raw = re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKC", stem))
    runs, current = [], []
    for token in raw:
        lowered = token.lower()
        if lowered in STOP or len(lowered) <= 1:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(lowered)
    if current:
        runs.append(current)
    return runs


def generate_candidates(stem: str) -> list[dict]:
    candidates: dict[str, dict] = {}
    quoted = {soft(value) for value in re.findall(r"[\"“‘']([^\"”’']+)[\"”’']", stem)}
    proper_tokens = re.findall(r"\b[A-Z][A-Za-z]*(?:[-'][A-Za-z]+)?(?:\s+[A-Z][A-Za-z]*(?:[-'][A-Za-z]+)?){0,2}", stem)
    proper = {soft(value) for value in proper_tokens if soft(value) not in STOP}
    for run in content_runs(stem):
        for size in (1, 2, 3):
            for start in range(0, len(run) - size + 1):
                phrase = " ".join(run[start:start + size])
                if all(token in GENERIC for token in phrase.split()):
                    continue
                candidates[phrase] = {
                    "text": phrase,
                    "kind": "number" if any(token.isdigit() for token in phrase.split()) else
                            "quoted" if phrase in quoted else
                            "proper" if phrase in proper else "content",
                }
    raw_tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]+", unicodedata.normalize("NFKC", stem))]
    for size in (2, 3):
        for start in range(0, len(raw_tokens) - size + 1):
            chunk = raw_tokens[start:start + size]
            if chunk[0] in STOP or chunk[-1] in STOP:
                continue
            if any(token in STOP and token not in BRIDGES for token in chunk[1:-1]):
                continue
            phrase = " ".join(chunk)
            if all(token in GENERIC or token in BRIDGES for token in chunk):
                continue
            candidates.setdefault(phrase, {"text": phrase, "kind": "content"})
    return list(candidates.values())


def choose_anchors(rows: list[dict], parts_of_speech: dict[str, set[str]]) -> dict[int, dict | None]:
    candidate_sets = {row["question_id"]: generate_candidates(row["stem"]) for row in rows}
    global_df = Counter()
    for candidates in candidate_sets.values():
        global_df.update({candidate["text"] for candidate in candidates})
    by_passage = defaultdict(list)
    for row in rows:
        by_passage[row["passage_id"]].append(row)
    selected = {}
    for passage_rows in by_passage.values():
        local_df = Counter()
        for row in passage_rows:
            local_df.update({candidate["text"] for candidate in candidate_sets[row["question_id"]]})
        for row in passage_rows:
            scored = []
            for candidate in candidate_sets[row["question_id"]]:
                phrase = candidate["text"]
                size = len(phrase.split())
                score = math.log((len(rows) + 1) / (global_df[phrase] + 1))
                score += 0.6 if local_df[phrase] == 1 else -0.7 * (local_df[phrase] - 1)
                score += 1.2 * (size - 1)
                score += {"proper": 1.0, "number": 1.8, "quoted": 1.8, "content": 0.0}[candidate["kind"]]
                content_tokens = [token for token in phrase.split() if token not in BRIDGES]
                for token in content_tokens:
                    pos_values = parts_of_speech.get(token, set())
                    if any(pos.startswith("n") for pos in pos_values):
                        score += 0.65
                    elif pos_values and all(pos.startswith(("adj", "adv", "v")) for pos in pos_values):
                        score -= 0.25
                scored.append((score, size, phrase, candidate))
            selected[row["question_id"]] = max(scored)[3] if scored else None
    return selected


def paragraph_features(anchor: str, paragraph: str, synonyms: dict[str, set[str]], relations: dict[str, set[str]]) -> dict:
    raw_anchor_tokens, paragraph_tokens = words(anchor), words(paragraph)
    anchor_tokens = [token for token in raw_anchor_tokens if token not in STOP and token not in BRIDGES and token not in GENERIC]
    if not anchor_tokens:
        anchor_tokens = [token for token in raw_anchor_tokens if token not in STOP and token not in BRIDGES]
    paragraph_set = set(paragraph_tokens)
    paragraph_lemmas = {lemma(token) for token in paragraph_tokens}
    exact = [token for token in anchor_tokens if token in paragraph_set]
    family = [token for token in anchor_tokens if token not in exact and lemma(token) in paragraph_lemmas]
    synonym_hits, relation_hits = [], []
    for token in anchor_tokens:
        if token in exact or token in family:
            continue
        for candidate in synonyms.get(token, set()):
            if candidate in soft(paragraph):
                synonym_hits.append((token, candidate))
                break
        if not any(item[0] == token for item in synonym_hits):
            for candidate in relations.get(token, set()):
                if candidate in soft(paragraph):
                    relation_hits.append((token, candidate))
                    break
    phrase_exact = soft(anchor) in soft(paragraph)
    covered = len(set(exact + family + [x[0] for x in synonym_hits] + [x[0] for x in relation_hits]))
    score = 8.0 * phrase_exact + 2.0 * len(exact) + 1.5 * len(family) + 1.25 * len(synonym_hits) + 1.0 * len(relation_hits)
    return {
        "score": score, "phrase_exact": phrase_exact, "exact": exact, "family": family,
        "synonym_hits": synonym_hits, "relation_hits": relation_hits,
        "coverage": covered / max(1, len(anchor_tokens)),
    }


def classify(features: dict, anchor_size: int) -> str:
    if features["phrase_exact"]:
        return "原词原短语"
    if features["coverage"] == 1 and features["synonym_hits"]:
        return "词典同义替换"
    if features["coverage"] == 1 and features["relation_hits"]:
        return "同根词或派生词"
    if features["coverage"] == 1 and features["family"]:
        return "词形变化"
    if len(features["exact"]) + len(features["family"]) > 0:
        return "部分原词重现"
    if features["synonym_hits"]:
        return "部分词典同义"
    if features["relation_hits"]:
        return "部分同根词"
    return "无可验证词面对应"


def sentence_relation(anchor: str, locator_paragraph: int, paragraphs: list[str], evidence: str, synonyms, relations) -> tuple[str, int, int]:
    flattened = []
    for paragraph_number, paragraph in enumerate(paragraphs, 1):
        for sentence_number, sentence in enumerate(split_sentences(paragraph)):
            flattened.append((paragraph_number, sentence_number, sentence))
    locator_candidates = [
        (paragraph_features(anchor, sentence, synonyms, relations)["score"], index)
        for index, (paragraph_number, _, sentence) in enumerate(flattened)
        if paragraph_number == locator_paragraph
    ]
    locator_index = max(locator_candidates)[1]
    fragments = split_sentences(evidence) or [evidence]
    evidence_candidates = []
    for index, (_, _, sentence) in enumerate(flattened):
        sentence_tokens = set(words(sentence))
        score = max(
            len(set(words(fragment)) & sentence_tokens) / max(1, len(set(words(fragment))))
            + (2.0 if soft(fragment) in soft(sentence) or soft(sentence) in soft(fragment) else 0.0)
            for fragment in fragments
        )
        if score >= 0.35:
            evidence_candidates.append((abs(index - locator_index), -score, index))
    evidence_index = min(evidence_candidates)[2] if evidence_candidates else locator_index
    delta = evidence_index - locator_index
    label = {0: "本句", -1: "前一句", 1: "后一句"}.get(delta, "前两句及以上" if delta < -1 else "后两句及以上")
    return label, locator_index, evidence_index


SCHEMA = """
CREATE TABLE IF NOT EXISTS careful_reading_locator_analysis (
 question_id BIGINT UNSIGNED NOT NULL, anchor_text VARCHAR(255) NOT NULL,
 anchor_kind VARCHAR(30) NOT NULL, match_type VARCHAR(40) NOT NULL,
 matched_text VARCHAR(500) NOT NULL, predicted_paragraph SMALLINT UNSIGNED DEFAULT NULL,
 evidence_paragraph_start SMALLINT UNSIGNED NOT NULL, evidence_paragraph_end SMALLINT UNSIGNED NOT NULL,
 paragraph_hit TINYINT(1) NOT NULL, sentence_relation VARCHAR(40) NOT NULL,
 manual_synonym_verified TINYINT(1) DEFAULT NULL,
 confidence DECIMAL(5,4) NOT NULL, split_label VARCHAR(20) NOT NULL,
 algorithm_version VARCHAR(30) NOT NULL, details_json JSON NOT NULL,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 PRIMARY KEY(question_id), KEY idx_locator_match_type(match_type),
 CONSTRAINT fk_locator_question FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def analyze(rows: list[dict], articles, synonyms, relations, parts_of_speech) -> list[dict]:
    anchors = choose_anchors(rows, parts_of_speech)
    prepared = []
    for row in rows:
        anchor = anchors[row["question_id"]]
        split_label = "test" if row["year"] >= 2024 else "train"
        if anchor is None:
            prepared.append({"row": row, "anchor": None, "split_label": split_label, "scored": []})
            continue
        paragraphs = articles[row["source_url"]]
        scored = []
        for index, paragraph in enumerate(paragraphs, 1):
            features = paragraph_features(anchor["text"], paragraph, synonyms, relations)
            scored.append((features["score"], features["coverage"], -index, index, features))
        scored.sort(reverse=True)
        prepared.append({"row": row, "anchor": anchor, "split_label": split_label, "scored": scored})

    selected_paragraphs: dict[int, int | None] = {}
    by_passage = defaultdict(list)
    for item in prepared:
        by_passage[item["row"]["passage_id"]].append(item)
    for passage_items in by_passage.values():
        passage_items.sort(key=lambda item: item["row"]["question_number"])
        paragraph_count = len(articles[passage_items[0]["row"]["source_url"]])
        dp, back = [], []
        for question_index, item in enumerate(passage_items):
            score_by_paragraph = {entry[3]: entry[0] for entry in item["scored"]}
            expected = 1 + question_index * max(0, paragraph_count - 1) / 4
            current, current_back = {}, {}
            for paragraph in range(1, paragraph_count + 1):
                local = score_by_paragraph.get(paragraph, 0.0) - 0.32 * abs(paragraph - expected)
                if not dp:
                    current[paragraph], current_back[paragraph] = local, None
                else:
                    options = []
                    for previous, previous_score in dp[-1].items():
                        transition = 0.12 if paragraph >= previous else -2.2 * (previous - paragraph)
                        options.append((previous_score + transition + local, previous))
                    current[paragraph], current_back[paragraph] = max(options)
            dp.append(current)
            back.append(current_back)
        paragraph = max(dp[-1], key=dp[-1].get)
        path = [paragraph]
        for index in range(len(passage_items) - 1, 0, -1):
            paragraph = back[index][paragraph]
            path.append(paragraph)
        path.reverse()
        for item, paragraph in zip(passage_items, path):
            best_lexical = item["scored"][0][0] if item["scored"] else 0.0
            selected_paragraphs[item["row"]["question_id"]] = paragraph if best_lexical > 0 else None

    output = []
    for item in prepared:
        row, anchor, split_label = item["row"], item["anchor"], item["split_label"]
        if anchor is None:
            output.append({**row, "anchor_text": "", "anchor_kind": "none", "match_type": "无硬定位词", "matched_text": "", "predicted_paragraph": None, "paragraph_hit": False, "sentence_relation": "不可计算", "confidence": 0.0, "split_label": split_label, "details": {}})
            continue
        predicted = selected_paragraphs[row["question_id"]]
        if predicted is None:
            best = item["scored"][0]
            selected_features = best[4]
        else:
            best = next(entry for entry in item["scored"] if entry[3] == predicted)
            selected_features = best[4]
        competing_scores = [entry[0] for entry in item["scored"] if entry[3] != predicted]
        second_score = max(competing_scores) if competing_scores else 0.0
        paragraphs = articles[row["source_url"]]
        global_features = paragraph_features(anchor["text"], " ".join(paragraphs), synonyms, relations)
        match_type = classify(global_features, len(anchor["text"].split()))
        paragraph_hit = predicted is not None and row["evidence_start"] <= predicted <= row["evidence_end"]
        confidence = 0.0 if predicted is None else min(1.0, 0.45 * selected_features["coverage"] + 0.55 * max(0.0, best[0] - second_score) / max(1.0, best[0]))
        matched = [f"{a}->{b}" for a, b in global_features["synonym_hits"] + global_features["relation_hits"]]
        matched.extend(global_features["exact"] + global_features["family"])
        relation = "不可计算"
        locator_sentence = evidence_sentence = None
        if predicted is not None:
            relation, locator_sentence, evidence_sentence = sentence_relation(anchor["text"], predicted, paragraphs, row["evidence_text"], synonyms, relations)
        output.append(
            {
                **row, "anchor_text": anchor["text"], "anchor_kind": anchor["kind"],
                "match_type": match_type, "matched_text": "; ".join(matched),
                "predicted_paragraph": predicted, "paragraph_hit": paragraph_hit,
                "sentence_relation": relation, "confidence": round(confidence, 4),
                "split_label": split_label,
                "details": {"global_features": global_features, "selected_features": selected_features, "locator_sentence": locator_sentence, "evidence_sentence": evidence_sentence},
            }
        )
    return output


def summarize(rows: list[dict]) -> dict:
    usable = [row for row in rows if row["match_type"] not in {"无硬定位词", "无可验证词面对应"}]
    strict_synonym = [row for row in usable if row["match_type"] in {"词典同义替换", "部分词典同义"}]
    nonexact = [row for row in usable if row["match_type"] not in {"原词原短语", "词形变化"}]
    result = {
        "corpus_questions": len(rows),
        "match_type_counts": dict(Counter(row["match_type"] for row in rows)),
        "usable_hard_locators": len(usable),
        "strict_dictionary_synonym": {
            "count": len(strict_synonym), "denominator": len(usable),
            "probability": round(len(strict_synonym) / max(1, len(usable)), 4),
            "all_question_probability": round(len(strict_synonym) / len(rows), 4),
        },
        "nonexact_locator_mapping": {
            "count": len(nonexact), "denominator": len(usable),
            "probability": round(len(nonexact) / max(1, len(usable)), 4),
        },
    }
    candidate_ids = {
        row["question_id"] for row in rows
        if row["match_type"] in {"词典同义替换", "部分词典同义"}
    }
    if candidate_ids != set(MANUAL_SYNONYM_REVIEW):
        raise RuntimeError(
            "Dictionary candidate set changed; renew manual review: "
            f"added={sorted(candidate_ids - set(MANUAL_SYNONYM_REVIEW))}, "
            f"removed={sorted(set(MANUAL_SYNONYM_REVIEW) - candidate_ids)}"
        )
    reviewed_true = [row for row in rows if MANUAL_SYNONYM_REVIEW.get(row["question_id"]) is True]
    result["manual_synonym_review"] = {
        "dictionary_candidates_reviewed": len(MANUAL_SYNONYM_REVIEW),
        "verified_secondary_relation_synonyms": len(reviewed_true),
        "verified_secondary_rate_all_questions": round(len(reviewed_true) / len(rows), 4),
        "verified_secondary_rate_usable_locators": round(len(reviewed_true) / max(1, len(usable)), 4),
        "pure_hard_locator_synonym_required_observed": 0,
        "note": "人工复核的是定位短语中的关系词；所有确认案例仍保留至少一个可直接扫描的主体、对象、专名或限定词。",
    }
    for split in ("train", "test", "all"):
        current = rows if split == "all" else [row for row in rows if row["split_label"] == split]
        predictable = [row for row in current if row["predicted_paragraph"] is not None]
        current_usable = [row for row in current if row["match_type"] not in {"无硬定位词", "无可验证词面对应"}]
        current_synonym = [row for row in current_usable if row["match_type"] in {"词典同义替换", "部分词典同义"}]
        result[f"locator_coverage_{split}"] = {
            "questions": len(current), "located": len(predictable),
            "coverage": round(len(predictable) / max(1, len(current)), 4),
            "usable_locators": len(current_usable),
            "strict_synonym_rate": round(len(current_synonym) / max(1, len(current_usable)), 4),
        }
    paragraph_offsets = Counter()
    for row in rows:
        predicted = row["predicted_paragraph"]
        if predicted is None:
            continue
        if row["evidence_start"] <= predicted <= row["evidence_end"]:
            label = "同段"
        elif predicted == row["evidence_start"] - 1:
            label = "证据在后一段"
        elif predicted == row["evidence_end"] + 1:
            label = "证据在前一段"
        elif predicted < row["evidence_start"] - 1:
            label = "证据在后两段及以上"
        else:
            label = "证据在前两段及以上"
        paragraph_offsets[label] += 1
    paragraph_total = sum(paragraph_offsets.values())
    result["evidence_relative_to_locator_paragraph"] = {
        "count": paragraph_total,
        "counts": dict(paragraph_offsets),
        "probabilities": {key: round(value / paragraph_total, 4) for key, value in paragraph_offsets.items()},
    }
    relations_count = Counter(row["sentence_relation"] for row in rows if row["sentence_relation"] != "不可计算")
    relations_total = sum(relations_count.values())
    result["answer_relative_to_locator_sentence"] = {
        "count": relations_total, "coverage": round(relations_total / len(rows), 4),
        "counts": dict(relations_count),
        "probabilities": {key: round(value / relations_total, 4) for key, value in relations_count.items()},
    }
    by_type = {}
    for subtype, current in sorted(defaultdict(list, {key: [row for row in rows if row["question_subtype"] == key] for key in {row["question_subtype"] for row in rows}}).items()):
        current_usable = [row for row in current if row in usable]
        current_synonym = [row for row in current_usable if row in strict_synonym]
        by_type[subtype] = {
            "questions": len(current), "usable_locators": len(current_usable),
            "strict_synonym_rate": round(len(current_synonym) / max(1, len(current_usable)), 4),
            "no_hard_or_unresolved": len(current) - len(current_usable),
        }
    result["patterns_by_question_type"] = by_type
    by_position = {}
    for label, test in {
        "首题": lambda row: row["question_number"] in {46, 51},
        "中间题": lambda row: row["question_number"] in {47, 48, 49, 52, 53, 54},
        "末题": lambda row: row["question_number"] in {50, 55},
    }.items():
        current = [row for row in rows if test(row)]
        current_usable = [row for row in current if row in usable]
        current_synonym = [row for row in current_usable if row in strict_synonym]
        by_position[label] = {
            "questions": len(current), "usable_locators": len(current_usable),
            "strict_synonym_rate": round(len(current_synonym) / max(1, len(current_usable)), 4),
            "no_hard_or_unresolved": len(current) - len(current_usable),
        }
    result["patterns_by_question_position"] = by_position
    unique_rows = list({row["question_fingerprint"]: row for row in rows}.values())
    unique_usable = [row for row in unique_rows if row["match_type"] not in {"无硬定位词", "无可验证词面对应"}]
    unique_verified = [row for row in unique_rows if MANUAL_SYNONYM_REVIEW.get(row["question_id"]) is True]
    unique_relations = Counter(row["sentence_relation"] for row in unique_rows if row["sentence_relation"] != "不可计算")
    unique_relation_total = sum(unique_relations.values())
    result["deduplicated_by_passage_and_stem"] = {
        "questions": len(unique_rows),
        "usable_locators": len(unique_usable),
        "verified_secondary_relation_synonyms": len(unique_verified),
        "verified_secondary_rate_all_questions": round(len(unique_verified) / len(unique_rows), 4),
        "verified_secondary_rate_usable_locators": round(len(unique_verified) / max(1, len(unique_usable)), 4),
        "pure_hard_locator_synonym_required_observed": 0,
        "answer_relative_to_locator_sentence": {
            "count": unique_relation_total,
            "counts": dict(unique_relations),
            "probabilities": {key: round(value / unique_relation_total, 4) for key, value in unique_relations.items()},
        },
    }
    return result


def apply_rows(rows: list[dict]) -> None:
    mysql("cet4", "", input_sql=SCHEMA)
    values = []
    for row in rows:
        values.append(
            "(" + ",".join(
                [
                    str(row["question_id"]), sql_quote(row["anchor_text"]), sql_quote(row["anchor_kind"]),
                    sql_quote(row["match_type"]), sql_quote(row["matched_text"]),
                    "NULL" if row["predicted_paragraph"] is None else str(row["predicted_paragraph"]),
                    str(row["evidence_start"]), str(row["evidence_end"]), "1" if row["paragraph_hit"] else "0",
                    sql_quote(row["sentence_relation"]),
                    "NULL" if row["question_id"] not in MANUAL_SYNONYM_REVIEW else ("1" if MANUAL_SYNONYM_REVIEW[row["question_id"]] else "0"),
                    f"{row['confidence']:.4f}", sql_quote(row["split_label"]),
                    sql_quote(ALGORITHM_VERSION), sql_quote(json.dumps(row["details"], ensure_ascii=False)),
                ]
            ) + ")"
        )
    for start in range(0, len(values), 100):
        sql = (
            "INSERT INTO careful_reading_locator_analysis"
            "(question_id,anchor_text,anchor_kind,match_type,matched_text,predicted_paragraph,"
            "evidence_paragraph_start,evidence_paragraph_end,paragraph_hit,sentence_relation,"
            "manual_synonym_verified,confidence,split_label,algorithm_version,details_json) VALUES\n"
            + ",\n".join(values[start:start + 100])
            + "\nON DUPLICATE KEY UPDATE anchor_text=VALUES(anchor_text),anchor_kind=VALUES(anchor_kind),"
            "match_type=VALUES(match_type),matched_text=VALUES(matched_text),predicted_paragraph=VALUES(predicted_paragraph),"
            "evidence_paragraph_start=VALUES(evidence_paragraph_start),evidence_paragraph_end=VALUES(evidence_paragraph_end),"
            "paragraph_hit=VALUES(paragraph_hit),sentence_relation=VALUES(sentence_relation),manual_synonym_verified=VALUES(manual_synonym_verified),confidence=VALUES(confidence),"
            "split_label=VALUES(split_label),algorithm_version=VALUES(algorithm_version),details_json=VALUES(details_json);"
        )
        mysql("cet4", "", input_sql=sql)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delay", type=float, default=0.15)
    args = parser.parse_args()
    rows = load_questions()
    if len(rows) != 420:
        raise RuntimeError(f"Expected 420 annotated questions, found {len(rows)}")
    articles = load_articles(rows, args.delay)
    synonyms, relations, parts_of_speech = load_lexicon()
    analyzed = analyze(rows, articles, synonyms, relations, parts_of_speech)
    stats = summarize(analyzed)
    ROWS_OUTPUT.write_text(json.dumps(analyzed, ensure_ascii=False, indent=2), encoding="utf-8")
    STATS_OUTPUT.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if args.apply:
        apply_rows(analyzed)
        print(f"APPLIED={len(analyzed)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
