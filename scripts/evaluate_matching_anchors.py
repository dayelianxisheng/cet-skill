#!/usr/bin/env python3
"""Evaluate paragraph-matching anchor extraction against the authorized CET corpus.

The extractor never uses answers. Answer letters are used only after extraction to
score whether the selected anchors retrieve the correct paragraph.
"""

from __future__ import annotations

import collections
import difflib
import hashlib
import itertools
import math
import re
import subprocess
import sys

from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer
from sklearn.model_selection import GroupKFold


STOP = set("""
a an the and or but if while although though because as at by for from in into of on
to with without about around through throughout during after before between among
is are was were be been being do does did have has had having can could may might
must should would will shall it its itself they them their theirs he him his she her
hers we us our ours you your yours this that these those there here where when which
who whom whose what why how one ones some any all many much more most less few little
other another same such very really quite rather also only even still just than then
author authors passage paragraph people person thing things way ways part place
according say says said tell tells told make makes made get gets got take takes took
great barrier island
""".split())

LOGIC = {
    "not", "no", "never", "failed", "unable", "unlikely", "without", "despite",
    "although", "because", "cause", "caused", "result", "results", "reason",
    "before", "after", "ago", "first", "last", "more", "less", "most", "least",
    "compared", "unlike", "similar", "different", "increase", "increased",
    "decrease", "decreased", "only", "mainly", "officially", "initially",
}

PARAPHRASE = {
    "purchase": {"buy", "bought", "property"},
    "house": {"home", "property"},
    "failed": {"rejected", "refused", "denied", "turned"},
    "delicious": {"tasty", "mouthwatering", "chef", "dinner", "food"},
    "sleep": {"slept", "asleep"},
    "slept": {"sleep", "asleep"},
    "recognized": {"awarded", "status", "designated"},
    "connected": {"grid", "supply", "facilities", "energy"},
    "power": {"electricity", "energy", "solar", "wind", "grid"},
    "faraway": {"remote", "away", "distance", "km"},
    "artist": {"musician", "painter", "writer", "artists"},
    "attracted": {"drawn", "come", "visit"},
    "pleased": {"glad", "delighted", "happy"},
    "view": {"sight", "scene", "look", "stared"},
    "job": {"work", "position", "employment"},
    "children": {"kids", "child"},
    "child": {"children", "kids"},
    "help": {"assist", "support", "aid"},
    "harm": {"damage", "hurt", "risk"},
    "important": {"essential", "crucial", "significant"},
}


def run_query() -> str:
    sql = (
        "SELECT q.id,e.year,e.month,e.set_number,HEX(q.stem_text),"
        "a.answer_value,HEX(COALESCE(a.answer_text,'')),HEX(p.content_text) "
        "FROM questions q JOIN exams e ON e.id=q.exam_id "
        "JOIN answer_keys a ON a.question_id=q.id "
        "JOIN passages p ON p.id=q.passage_id "
        "WHERE q.question_type='matching' "
        "ORDER BY e.year,e.month,e.set_number,q.question_number;"
    )
    cmd = [
        "docker", "exec", "cet4_mysql", "sh", "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --default-character-set=utf8mb4 '
        f'-N -B -uroot cet4 -e "{sql}"',
    ]
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", stdout=subprocess.PIPE).stdout


def dehex(value: str) -> str:
    return bytes.fromhex(value).decode("utf-8", errors="replace") if value else ""


def split_paragraphs(text: str) -> dict[str, str]:
    text = text.replace("\\n", "\n")
    pattern = re.compile(r"(?m)(?:^|\n)\s*(?:\[([A-Z])\]|([A-Z])\))\s*")
    matches = list(pattern.finditer(text))
    result = {}
    for index, match in enumerate(matches):
        letter = match.group(1) or match.group(2)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[letter] = text[match.end():end].strip()
    return result


def load_rows():
    rows = []
    for line in run_query().splitlines():
        cols = line.split("\t")
        if len(cols) != 8:
            continue
        qid, year, month, set_number, stem_hex, answer, answer_hex, passage_hex = cols
        passage = dehex(passage_hex)
        rows.append({
            "id": int(qid), "year": int(year), "month": int(month),
            "set": int(set_number), "stem": dehex(stem_hex), "answer": answer.strip(),
            "answer_text": dehex(answer_hex), "paragraphs": split_paragraphs(passage),
        })
    return rows


