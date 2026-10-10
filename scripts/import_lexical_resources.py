#!/usr/bin/env python3
"""Normalize and import the pinned Match-Root and dict CET-4 resources.

The upstream repositories currently declare no license.  Raw and normalized
data therefore remain local/ignored; only provenance and importer code belong
in version control.  The script never executes third-party project code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MATCH_ROOT = ROOT / "data" / "external-sources" / "Match-Root"
DICT_ROOT = ROOT / "data" / "external-sources" / "dict"
NORMALIZED = ROOT / "data" / "lexical" / "normalized"

SOURCES = {
    "Match-Root": {
        "url": "https://github.com/lnkDrop/Match-Root.git",
        "expected_commit": "103df58c17f5600968f8e05c88fc997c50e15dff",
        "path": MATCH_ROOT,
    },
    "kajweb-dict": {
        "url": "https://github.com/kajweb/dict.git",
        "expected_commit": "3992bcb94c800a2fd38a9fd6ff95b2353e755363",
        "path": DICT_ROOT,
    },
}


def mysql(sql: str) -> list[list[str]]:
    command = [
        "docker", "exec", "-i", "cet4_mysql", "sh", "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --default-character-set=utf8mb4 -N -B -uroot cet4',
    ]
    result = subprocess.run(
        command,
        input=sql,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"mysql exited with {result.returncode}")
    return [line.split("\t") for line in result.stdout.splitlines() if line]


def sql_quote(value: object | None) -> str:
    if value is None:
        return "NULL"
    string = str(value).replace("\\", "\\\\").replace("'", "''")
    return "'" + string + "'"


def norm_word(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().lower()
    return re.sub(r"\s+", " ", value)


def digest(*values: object) -> str:
    raw = "\x1f".join("" if value is None else str(value) for value in values)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def git_commit(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    ).stdout.strip()


def add_word(words: dict[str, dict], word: str, **fields: str) -> str:
    normalized = norm_word(word)
    if not normalized:
        return ""
    row = words.setdefault(
        normalized,
        {
            "normalized_word": normalized,
            "display_word": word.strip(),
            "uk_phone": "",
            "us_phone": "",
            "phone": "",
            "translation_text": "",
        },
    )
    for key, value in fields.items():
        if value and not row.get(key):
            row[key] = value.strip()
    return normalized


def nested_rows(content: dict, section: str, field: str) -> list:
    value = content.get(section, {})
    if isinstance(value, dict):
        value = value.get(field, [])
    return value if isinstance(value, list) else []


def parse_dict_archives(data: dict) -> None:
    archives = sorted((DICT_ROOT / "book").glob("*CET4*.zip"))
    for archive in archives:
        with zipfile.ZipFile(archive) as package:
            members = [name for name in package.namelist() if name.lower().endswith(".json")]
            if len(members) != 1:
                raise RuntimeError(f"Unexpected archive members: {archive}: {members}")
            with package.open(members[0]) as handle:
                for raw_line in handle:
                    if not raw_line.strip():
                        continue
                    record = json.loads(raw_line)
                    book_id = str(record.get("bookId") or Path(members[0]).stem)
                    head = str(record.get("headWord") or "").strip()
                    payload = record.get("content", {}).get("word", {})
                    content = payload.get("content", {}) if isinstance(payload, dict) else {}
                    translations = nested_rows(content, "trans", "trans")
                    translation_text = "; ".join(
                        filter(None, [str(item.get("pos", "")).strip() + ". " + str(item.get("tran", "")).strip() for item in translations])
                    )
                    normalized = add_word(
                        data["words"],
                        head,
                        uk_phone=str(content.get("ukphone", "")),
                        us_phone=str(content.get("usphone", "")),
                        phone=str(content.get("phone", "")),
                        translation_text=translation_text,
                    )
                    if not normalized:
                        continue
                    data["memberships"].append(
                        {
                            "word": normalized,
                            "source": "kajweb-dict",
                            "book_id": book_id,
                            "word_rank": int(record.get("wordRank") or 0),
                            "raw_word_id": str(payload.get("wordId", "")),
                        }
                    )
                    for item in translations:
                        data["translations"].append(
                            {
                                "word": normalized,
                                "source": "kajweb-dict",
                                "pos": str(item.get("pos", "")),
                                "translation": str(item.get("tran", "")),
                            }
                        )
                    for kind, key in (("general", "sentence"), ("real_exam", "realExamSentence")):
                        for item in nested_rows(content, key, "sentences"):
                            metadata = item.get("sourceInfo", {}) if kind == "real_exam" else {}
                            data["examples"].append(
                                {
                                    "word": normalized,
                                    "source": "kajweb-dict",
                                    "kind": kind,
                                    "example_en": str(item.get("sContent", "")),
                                    "example_cn": str(item.get("sCn", "")),
                                    "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                                }
                            )
                    for group in nested_rows(content, "syno", "synos"):
                        for item in group.get("hwds", []) or []:
                            data["synonyms"].append(
                                {
                                    "word": normalized,
                                    "source": "kajweb-dict",
                                    "pos": str(group.get("pos", "")),
                                    "sense": str(group.get("tran", "")),
                                    "synonym": str(item.get("w", "")),
                                }
                            )
                    for item in nested_rows(content, "phrase", "phrases"):
                        data["phrases"].append(
                            {
                                "word": normalized,
                                "source": "kajweb-dict",
                                "phrase_en": str(item.get("pContent", "")),
                                "phrase_cn": str(item.get("pCn", "")),
                            }
                        )
                    for group in nested_rows(content, "relWord", "rels"):
                        for item in group.get("words", []) or []:
                            data["relations"].append(
                                {
                                    "word": normalized,
                                    "source": "kajweb-dict",
                                    "pos": str(group.get("pos", "")),
                                    "related_word": str(item.get("hwd", "")),
                                    "translation": str(item.get("tran", "")),
                                }
                            )


def read_csv(path: Path, encoding: str) -> list[dict[str, str]]:
    with path.open("r", encoding=encoding, newline="") as handle:
        return list(csv.DictReader(handle))


def split_morpheme(value: str) -> tuple[str, str]:
    value = " ".join(value.split())
    if not value:
        return "", ""
    bits = value.split(" ", 1)
    return bits[0], bits[1] if len(bits) > 1 else ""


def parse_match_root(data: dict) -> None:
    folder = MATCH_ROOT / "data"
    vocab_rows = read_csv(folder / "四六级单词.csv", "gb18030")
    for index, row in enumerate(vocab_rows, 1):
        word = row.get("四六级合并词汇", "")
        definition = row.get("Unnamed: 1", "")
        level = row.get("Unnamed: 2", "")
        normalized = add_word(data["words"], word, translation_text=definition)
        if normalized:
            data["memberships"].append(
                {
                    "word": normalized,
                    "source": "Match-Root",
                    "book_id": level or "四六级合并词汇",
                    "word_rank": index,
                    "raw_word_id": str(index),
                }
            )
    configs = [
        ("cigen.csv", "root", "词根", "释义"),
        ("qianzhui.csv", "prefix", "前缀", "单词释义"),
        ("houzhui.csv", "suffix", "后缀", "单词释义"),
    ]
    for filename, kind, value_column, definition_column in configs:
        for index, row in enumerate(read_csv(folder / filename, "utf-8"), 1):
            word = row.get("单词", "")
            normalized = add_word(data["words"], word, translation_text=row.get(definition_column, ""))
            form, meaning = split_morpheme(row.get(value_column, ""))
            if normalized and form:
                data["morphemes"].append(
                    {
                        "source": "Match-Root",
                        "word": normalized,
                        "kind": kind,
                        "morpheme": form,
                        "meaning": meaning,
                        "word_definition": row.get(definition_column, ""),
                        "source_row": index,
                    }
                )
    for index, row in enumerate(read_csv(folder / "cipin.csv", "utf-8"), 1):
        normalized = add_word(data["words"], row.get("单词", ""), translation_text=row.get("单词释义", ""))
        if normalized:
            data["frequencies"].append(
                {
                    "source": "Match-Root",
                    "word": normalized,
                    "frequency": int(float(row.get("词频", "0") or 0)),
                    "word_definition": row.get("单词释义", ""),
                    "source_row": index,
                }
            )


def dedupe(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    result = {}
    for row in rows:
        row_hash = digest(*(row.get(key, "") for key in keys))
        result[row_hash] = {**row, "row_hash": row_hash}
    return list(result.values())


def build_data() -> dict:
    data = {
        "words": {}, "memberships": [], "translations": [], "examples": [],
        "synonyms": [], "phrases": [], "relations": [], "morphemes": [], "frequencies": [],
    }
    parse_dict_archives(data)
    parse_match_root(data)
    key_map = {
        "memberships": ("word", "source", "book_id"),
        "translations": ("word", "source", "pos", "translation"),
        "examples": ("word", "source", "kind", "example_en", "example_cn", "metadata_json"),
        "synonyms": ("word", "source", "pos", "sense", "synonym"),
        "phrases": ("word", "source", "phrase_en", "phrase_cn"),
        "relations": ("word", "source", "pos", "related_word", "translation"),
        "morphemes": ("source", "word", "kind", "morpheme", "meaning", "source_row"),
        "frequencies": ("source", "word"),
    }
    for name, keys in key_map.items():
        data[name] = dedupe(data[name], keys)
    return data


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS lexical_sources (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, source_name VARCHAR(80) NOT NULL,
 repository_url VARCHAR(500) NOT NULL, commit_sha CHAR(40) NOT NULL,
 license_status VARCHAR(40) NOT NULL, metadata_json JSON NOT NULL,
 imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(id), UNIQUE KEY uq_lexical_source(source_name,commit_sha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_words (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, normalized_word VARCHAR(191) NOT NULL,
 display_word VARCHAR(255) NOT NULL, uk_phone VARCHAR(255) NOT NULL,
 us_phone VARCHAR(255) NOT NULL, phone VARCHAR(255) NOT NULL,
 translation_text TEXT NOT NULL, PRIMARY KEY(id), UNIQUE KEY uq_vocab_word(normalized_word)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_memberships (
 word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 book_id VARCHAR(100) NOT NULL, word_rank INT NOT NULL, raw_word_id VARCHAR(100) NOT NULL,
 PRIMARY KEY(word_id,source_id,book_id), CONSTRAINT fk_vm_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_vm_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_translations (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 pos VARCHAR(50) NOT NULL, translation TEXT NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uq_vt_hash(row_hash), KEY idx_vt_word(word_id),
 CONSTRAINT fk_vt_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_vt_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_examples (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 example_kind VARCHAR(30) NOT NULL, example_en TEXT NOT NULL, example_cn TEXT NOT NULL,
 metadata_json JSON NOT NULL, row_hash CHAR(64) NOT NULL, PRIMARY KEY(id), UNIQUE KEY uq_ve_hash(row_hash), KEY idx_ve_word(word_id),
 CONSTRAINT fk_ve_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_ve_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_synonyms (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 pos VARCHAR(50) NOT NULL, sense TEXT NOT NULL, synonym VARCHAR(255) NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uq_vs_hash(row_hash), KEY idx_vs_word(word_id),
 CONSTRAINT fk_vs_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_vs_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_phrases (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 phrase_en TEXT NOT NULL, phrase_cn TEXT NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uq_vp_hash(row_hash), KEY idx_vp_word(word_id),
 CONSTRAINT fk_vp_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_vp_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS vocabulary_relations (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 pos VARCHAR(50) NOT NULL, related_word VARCHAR(255) NOT NULL, translation TEXT NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uq_vr_hash(row_hash), KEY idx_vr_word(word_id),
 CONSTRAINT fk_vr_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_vr_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS word_morpheme_matches (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT, word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL,
 match_kind ENUM('root','prefix','suffix') NOT NULL, morpheme VARCHAR(191) NOT NULL,
 meaning TEXT NOT NULL, word_definition TEXT NOT NULL, source_row INT NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(id), UNIQUE KEY uq_wmm_hash(row_hash), KEY idx_wmm_word(word_id), KEY idx_wmm_form(match_kind,morpheme),
 CONSTRAINT fk_wmm_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_wmm_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS word_frequencies (
 word_id BIGINT UNSIGNED NOT NULL, source_id BIGINT UNSIGNED NOT NULL, frequency INT NOT NULL,
 word_definition TEXT NOT NULL, source_row INT NOT NULL, row_hash CHAR(64) NOT NULL,
 PRIMARY KEY(word_id,source_id), UNIQUE KEY uq_wf_hash(row_hash),
 CONSTRAINT fk_wf_word FOREIGN KEY(word_id) REFERENCES vocabulary_words(id) ON DELETE CASCADE,
 CONSTRAINT fk_wf_source FOREIGN KEY(source_id) REFERENCES lexical_sources(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


def insert_chunks(table: str, columns: list[str], rows: list[list[object]], *, suffix: str = "", chunk_size: int = 500) -> None:
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        values = ",\n".join("(" + ",".join(sql_quote(value) for value in row) + ")" for row in chunk)
        mysql(f"INSERT INTO {table}({','.join(columns)}) VALUES {values} {suffix};")


def export_jsonl(data: dict) -> None:
    NORMALIZED.mkdir(parents=True, exist_ok=True)
    for name, value in data.items():
        path = NORMALIZED / f"{name}.jsonl"
        rows = value.values() if isinstance(value, dict) else value
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def apply_data(data: dict, commits: dict[str, str]) -> None:
    mysql(SCHEMA)
    source_rows = []
    for name, info in SOURCES.items():
        metadata = json.dumps({"expected_commit": info["expected_commit"]}, ensure_ascii=False)
        source_rows.append([name, info["url"], commits[name], "not_declared", metadata])
    insert_chunks(
        "lexical_sources",
        ["source_name", "repository_url", "commit_sha", "license_status", "metadata_json"],
        source_rows,
        suffix=("ON DUPLICATE KEY UPDATE repository_url=VALUES(repository_url),"
                "license_status=VALUES(license_status),metadata_json=VALUES(metadata_json)"),
    )
    word_rows = [
        [row["normalized_word"], row["display_word"], row["uk_phone"], row["us_phone"], row["phone"], row["translation_text"]]
        for row in data["words"].values()
    ]
    insert_chunks(
        "vocabulary_words",
        ["normalized_word", "display_word", "uk_phone", "us_phone", "phone", "translation_text"],
        word_rows,
        suffix=("ON DUPLICATE KEY UPDATE display_word=VALUES(display_word),"
                "uk_phone=IF(uk_phone='',VALUES(uk_phone),uk_phone),"
                "us_phone=IF(us_phone='',VALUES(us_phone),us_phone),"
                "phone=IF(phone='',VALUES(phone),phone),"
                "translation_text=IF(translation_text='',VALUES(translation_text),translation_text)"),
    )
    source_ids = {name: int(sid) for sid, name in mysql("SELECT id,source_name FROM lexical_sources;")}
    word_ids = {word: int(wid) for wid, word in mysql("SELECT id,normalized_word FROM vocabulary_words;")}

    def ids(row: dict) -> tuple[int, int]:
        return word_ids[row["word"]], source_ids[row["source"]]

    insert_chunks("vocabulary_memberships", ["word_id", "source_id", "book_id", "word_rank", "raw_word_id"],
                  [[*ids(r), r["book_id"], r["word_rank"], r["raw_word_id"]] for r in data["memberships"]],
                  suffix="ON DUPLICATE KEY UPDATE word_rank=VALUES(word_rank),raw_word_id=VALUES(raw_word_id)")
    insert_chunks("vocabulary_translations", ["word_id", "source_id", "pos", "translation", "row_hash"],
                  [[*ids(r), r["pos"], r["translation"], r["row_hash"]] for r in data["translations"]], suffix="ON DUPLICATE KEY UPDATE translation=VALUES(translation)")
    insert_chunks("vocabulary_examples", ["word_id", "source_id", "example_kind", "example_en", "example_cn", "metadata_json", "row_hash"],
                  [[*ids(r), r["kind"], r["example_en"], r["example_cn"], r["metadata_json"], r["row_hash"]] for r in data["examples"]], suffix="ON DUPLICATE KEY UPDATE example_en=VALUES(example_en)", chunk_size=200)
    insert_chunks("vocabulary_synonyms", ["word_id", "source_id", "pos", "sense", "synonym", "row_hash"],
                  [[*ids(r), r["pos"], r["sense"], r["synonym"], r["row_hash"]] for r in data["synonyms"]], suffix="ON DUPLICATE KEY UPDATE synonym=VALUES(synonym)")
    insert_chunks("vocabulary_phrases", ["word_id", "source_id", "phrase_en", "phrase_cn", "row_hash"],
                  [[*ids(r), r["phrase_en"], r["phrase_cn"], r["row_hash"]] for r in data["phrases"]], suffix="ON DUPLICATE KEY UPDATE phrase_en=VALUES(phrase_en)")
    insert_chunks("vocabulary_relations", ["word_id", "source_id", "pos", "related_word", "translation", "row_hash"],
                  [[*ids(r), r["pos"], r["related_word"], r["translation"], r["row_hash"]] for r in data["relations"]], suffix="ON DUPLICATE KEY UPDATE related_word=VALUES(related_word)")
    insert_chunks("word_morpheme_matches", ["word_id", "source_id", "match_kind", "morpheme", "meaning", "word_definition", "source_row", "row_hash"],
                  [[*ids(r), r["kind"], r["morpheme"], r["meaning"], r["word_definition"], r["source_row"], r["row_hash"]] for r in data["morphemes"]], suffix="ON DUPLICATE KEY UPDATE meaning=VALUES(meaning)")
    insert_chunks("word_frequencies", ["word_id", "source_id", "frequency", "word_definition", "source_row", "row_hash"],
                  [[*ids(r), r["frequency"], r["word_definition"], r["source_row"], r["row_hash"]] for r in data["frequencies"]], suffix="ON DUPLICATE KEY UPDATE frequency=VALUES(frequency),word_definition=VALUES(word_definition)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--export-data", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commits = {}
    for name, info in SOURCES.items():
        commit = git_commit(info["path"])
        if commit != info["expected_commit"]:
            raise RuntimeError(f"{name} commit changed: expected {info['expected_commit']}, found {commit}")
        commits[name] = commit
    data = build_data()
    summary = {"commits": commits, **{name: len(value) for name, value in data.items()}}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.export_data:
        export_jsonl(data)
        print(f"EXPORTED={NORMALIZED}")
    if args.apply:
        apply_data(data, commits)
        print("APPLIED=1")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
