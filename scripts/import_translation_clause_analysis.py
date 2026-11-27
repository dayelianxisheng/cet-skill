#!/usr/bin/env python3
"""Import derived CET translation clause annotations into the Docker MySQL DB.

The source table ``translation_prompts`` is never modified.  This script owns
only ``translation_clause_analysis`` and two read-only frequency views.
"""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis" / "translation_clause_annotations.tsv"
CONTAINER = "cet4-mysql"


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def tag_json(value: str) -> str:
    tags = [item.strip() for item in value.split(";") if item.strip()]
    return json.dumps(tags, ensure_ascii=False)


def load_rows() -> list[dict[str, str]]:
    with SOURCE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise SystemExit("annotation file is empty")
    prompt_ids = {int(row["prompt_id"]) for row in rows}
    expected = set(range(1, 43)) - {38}
    if prompt_ids != expected:
        raise SystemExit(
            f"prompt coverage mismatch: missing={sorted(expected - prompt_ids)}, "
            f"unexpected={sorted(prompt_ids - expected)}"
        )
    return rows


def build_sql(rows: list[dict[str, str]]) -> str:
    values = []
    for row in rows:
        values.append(
            "(" + ",".join(
                [
                    row["prompt_id"],
                    row["unit"],
                    sql_string(row["exam"]),
                    row["set_number"],
                    sql_string(row["zh_clause"]),
                    sql_string(row["zh_backbone"]),
                    sql_string(row["en_phrase"]),
                    sql_string(tag_json(row["pattern"])),
                    sql_string(tag_json(row["theme"])),
                ]
            ) + ")"
        )

    prompt_ids = ",".join(str(value) for value in sorted({int(r["prompt_id"]) for r in rows}))
    return f"""
SET NAMES utf8mb4;
CREATE TABLE IF NOT EXISTS translation_clause_analysis (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  translation_prompt_id BIGINT UNSIGNED NOT NULL,
  clause_order SMALLINT UNSIGNED NOT NULL,
  exam_label VARCHAR(10) NOT NULL,
  set_number TINYINT UNSIGNED NOT NULL,
  zh_clause TEXT NOT NULL,
  zh_backbone VARCHAR(255) NOT NULL,
  en_phrase VARCHAR(500) NOT NULL,
  pattern_tags JSON NOT NULL,
  theme_tags JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_translation_clause (translation_prompt_id, clause_order),
  KEY idx_translation_clause_exam (exam_label, set_number),
  CONSTRAINT fk_clause_translation_prompt
    FOREIGN KEY (translation_prompt_id) REFERENCES translation_prompts(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;
DELETE FROM translation_clause_analysis
WHERE translation_prompt_id IN ({prompt_ids});
INSERT INTO translation_clause_analysis
  (translation_prompt_id, clause_order, exam_label, set_number,
   zh_clause, zh_backbone, en_phrase, pattern_tags, theme_tags)
VALUES
{','.join(values)};
COMMIT;

CREATE OR REPLACE VIEW translation_pattern_frequency AS
SELECT tag_table.tag, COUNT(*) AS frequency
FROM translation_clause_analysis AS a
JOIN JSON_TABLE(
  a.pattern_tags,
  '$[*]' COLUMNS(tag VARCHAR(100) PATH '$')
) AS tag_table
GROUP BY tag_table.tag;

CREATE OR REPLACE VIEW translation_theme_frequency AS
SELECT tag_table.tag, COUNT(*) AS frequency
FROM translation_clause_analysis AS a
JOIN JSON_TABLE(
  a.theme_tags,
  '$[*]' COLUMNS(tag VARCHAR(100) PATH '$')
) AS tag_table
GROUP BY tag_table.tag;
"""


def main() -> None:
    rows = load_rows()
    sql = build_sql(rows)
    command = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "sh",
        "-lc",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql '
        '--default-character-set=utf8mb4 -uroot -D "$MYSQL_DATABASE"',
    ]
    result = subprocess.run(command, input=sql, text=True, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
    print(f"imported {len(rows)} clause units into {CONTAINER}:cet4")


if __name__ == "__main__":
    main()