TOKEN_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*|\d+(?:[.,]\d+)?%?")


def stem(word: str) -> str:
    w = word.lower().replace("’", "'")
    if len(w) > 5 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("ed"):
        return w[:-2]
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s"):
        return w[:-1]
    return w


def tokens(text: str):
    return [stem(m.group()) for m in TOKEN_RE.finditer(text)]


def build_idf(rows):
    docs = [set(tokens(p)) for row in rows for p in row["paragraphs"].values()]
    df = collections.Counter(t for doc in docs for t in doc)
    n = max(len(docs), 1)
    return {t: math.log((n + 1) / (c + 0.5)) + 1 for t, c in df.items()}


def exam_common(rows):
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["year"], row["month"], row["set"])].append(row)
    common = {}
    for key, items in grouped.items():
        counts = collections.Counter(t for row in items for t in set(tokens(row["stem"])))
        common[key] = {t for t, c in counts.items() if c >= max(4, math.ceil(len(items) * 0.6))}
    return common


def select_anchor_spans(row, idf, common, max_spans=4):
    """Select non-overlapping blind spans, each containing 1-3 source words."""
    matches = list(TOKEN_RE.finditer(row["stem"]))
    raw_words = [match.group() for match in matches]
    normalized = [stem(word) for word in raw_words]
    topic = common[(row["year"], row["month"], row["set"])]
    token_scores = []
    for tok in normalized:
        if tok in STOP and tok not in LOGIC:
            token_scores.append(0.0)
            continue
        score = idf.get(tok, 1.0)
        if tok in topic and tok not in LOGIC:
            score *= 0.15
        if tok in LOGIC:
            score += 1.8
        if any(ch.isdigit() for ch in tok):
            score += 2.5
        token_scores.append(score)

    candidates = []
    for start in range(len(raw_words)):
        for length in (1, 2, 3):
            end = start + length
            if end > len(raw_words):
                continue
            scores = token_scores[start:end]
            content_count = sum(score > 0 for score in scores)
            if not content_count:
                continue
            utility = sum(scores) + 0.7 * (content_count - 1) - 0.2 * (length - content_count)
            candidates.append((utility, content_count, -length, start, end))

    selected = []
    occupied = set()
    for utility, content_count, neg_length, start, end in sorted(candidates, reverse=True):
        positions = set(range(start, end))
        if positions & occupied:
            continue
        selected.append((start, end))
        occupied.update(positions)
        if len(selected) == max_spans:
            break

    selected.sort()
    spans = [" ".join(raw_words[start:end]) for start, end in selected]
    query = []
    for start, end in selected:
        for tok in normalized[start:end]:
            if tok not in STOP or tok in LOGIC:
                query.append(tok)
    return spans, query


def select_anchor_singletons(row, idf, common):
    """Select up to four one-word anchors for maximum marking convenience."""
    matches = list(TOKEN_RE.finditer(row["stem"]))
    topic = common[(row["year"], row["month"], row["set"])]
    candidates = []
    for index, match in enumerate(matches):
        tok = stem(match.group())
        if tok in STOP and tok not in LOGIC:
            continue
        score = idf.get(tok, 1.0)
        if tok in topic and tok not in LOGIC:
            score *= 0.15
        if tok in LOGIC:
            score += 1.8
        if any(ch.isdigit() for ch in tok):
            score += 2.5
        candidates.append((score, index, match.group(), tok))
    chosen = sorted(candidates, reverse=True)[:4]
    chosen.sort(key=lambda item: item[1])
    return [raw for _, _, raw, _ in chosen], [tok for _, _, _, tok in chosen]


