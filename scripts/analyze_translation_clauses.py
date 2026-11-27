#!/usr/bin/env python3
"""Aggregate the manually curated CET translation clause annotations."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "analysis" / "translation_clause_annotations.tsv"
REPORT = ROOT / "analysis" / "translation_high_frequency_report.md"
JSON_OUT = ROOT / "analysis" / "translation_frequency.json"

PATTERN_TEMPLATES = {
    "动作与过程": "use / produce / carry / prepare + object",
    "被动语态": "be + past participle (+ by/in/for)",
    "是与定义": "be / serve as + noun phrase",
    "发展与变化": "develop / improve / increase / undergo changes",
    "have/contain/include": "have / contain / include / be rich in",
    "地点与分布": "be located in/on / be found throughout / come from",
    "时间结构": "date back to / since / for / by the end of",
    "促进与推动": "promote / drive / advance / improve",
    "使役结构": "enable / allow / make + object + complement",
    "越来越多": "increasingly / a growing number of / more and more",
    "占比与数量": "account for / reach / exceed / increase by",
    "最高级": "one of the most ... / the world's longest",
    "象征与代表": "symbolize / represent / mark / embody",
    "开始与持续": "begin/start to / continue to / remain",
    "减少与保护": "reduce / prevent / protect / preserve",
    "结果与后果": "lead to / result in / cause / leave + object + complement",
    "重要性": "attach great importance to / be important to",
    "感官与状态": "feel / taste / sound / remain + adjective",
    "成为": "become / develop into / turn ... into",
    "help (to) do": "help (to) + verb",
    "流行与欢迎": "be popular with/among / be widely welcomed",
    "方式与途径": "by + -ing / through / via / by means of",
    "起源与历史": "originate in / date back to",
    "用途与功能": "be used to/for / serve ... purposes",
    "变化与差异": "vary / differ from / range from ... to ...",
    "提供": "provide somebody with something / provide something for",
    "发挥作用": "play an important role in + noun/-ing",
    "贡献": "make a contribution to / contribute to",
    "满足需求": "meet / satisfy the needs of",
}


def split_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def main() -> None:
    with SOURCE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    required = {
        "prompt_id",
        "exam",
        "set_number",
        "unit",
        "zh_clause",
        "zh_backbone",
        "en_phrase",
        "pattern",
        "theme",
    }
    missing = required - set(rows[0]) if rows else required
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")

    duplicate_keys = [
        key
        for key, count in Counter(
            (row["prompt_id"], row["unit"]) for row in rows
        ).items()
        if count > 1
    ]
    if duplicate_keys:
        raise SystemExit(f"Duplicate prompt/unit keys: {duplicate_keys}")

    prompts = {row["prompt_id"] for row in rows}
    patterns = Counter(
        tag for row in rows for tag in split_tags(row["pattern"])
    )
    themes = Counter(tag for row in rows for tag in split_tags(row["theme"]))
    phrase_heads = Counter(
        row["en_phrase"].strip().split(maxsplit=1)[0].lower()
        for row in rows
        if row["en_phrase"].strip()
    )

    payload = {
        "valid_prompts": len(prompts),
        "simple_clause_units": len(rows),
        "excluded_prompt_ids": [38],
        "patterns": dict(patterns.most_common()),
        "themes": dict(themes.most_common()),
        "english_phrase_heads": dict(phrase_heads.most_common()),
    }
    JSON_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    def table(counter: Counter[str], limit: int | None = None) -> str:
        items = counter.most_common(limit)
        lines = ["| 排名 | 类别 | 次数 |", "|---:|---|---:|"]
        lines.extend(
            f"| {rank} | {name} | {count} |"
            for rank, (name, count) in enumerate(items, 1)
        )
        return "\n".join(lines)

    def phrase_table(counter: Counter[str], limit: int = 20) -> str:
        lines = ["| 排名 | 结构 | 次数 | 推荐英文词块 |", "|---:|---|---:|---|"]
        for rank, (name, count) in enumerate(counter.most_common(limit), 1):
            template = PATTERN_TEMPLATES.get(name, "—")
            lines.append(f"| {rank} | {name} | {count} | `{template}` |")
        return "\n".join(lines)

    report = f"""# CET-4 翻译简单句与高频表达统计

## 数据口径

- 数据库原始记录：42 条。
- 有效翻译材料：{len(prompts)} 篇。
- 排除异常记录：`translation_prompts.id=38`，其内容为英文写作题。
- 拆分后的简单句/语义单元：{len(rows)} 条。
- 统计单位：一个语义单元可以同时拥有多个结构标签或主题标签。

## 高频英文结构

{table(patterns)}

## 高频可背词块

下表把出现次数最多的结构转成可直接套用的英文骨架。次数来自逐句标注，不是主观排序。

{phrase_table(patterns)}

## 高频内容主题

{table(themes)}

## 英文短语首词

该表用于观察翻译时最常调用的谓语或结构入口，不等同于严格词频。

{table(phrase_heads, 20)}

## 使用建议

1. 优先掌握前十项英文结构，并用不同主题名词替换宾语。
2. 先根据“中文主干”口头说出英文核心短语，再扩展时间、地点、原因和结果。
3. 对“发展与变化、作用与贡献、文化与传统”三个高频主题分别建立词块库。
4. 明细见 `translation_clause_annotations.tsv`；机器可读统计见 `translation_frequency.json`。
"""
    REPORT.write_text(report, encoding="utf-8")
    print(
        f"processed {len(rows)} clause units from {len(prompts)} prompts; "
        f"wrote {REPORT.name} and {JSON_OUT.name}"
    )


if __name__ == "__main__":
    main()
