#!/usr/bin/env python3
"""Evaluate paragraph-matching anchor extraction against the authorized CET corpus.

The extractor never uses answers. Answer letters are used only after extraction to
score whether the selected anchors retrieve the correct paragraph.
"""

from __future__ import annotations

import collections
import difflib
import math
import re
import subprocess
import sys

from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer


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


def select_anchor_tokens(row, idf, common, version):
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


def evaluate(rows, idf, common, version, semantic=None, use_full_stem=False):
    correct1 = correct3 = correct5 = usable = 0
    failures = []
    for row in rows:
        if row["answer"] not in row["paragraphs"]:
            continue
        usable += 1
        query = select_anchor_tokens(row, idf, common, version)
        ranking = rank(
            row, expand_query(query, version), idf, semantic,
            semantic_query=row["stem"] if use_full_stem else None,
        )
        if ranking and ranking[0] == row["answer"]:
            correct1 += 1
        else:
            failures.append((row, query, ranking[:3]))
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

    def similarity(self, left, right):
        w = cosine_similarity(self.word.transform([left]), self.word.transform([right]))[0, 0]
        c = cosine_similarity(self.char.transform([left]), self.char.transform([right]))[0, 0]
        return float(0.65 * w + 0.35 * c)


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


def main():
    rows = load_rows()
    train = [r for r in rows if r["year"] <= 2023]
    valid = [r for r in rows if r["year"] == 2024]
    test = [r for r in rows if r["year"] >= 2025]
    idf = build_idf(train)
    common = exam_common(rows)
    if "--audit" in sys.argv:
        return audit_answers(rows, idf, common)
    semantic = SemanticIndex(train)
    surface = SurfaceIndex(train)
    lexicon = TranslationLexicon(train)
    print(f"rows={len(rows)} train={len(train)} validation={len(valid)} test={len(test)}")
    selected = None
    for version in ("v1", "v2", "v3", "v4", "v5", "v6"):
        base_version = "v2" if version == "v3" else version
        scorer = semantic if version == "v3" else None
        if version == "v5":
            base_version = "v2"
            scorer = surface
        use_full_stem = version == "v6"
        if version == "v6":
            base_version = "v2"
            scorer = surface
        if version == "v4":
            original_expand = expand_query
            def learned_expand(query, _version):
                return lexicon.expand(original_expand(query, "v2"))
            globals()["expand_query"] = learned_expand
            base_version = "v2"
        tr = evaluate(train, idf, common, base_version, scorer, use_full_stem)
        va = evaluate(valid, idf, common, base_version, scorer, use_full_stem)
        if version == "v4":
            globals()["expand_query"] = original_expand
        print(f"{version} train top1={pct(tr['top1'])} top3={pct(tr['top3'])} top5={pct(tr['top5'])}")
        print(f"{version} validation top1={pct(va['top1'])} top3={pct(va['top3'])} top5={pct(va['top5'])}")
        if selected is None or (va["top3"], va["top1"]) > (selected[1]["top3"], selected[1]["top1"]):
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
    if version == "v4":
        original_expand = expand_query
        def learned_expand(query, _version):
            return lexicon.expand(original_expand(query, "v2"))
        globals()["expand_query"] = learned_expand
        base_version = "v2"
    te = evaluate(test, idf, common, base_version, scorer, use_full_stem)
    if version == "v4":
        globals()["expand_query"] = original_expand
    print(f"selected={version}")
    print(f"test top1={pct(te['top1'])} top3={pct(te['top3'])} top5={pct(te['top5'])} n={te['n']}")
    print("sample_failures:")
    for row, query, ranking in te["failures"][:12]:
        print(f"{row['year']}-{row['month']:02d}-{row['set']} qid={row['id']} answer={row['answer']} top3={','.join(ranking)}")
        print(f"  stem={row['stem']}")
        print(f"  anchors={' | '.join(query)}")
    anchor_status = "PASS" if te["top5"] >= 0.95 else "ITERATE"
    auto_status = "PASS" if te["top1"] >= 0.85 else "REJECT"
    print(f"ANCHOR_RECALL_STATUS={anchor_status}")
    print(f"AUTO_SELECTION_STATUS={auto_status}")
    return 0 if anchor_status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