def select_anchor_tokens(row, idf, common, version):
    if version == "v11":
        return select_anchor_spans(row, idf, common)[1]
    if version == "v12":
        return select_anchor_singletons(row, idf, common)[1]
    if version == "v13":
        return select_anchor_spans(row, idf, common, max_spans=2)[1]
    if version == "v14":
        return select_anchor_spans(row, idf, common, max_spans=3)[1]
    raw = tokens(row["stem"])
    topic = common[(row["year"], row["month"], row["set"])]
    candidates = []
    for i, tok in enumerate(raw):
        if tok in STOP and tok not in LOGIC:
            continue
        if tok in topic and tok not in LOGIC:
            continue
        score = idf.get(tok, 1.0)
        if tok in LOGIC:
            score += 1.8
        if any(ch.isdigit() for ch in tok):
            score += 2.5
        candidates.append((score, i, tok))
    limit = 7 if version == "v1" else 10
    chosen = sorted(candidates, reverse=True)[:limit]
    chosen_ids = {i for _, i, _ in chosen}
    if version == "v2":
        for _, i, _ in chosen[:5]:
            for j in (i - 1, i + 1):
                if 0 <= j < len(raw) and raw[j] not in STOP:
                    chosen_ids.add(j)
    return [raw[i] for i in sorted(chosen_ids)]


def expand_query(query, version):
    result = list(query)
    if version == "v2":
        for tok in query:
            result.extend(stem(x) for x in PARAPHRASE.get(tok, ()))
    return result


def rank(row, query, idf, semantic=None, semantic_query=None):
    q = collections.Counter(query)
    scored = []
    for letter, paragraph in row["paragraphs"].items():
        p = collections.Counter(tokens(paragraph))
        score = 0.0
        for tok, qf in q.items():
            if p[tok]:
                score += idf.get(tok, 1.0) * (1 + math.log1p(p[tok])) * qf
        if semantic is not None:
            score += semantic.similarity(semantic_query or " ".join(query), paragraph) * 12.0
        scored.append((score, letter))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [letter for _, letter in scored]


def rank_local(row, query, semantic=None, semantic_query=None):
    """Rank with within-passage distinctiveness after blind anchors are frozen."""
    paragraph_tokens = {letter: tokens(text) for letter, text in row["paragraphs"].items()}
    n = max(len(paragraph_tokens), 1)
    df = collections.Counter(tok for toks in paragraph_tokens.values() for tok in set(toks))
    local_idf = {tok: math.log((n + 1) / (count + 0.5)) + 1 for tok, count in df.items()}
    q = collections.Counter(query)
    q_unique = set(query)
    scored = []
    for letter, toks in paragraph_tokens.items():
        p = collections.Counter(toks)
        matched = {tok for tok in q_unique if p[tok]}
        score = sum(local_idf.get(tok, 1.0) * (1 + math.log1p(p[tok])) * q[tok] for tok in matched)
        score += 4.0 * len(matched) / max(len(q_unique), 1)
        if semantic is not None:
            score += semantic.similarity(semantic_query or " ".join(query), row["paragraphs"][letter]) * 10.0
        scored.append((score, letter))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [letter for _, letter in scored]


def evaluate(rows, idf, common, version, semantic=None, use_full_stem=False, use_local_rank=False):
    correct1 = correct3 = correct5 = usable = 0
    failures = []
    for row in rows:
        if row["answer"] not in row["paragraphs"]:
            continue
        usable += 1
        query = select_anchor_tokens(row, idf, common, version)
        ranker = rank_local if use_local_rank else rank
        if use_local_rank:
            ranking = ranker(
                row, expand_query(query, version), semantic,
                semantic_query=row["stem"] if use_full_stem else None,
            )
        else:
            ranking = ranker(
                row, expand_query(query, version), idf, semantic,
                semantic_query=row["stem"] if use_full_stem else None,
            )
        if ranking and ranking[0] == row["answer"]:
            correct1 += 1
        else:
            failures.append((row, query, ranking[:5]))
        if row["answer"] in ranking[:3]:
            correct3 += 1
        if row["answer"] in ranking[:5]:
            correct5 += 1
    return {"n": usable, "top1": correct1 / usable if usable else 0,
            "top3": correct3 / usable if usable else 0,
            "top5": correct5 / usable if usable else 0, "failures": failures}


def pct(value):
    return f"{value * 100:.1f}%"


def normalize_text(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def audit_answers(rows, idf, common):
    exact = near = mismatch = invalid_letter = 0
    semantic_flags = []
    structural_flags = []
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["year"], row["month"], row["set"])].append(row)
        answer = row["answer"]
        if answer not in row["paragraphs"]:
            invalid_letter += 1
            structural_flags.append((row, "answer letter missing from passage"))
            continue
        stored = normalize_text(row["answer_text"])
        actual = normalize_text(row["paragraphs"][answer])
        if stored == actual:
            exact += 1
        else:
            ratio = difflib.SequenceMatcher(None, stored, actual).ratio()
            if stored in actual or actual in stored or ratio >= 0.96:
                near += 1
            else:
                mismatch += 1
                structural_flags.append((row, f"answer_text mismatch ratio={ratio:.3f}"))
        query = select_anchor_tokens(row, idf, common, "v1")
        ranking = rank(row, query, idf)
        if answer not in ranking[:3]:
            semantic_flags.append((row, query, ranking[:3]))
    bad_sets = []
    for key, items in grouped.items():
        numbers = sorted(int(re.search(r"\d+", str(r["id"])).group()) for r in [])
        if len(items) != 10:
            bad_sets.append((key, len(items)))
    print("AUDIT_SUMMARY")
    print(f"labeled={len(rows)} exams={len(grouped)}")
    print(f"evidence_exact={exact} evidence_near={near} evidence_mismatch={mismatch} invalid_letter={invalid_letter}")
    print(f"structural_flags={len(structural_flags)} semantic_review_flags={len(semantic_flags)}")
    print(f"sets_with_non10_count={len(bad_sets)}")
    for row, reason in structural_flags[:30]:
        print(f"STRUCT {row['year']}-{row['month']:02d}-{row['set']} qid={row['id']} answer={row['answer']} {reason}")
    print("SEMANTIC_REVIEW")
    for row, query, ranking in semantic_flags:
        print(f"FLAG {row['year']}-{row['month']:02d}-{row['set']} qid={row['id']} answer={row['answer']} top3={','.join(ranking)}")
        print(f"  stem={row['stem']}")
        print(f"  assigned={row['paragraphs'].get(row['answer'], '')}")
        print(f"  anchors={' | '.join(query)}")
    return 0 if not structural_flags else 3


class SemanticIndex:
    """Unsupervised latent-semantic scorer fitted only on training text."""

    def __init__(self, rows):
        corpus = []
        for row in rows:
            corpus.append(row["stem"])
            corpus.extend(row["paragraphs"].values())
        self.vectorizer = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            min_df=2, max_df=0.9, sublinear_tf=True,
        )
        matrix = self.vectorizer.fit_transform(corpus)
        components = max(2, min(120, matrix.shape[0] - 1, matrix.shape[1] - 1))
        self.lsa = make_pipeline(TruncatedSVD(n_components=components, random_state=17), Normalizer(copy=False))
        self.lsa.fit(matrix)

    def encode(self, text):
        return self.lsa.transform(self.vectorizer.transform([text]))

    def similarity(self, left, right):
        return float(cosine_similarity(self.encode(left), self.encode(right))[0, 0])


class SurfaceIndex:
    """Word/character similarity for morphology and phrase-level overlap."""

    def __init__(self, rows):
        corpus = []
        for row in rows:
            corpus.append(row["stem"])
            corpus.extend(row["paragraphs"].values())
        self.word = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2),
            min_df=1, sublinear_tf=True,
        )
        self.char = TfidfVectorizer(
            lowercase=True, analyzer="char_wb", ngram_range=(3, 5),
            min_df=2, sublinear_tf=True,
        )
        self.word.fit(corpus)
        self.char.fit(corpus)

    def components(self, left, right):
        w = cosine_similarity(self.word.transform([left]), self.word.transform([right]))[0, 0]
        c = cosine_similarity(self.char.transform([left]), self.char.transform([right]))[0, 0]
        return float(w), float(c)

    def similarity(self, left, right):
        w, c = self.components(left, right)
        return float(0.65 * w + 0.35 * c)


class WindowSurfaceIndex:
    """Compare a stem with the best sentence or adjacent-sentence evidence window."""

    def __init__(self, rows):
        self.surface = SurfaceIndex(rows)

    @staticmethod
    def windows(text):
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])(?:[\"'’”])?\s+", text) if s.strip()]
        if not sentences:
            return [text]
        windows = list(sentences)
        windows.extend(sentences[i] + " " + sentences[i + 1] for i in range(len(sentences) - 1))
        return windows

    def similarity(self, left, right):
        whole = self.surface.similarity(left, right)
        local = max(self.surface.similarity(left, window) for window in self.windows(right))
        return 0.8 * local + 0.2 * whole


class CvSelectedSurfaceIndex(SurfaceIndex):
    """Surface scorer selected by passage-grouped cross-validation."""

    def similarity(self, left, right):
        word, char = self.components(left, right)
        return 0.8 * (0.5 * word + 0.5 * char)


class TranslationLexicon:
    """Learn recurring stem-to-evidence substitutions from training pairs only."""

    def __init__(self, rows):
        q_df = collections.Counter()
        p_df = collections.Counter()
        pair_df = collections.defaultdict(collections.Counter)
        usable = 0
        for row in rows:
            paragraph = row["paragraphs"].get(row["answer"], row["answer_text"])
            if not paragraph:
                continue
            usable += 1
            qs = {t for t in tokens(row["stem"]) if t not in STOP or t in LOGIC}
            ps = {t for t in tokens(paragraph) if t not in STOP or t in LOGIC}
            q_df.update(qs)
            p_df.update(ps)
            for qtok in qs:
                pair_df[qtok].update(ps)
        self.mapping = {}
        for qtok, associates in pair_df.items():
            ranked = []
            for ptok, cooc in associates.items():
                if ptok == qtok or cooc < 2:
                    continue
                pmi = math.log(((cooc + 0.25) * usable) / ((q_df[qtok] + 0.5) * (p_df[ptok] + 0.5)))
                if pmi >= 1.2:
                    ranked.append((pmi * math.log1p(cooc), ptok))
            ranked.sort(reverse=True)
            self.mapping[qtok] = [ptok for _, ptok in ranked[:4]]

    def expand(self, query):
        expanded = list(query)
        for token in query:
            expanded.extend(self.mapping.get(token, ()))
        return expanded


def passage_group(row):
    normalized = "\n".join(
        normalize_text(row["paragraphs"][letter]) for letter in sorted(row["paragraphs"])
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def local_candidate_features(row, query, surface):
    paragraph_tokens = {letter: tokens(text) for letter, text in row["paragraphs"].items()}
    n = max(len(paragraph_tokens), 1)
    df = collections.Counter(tok for toks in paragraph_tokens.values() for tok in set(toks))
    local_idf = {tok: math.log((n + 1) / (count + 0.5)) + 1 for tok, count in df.items()}
    q = collections.Counter(query)
    q_unique = set(query)
    q_numbers = {t for t in tokens(row["stem"]) if any(ch.isdigit() for ch in t)}
    q_logic = {t for t in tokens(row["stem"]) if t in LOGIC}
    q_proper = {
        stem(word) for word in re.findall(r"\b[A-Z][A-Za-z'-]+\b", row["stem"])
        if word.lower() not in {"the", "a", "an", "according", "one", "many", "some", "it"}
    }
    features = {}
    for letter, toks in paragraph_tokens.items():
        p = collections.Counter(toks)
        p_set = set(toks)
        matched = {tok for tok in q_unique if p[tok]}
        lexical = sum(local_idf.get(tok, 1.0) * (1 + math.log1p(p[tok])) * q[tok] for tok in matched)
        coverage = len(matched) / max(len(q_unique), 1)
        number_coverage = len(q_numbers & p_set) / max(len(q_numbers), 1) if q_numbers else 0.0
        logic_coverage = len(q_logic & p_set) / max(len(q_logic), 1) if q_logic else 0.0
        proper_coverage = len(q_proper & p_set) / max(len(q_proper), 1) if q_proper else 0.0
        word_cos, char_cos = surface.components(row["stem"], row["paragraphs"][letter])
        features[letter] = (lexical, coverage, word_cos, char_cos, number_coverage, logic_coverage, proper_coverage)
    return features


def metrics_from_rankings(rankings):
    n = len(rankings)
    return {
        "top1": sum(answer in ranking[:1] for answer, ranking in rankings) / n,
        "top3": sum(answer in ranking[:3] for answer, ranking in rankings) / n,
        "top5": sum(answer in ranking[:5] for answer, ranking in rankings) / n,
    }


def grouped_cross_validation(rows):
    groups = [passage_group(row) for row in rows]
    unique_groups = len(set(groups))
    splitter = GroupKFold(n_splits=min(6, unique_groups))
    cached = {"v1": [], "v2": [], "v11": [], "v12": [], "v13": [], "v14": []}
    for fold, (train_idx, valid_idx) in enumerate(splitter.split(rows, groups=groups), 1):
        train_rows = [rows[i] for i in train_idx]
        valid_rows = [rows[i] for i in valid_idx]
        idf = build_idf(train_rows)
        common = exam_common(rows)
        surface = SurfaceIndex(train_rows)
        for row in valid_rows:
            for anchor_version in ("v1", "v2", "v11", "v12", "v13", "v14"):
                query = select_anchor_tokens(row, idf, common, anchor_version)
                cached[anchor_version].append((row["answer"], local_candidate_features(row, query, surface)))
        print(f"CV_FOLD={fold} train={len(train_rows)} validation={len(valid_rows)}")

    grid = itertools.product(
        ("v1", "v2", "v11", "v12", "v13", "v14"),
        (0.0, 4.0, 8.0),
        (4.0, 8.0, 12.0, 16.0),
        (0.50, 0.65, 0.80),
        (0.0, 3.0),
        (0.0, 3.0),
        (0.0, 3.0),
    )
    results = []
    for params in grid:
        anchor_version, coverage_w, surface_w, word_mix, number_w, logic_w, proper_w = params
        rankings = []
        for answer, candidate_features in cached[anchor_version]:
            scored = []
            for letter, feature in candidate_features.items():
                lexical, coverage, word_cos, char_cos, number_cov, logic_cov, proper_cov = feature
                score = (
                    lexical
                    + coverage_w * coverage
                    + surface_w * (word_mix * word_cos + (1 - word_mix) * char_cos)
                    + number_w * number_cov
                    + logic_w * logic_cov
                    + proper_w * proper_cov
                )
                scored.append((score, letter))
            scored.sort(key=lambda item: (-item[0], item[1]))
            rankings.append((answer, [letter for _, letter in scored]))
        metric = metrics_from_rankings(rankings)
        results.append((metric["top1"], metric["top3"], metric["top5"], params))
    results.sort(reverse=True)
    print(f"CV_ROWS={len(rows)} UNIQUE_PASSAGES={unique_groups}")
    for top1, top3, top5, params in results[:10]:
        print(
            f"CV top1={pct(top1)} top3={pct(top3)} top5={pct(top5)} "
            f"params={params}"
        )
    for anchor_version in ("v1", "v2", "v11", "v12", "v13", "v14"):
        best = next(result for result in results if result[3][0] == anchor_version)
        top1, top3, top5, params = best
        print(
            f"CV_BEST_{anchor_version} top1={pct(top1)} top3={pct(top3)} "
            f"top5={pct(top5)} params={params}"
        )
        recall_best = max(
            (result for result in results if result[3][0] == anchor_version),
            key=lambda result: (result[2], result[1], result[0]),
        )
        r_top1, r_top3, r_top5, r_params = recall_best
        print(
            f"CV_RECALL_{anchor_version} top1={pct(r_top1)} top3={pct(r_top3)} "
            f"top5={pct(r_top5)} params={r_params}"
        )
    return 0


def main():
    rows = load_rows()
    if "--cv" in sys.argv:
        return grouped_cross_validation(rows)
    train = [r for r in rows if r["year"] <= 2023]
    valid = [r for r in rows if r["year"] == 2024]
    test = [r for r in rows if r["year"] >= 2025]
    idf = build_idf(train)
    common = exam_common(rows)
    if "--audit" in sys.argv:
        return audit_answers(rows, idf, common)
    semantic = SemanticIndex(train)
    surface = SurfaceIndex(train)
    window_surface = WindowSurfaceIndex(train)
    cv_surface = CvSelectedSurfaceIndex(train)
    lexicon = TranslationLexicon(train)
    print(f"rows={len(rows)} train={len(train)} validation={len(valid)} test={len(test)}")
    if "--v11" in sys.argv:
        span_counts = collections.Counter()
        violations = []
        for row in rows:
            spans, _ = select_anchor_spans(row, idf, common)
            span_counts[len(spans)] += 1
            for phrase in spans:
                count = len(TOKEN_RE.findall(phrase))
                if not 1 <= count <= 3:
                    violations.append((row["id"], phrase, count))
        for name, split in (("train", train), ("validation", valid), ("test", test)):
            result = evaluate(split, idf, common, "v11", cv_surface, True, True)
            print(
                f"v11 {name} top1={pct(result['top1'])} "
                f"top3={pct(result['top3'])} top5={pct(result['top5'])} n={result['n']}"
            )
        print(f"SPAN_COUNTS={dict(sorted(span_counts.items()))}")
        print(f"SPAN_VIOLATIONS={len(violations)}")
        for row in [r for r in rows if r["year"] == 2026 and r["month"] == 6 and r["set"] == 1]:
            spans, _ = select_anchor_spans(row, idf, common)
            print(f"EXAMPLE qid={row['id']} spans={' | '.join(spans)}")
        return 0 if not violations else 2
    if "--v12" in sys.argv:
        anchor_counts = collections.Counter()
        violations = []
        for row in rows:
            spans, _ = select_anchor_singletons(row, idf, common)
            anchor_counts[len(spans)] += 1
            for word in spans:
                count = len(TOKEN_RE.findall(word))
                if count != 1:
                    violations.append((row["id"], word, count))
        for name, split in (("train", train), ("validation", valid), ("test", test)):
            result = evaluate(split, idf, common, "v12", cv_surface, True, True)
            print(
                f"v12 {name} top1={pct(result['top1'])} "
                f"top3={pct(result['top3'])} top5={pct(result['top5'])} n={result['n']}"
            )
        print(f"ANCHOR_COUNTS={dict(sorted(anchor_counts.items()))}")
        print(f"ANCHOR_VIOLATIONS={len(violations)}")
        for row in [r for r in rows if r["year"] == 2026 and r["month"] == 6 and r["set"] == 1]:
            spans, _ = select_anchor_singletons(row, idf, common)
            print(f"EXAMPLE qid={row['id']} anchors={' | '.join(spans)}")
        return 0 if not violations else 2
    if "--v13" in sys.argv:
        violations = []
        for row in rows:
            spans, _ = select_anchor_spans(row, idf, common, max_spans=2)
            if len(spans) != 2:
                violations.append((row["id"], "anchor_count", len(spans)))
            for phrase in spans:
                count = len(TOKEN_RE.findall(phrase))
                if not 1 <= count <= 3:
                    violations.append((row["id"], phrase, count))
        for name, split in (("train", train), ("validation", valid), ("test", test)):
            result = evaluate(split, idf, common, "v13", cv_surface, True, True)
            print(
                f"v13 {name} top1={pct(result['top1'])} "
                f"top3={pct(result['top3'])} top5={pct(result['top5'])} n={result['n']}"
            )
        print(f"FORMAT_VIOLATIONS={len(violations)}")
        for row in [r for r in rows if r["year"] == 2026 and r["month"] == 6 and r["set"] == 1]:
            spans, _ = select_anchor_spans(row, idf, common, max_spans=2)
            primary = spans[0] if spans else ""
            secondary = spans[1] if len(spans) > 1 else ""
            print(f"EXAMPLE qid={row['id']} primary={primary} secondary={secondary}")
        return 0 if not violations else 2
    if "--v14" in sys.argv:
        violations = []
        counts = collections.Counter()
        for row in rows:
            spans, _ = select_anchor_spans(row, idf, common, max_spans=3)
            counts[len(spans)] += 1
            if not 1 <= len(spans) <= 3:
                violations.append((row["id"], "anchor_count", len(spans)))
            for phrase in spans:
                count = len(TOKEN_RE.findall(phrase))
                if not 1 <= count <= 3:
                    violations.append((row["id"], phrase, count))
        for name, split in (("train", train), ("validation", valid), ("test", test)):
            result = evaluate(split, idf, common, "v14", cv_surface, True, True)
            print(
                f"v14 {name} top1={pct(result['top1'])} "
                f"top3={pct(result['top3'])} top5={pct(result['top5'])} n={result['n']}"
            )
        print(f"ANCHOR_COUNTS={dict(sorted(counts.items()))}")
        print(f"FORMAT_VIOLATIONS={len(violations)}")
        return 0 if not violations else 2
    selected = None
    for version in ("v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "v10", "v11", "v12", "v13", "v14"):
        base_version = "v2" if version == "v3" else version
        scorer = semantic if version == "v3" else None
        if version == "v5":
            base_version = "v2"
            scorer = surface
        use_full_stem = version == "v6"
        if version == "v6":
            base_version = "v2"
            scorer = surface
        if version == "v7":
            base_version = "v2"
            scorer = window_surface
            use_full_stem = True
        use_local_rank = version in {"v8", "v9"}
        if version == "v8":
            base_version = "v1"
            scorer = None
        if version == "v9":
            base_version = "v2"
            scorer = surface
            use_full_stem = True
        if version == "v10":
            base_version = "v2"
            scorer = cv_surface
            use_full_stem = True
            use_local_rank = True
        if version == "v11":
            base_version = "v11"
            scorer = cv_surface
            use_full_stem = True
            use_local_rank = True
        if version == "v12":
            base_version = "v12"
            scorer = cv_surface
            use_full_stem = True
            use_local_rank = True
        if version == "v13":
            base_version = "v13"
            scorer = cv_surface
            use_full_stem = True
            use_local_rank = True
        if version == "v14":
            base_version = "v14"
            scorer = cv_surface
            use_full_stem = True
            use_local_rank = True
        if version == "v4":
            original_expand = expand_query
            def learned_expand(query, _version):
                return lexicon.expand(original_expand(query, "v2"))
            globals()["expand_query"] = learned_expand
            base_version = "v2"
        tr = evaluate(train, idf, common, base_version, scorer, use_full_stem, use_local_rank)
        va = evaluate(valid, idf, common, base_version, scorer, use_full_stem, use_local_rank)
        if version == "v4":
            globals()["expand_query"] = original_expand
        print(f"{version} train top1={pct(tr['top1'])} top3={pct(tr['top3'])} top5={pct(tr['top5'])}")
        print(f"{version} validation top1={pct(va['top1'])} top3={pct(va['top3'])} top5={pct(va['top5'])}")
        if selected is None or (va["top1"], va["top5"], va["top3"]) > (
            selected[1]["top1"], selected[1]["top5"], selected[1]["top3"]
        ):
            selected = (version, va)
    version = selected[0]
    base_version = "v2" if version == "v3" else version
    scorer = semantic if version == "v3" else None
    if version == "v5":
        base_version = "v2"
        scorer = surface
    use_full_stem = version == "v6"
    if version == "v6":
        base_version = "v2"
        scorer = surface
    if version == "v7":
        base_version = "v2"
        scorer = window_surface
        use_full_stem = True
    use_local_rank = version in {"v8", "v9"}
    if version == "v8":
        base_version = "v1"
        scorer = None
    if version == "v9":
        base_version = "v2"
        scorer = surface
        use_full_stem = True
    if version == "v10":
        base_version = "v2"
        scorer = cv_surface
        use_full_stem = True
        use_local_rank = True
    if version == "v11":
        base_version = "v11"
        scorer = cv_surface
        use_full_stem = True
        use_local_rank = True
    if version == "v12":
        base_version = "v12"
        scorer = cv_surface
        use_full_stem = True
        use_local_rank = True
    if version == "v13":
        base_version = "v13"
        scorer = cv_surface
        use_full_stem = True
        use_local_rank = True
    if version == "v14":
        base_version = "v14"
        scorer = cv_surface
        use_full_stem = True
        use_local_rank = True
    if version == "v4":
        original_expand = expand_query
        def learned_expand(query, _version):
            return lexicon.expand(original_expand(query, "v2"))
        globals()["expand_query"] = learned_expand
        base_version = "v2"
    te = evaluate(test, idf, common, base_version, scorer, use_full_stem, use_local_rank)
    if version == "v4":
        globals()["expand_query"] = original_expand
    print(f"selected={version}")
    print(f"test top1={pct(te['top1'])} top3={pct(te['top3'])} top5={pct(te['top5'])} n={te['n']}")
    print("sample_failures:")
    for row, query, ranking in te["failures"]:
        print(f"{row['year']}-{row['month']:02d}-{row['set']} qid={row['id']} answer={row['answer']} top5={','.join(ranking)}")
        print(f"  stem={row['stem']}")
        print(f"  anchors={' | '.join(query)}")
    anchor_status = "PASS" if te["top5"] >= 0.95 else "ITERATE"
    auto_status = "PASS" if te["top1"] >= 0.85 else "REJECT"
    print(f"ANCHOR_RECALL_STATUS={anchor_status}")
    print(f"AUTO_SELECTION_STATUS={auto_status}")
    return 0 if anchor_status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
