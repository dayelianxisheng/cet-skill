#!/usr/bin/env python3
"""Extract the complete data available in the 2014-2019 CET-4 PDF bundle.

The PDFs are user-provided/authorized local corpus material.  This script keeps
the source text faithful, maps the 2014-2015 reading-only numbering (1-30) to
the database's canonical reading range (26-55), and never invents answers or
listening transcripts that are absent from the source PDFs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


PDF_NAME_RE = re.compile(
    r"(?P<year>20(?:14|15|16|17|18|19))年(?P<month>6|12)月大学英语四级考试题[（(](?P<set_cn>[一二三])[）)]\.pdf$"
)
SET_NUMBER = {"一": 1, "二": 2, "三": 3}
PART_RE = {
    "writing": re.compile(r"^\s*Part\s+I\s+Writing\s*\(", re.I),
    "listening": re.compile(r"^\s*Part\s+II\s+Listening\s+Comprehension\s*\(", re.I),
    "reading": re.compile(r"^\s*Part\s+III\s+Reading\s+Comprehension\s*\(", re.I),
    "translation": re.compile(r"^\s*Part\s+IV\s+Translation\s*\(", re.I),
}
QUESTION_RE = re.compile(r"^\s*(\d{1,2})\.\s*(.*)$")
OPTION_RE = re.compile(r"^\s*([A-D])\.\s*(.*)$")
# A second option on the same PDF text line is column-aligned with at least
# two spaces.  Requiring that gap avoids misreading "Ph. D." as option D.
OPTION_TOKEN_RE = re.compile(r"(?:^|\s{2,})([A-D])\.\s*")
# Most papers end at O, but a few historical matching passages continue to P
# or Q.  Do not conflate this with the A-O word bank below.
MATCHING_PARAGRAPH_RE = re.compile(r"^\s*([A-Z])\)\s*(.*)$")
WORD_BANK_RE = re.compile(r"(?:^|\s)([A-O])\.\s*([A-Za-z][A-Za-z'’-]*)")
GROUP_RANGE_RE = re.compile(r"questions?\s+(\d{1,2})\s+(?:to|and)\s+(\d{1,2})", re.I)
GROUP_RANGE_ALT_RE = re.compile(r"questions?\s+(\d{1,2})\s*[-–]\s*(\d{1,2})", re.I)
CHINESE_RE = re.compile(r"[\u3400-\u9fff]")


@dataclass
class Option:
    label: str
    text: str


@dataclass
class Question:
    number: int
    question_type: str
    stem: str = ""
    options: list[Option] = field(default_factory=list)
    listening_group: int | None = None
    passage_index: int | None = None
    source_number: int | None = None


@dataclass
class ListeningGroup:
    group_type: str
    group_number: int
    start: int
    end: int
    instructions: str
    questions: list[Question]


@dataclass
class Passage:
    passage_type: str
    passage_index: int
    title: str
    content: str
    paragraphs: list[tuple[str, str]] = field(default_factory=list)
    word_bank: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Exam:
    year: int
    month: int
    set_number: int
    filename: str
    source_path: str
    writing_prompt: str
    writing_min: int
    writing_max: int
    translation_instructions: str
    translation_source: str
    listening_groups: list[ListeningGroup]
    passages: list[Passage]
    reading_questions: list[Question]
    warnings: list[str] = field(default_factory=list)

    @property
    def exam_id(self) -> int:
        return self.year * 1000 + self.month * 10 + self.set_number


def clean_line(line: str, title_re: re.Pattern[str]) -> str:
    line = line.replace("\u00a0", " ").replace("\x0c", "")
    line = re.sub(r"\s+(?:一键批改写译|扫码精听|材料音频)\s*$", "", line)
    stripped = line.strip()
    if not stripped:
        return ""
    if title_re.fullmatch(stripped):
        return ""
    if "本试卷由粉笔用户" in stripped:
        return ""
    if re.fullmatch(r"(?:一键批改写译|扫码精听|材料音频)", stripped):
        return ""
    return line.rstrip()


def compact_lines(lines: Iterable[str]) -> list[str]:
    out: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            out.append(line.rstrip())
            blank = False
        elif out and not blank:
            out.append("")
            blank = True
    while out and not out[-1]:
        out.pop()
    return out


def join_lines(lines: Iterable[str], paragraph_breaks: bool = False) -> str:
    parts: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = " ".join(x.strip() for x in paragraph if x.strip())
        text = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "-", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(text)
        paragraph.clear()

    for line in lines:
        if line.strip():
            paragraph.append(line)
        else:
            flush()
    flush()
    return ("\n\n" if paragraph_breaks else " ").join(parts).strip()


def join_indented_paragraphs(lines: Iterable[str]) -> str:
    """Recover prose paragraphs from first-line indentation in layout PDF text.

    The historical PDFs do not put blank lines between careful-reading
    paragraphs.  Their first line is indented farther than wrapped lines,
    however.  Page headers are removed earlier, so a shallow-indented line
    after a page break remains a continuation rather than a false paragraph.
    """
    source = [line.rstrip() for line in lines if line.strip()]
    if not source:
        return ""
    indents = [len(line) - len(line.lstrip()) for line in source]
    continuation_indent = min(indents)
    parts: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if not paragraph:
            return
        text = " ".join(line.strip() for line in paragraph)
        text = re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "-", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            parts.append(text)
        paragraph.clear()

    for line, indent in zip(source, indents):
        previous = " ".join(item.strip() for item in paragraph).rstrip()
        starts_paragraph = (
            bool(paragraph)
            and indent >= continuation_indent + 3
            and bool(re.search(r"[.!?][\"'”’)]?$", previous))
        )
        if starts_paragraph:
            flush()
        paragraph.append(line)
    flush()
    return "\n\n".join(parts)


def find_part_indices(lines: list[str]) -> dict[str, int]:
    indices: dict[str, int] = {}
    for i, line in enumerate(lines):
        for name, pattern in PART_RE.items():
            if name not in indices and pattern.search(line):
                indices[name] = i
    missing = [name for name in PART_RE if name not in indices]
    if missing:
        raise ValueError(f"missing part markers: {', '.join(missing)}")
    if not (indices["writing"] < indices["listening"] < indices["reading"] < indices["translation"]):
        raise ValueError(f"part markers out of order: {indices}")
    return indices


def first_question_line(lines: list[str], number: int, start: int = 0) -> int:
    for i in range(start, len(lines)):
        match = QUESTION_RE.match(lines[i])
        if match and int(match.group(1)) == number:
            return i
    raise ValueError(f"question {number} not found")


def sentence_end_index(lines: list[str], start: int) -> int:
    text: list[str] = []
    for i in range(start, len(lines)):
        if not lines[i].strip():
            if text and re.search(r"[.?!。？！]['\"”’)]?\s*$", " ".join(text)):
                return i
            continue
        text.append(lines[i].strip())
        if re.search(r"[.?!。？！]['\"”’)]?\s*$", " ".join(text)):
            return i + 1
    return len(lines)


def parse_mcq_block(
    lines: list[str], expected_numbers: Iterable[int], question_type: str, number_offset: int = 0
) -> list[Question]:
    expected = set(expected_numbers)
    questions: list[Question] = []
    current: Question | None = None
    current_option: Option | None = None

    def append_text(existing: str, extra: str) -> str:
        return join_lines([existing, extra]) if existing else extra.strip()

    for line in lines:
        qmatch = QUESTION_RE.match(line)
        if qmatch and int(qmatch.group(1)) in expected:
            source_number = int(qmatch.group(1))
            current = Question(
                number=source_number + number_offset,
                source_number=source_number,
                question_type=question_type,
                stem=qmatch.group(2).strip(),
            )
            questions.append(current)
            current_option = None
            continue
        inline_options = split_inline_options(line)
        if inline_options and current is not None:
            for label, option_text in inline_options:
                current_option = Option(label, option_text)
                current.options.append(current_option)
            continue
        if current is None or not line.strip():
            continue
        if current_option is not None:
            current_option.text = append_text(current_option.text, line.strip())
        else:
            current.stem = append_text(current.stem, line.strip())

    return questions


def split_inline_options(line: str) -> list[tuple[str, str]]:
    stripped = line.strip()
    matches = list(OPTION_TOKEN_RE.finditer(stripped))
    if not matches or matches[0].start() != 0:
        return []
    options: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(stripped)
        options.append((match.group(1), stripped[match.end() : end].strip()))
    return options


def listening_group_type(text: str) -> str:
    lowered = text.lower()
    if "news report" in lowered:
        return "news_report"
    if "conversation" in lowered:
        return "conversation"
    if "passage" in lowered or "monologue" in lowered:
        return "passage"
    return "listening"


def parse_listening(lines: list[str], warnings: list[str]) -> list[ListeningGroup]:
    starts: list[tuple[int, int, int, str]] = []
    for i, line in enumerate(lines):
        if "Direction" not in line and "question" not in line.lower():
            continue
        normalized = join_lines(lines[i : min(i + 2, len(lines))])
        match = GROUP_RANGE_RE.search(normalized) or GROUP_RANGE_ALT_RE.search(normalized)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if 1 <= start <= end <= 25 and not any(x[1] == start for x in starts):
                starts.append((i, start, end, normalized))

    groups: list[ListeningGroup] = []
    type_counts: dict[str, int] = {}
    for position, (line_index, start, end, instructions) in enumerate(starts):
        block_end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        questions = parse_mcq_block(lines[line_index + 1 : block_end], range(start, end + 1), "listening")
        group_type = listening_group_type(instructions)
        type_counts[group_type] = type_counts.get(group_type, 0) + 1
        group_number = type_counts[group_type]
        group_index = len(groups) + 1
        for question in questions:
            question.listening_group = group_index
        groups.append(
            ListeningGroup(group_type, group_number, start, end, instructions, questions)
        )
        if len(questions) != end - start + 1:
            warnings.append(
                f"listening group {start}-{end}: parsed {len(questions)} questions"
            )
        for question in questions:
            if len(question.options) != 4:
                warnings.append(
                    f"listening question {question.number}: parsed {len(question.options)} options"
                )
    return groups


def strip_leading_directions(lines: list[str]) -> list[str]:
    lines = compact_lines(lines)
    if not lines:
        return lines
    first_text = join_lines(lines[:3])
    if first_text.lower().startswith("directions:"):
        for i, line in enumerate(lines):
            if not line.strip() and i > 0:
                return compact_lines(lines[i + 1 :])
    return lines


def parse_matching_passage(lines: list[str]) -> tuple[str, str, list[tuple[str, str]]]:
    first_label = next(
        (i for i, line in enumerate(lines) if MATCHING_PARAGRAPH_RE.match(line)), None
    )
    if first_label is None:
        raise ValueError("matching passage has no A)-O) paragraphs")
    title = join_lines(lines[:first_label])
    paragraphs: list[tuple[str, str]] = []
    current_label: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_label, current_lines
        if current_label is not None:
            paragraphs.append((current_label, join_lines(current_lines, paragraph_breaks=True)))
        current_label = None
        current_lines = []

    for line in lines[first_label:]:
        match = MATCHING_PARAGRAPH_RE.match(line)
        if match:
            flush()
            current_label = match.group(1)
            current_lines = [match.group(2)]
        else:
            current_lines.append(line)
    flush()
    content = "\n\n".join(f"{label}) {text}" for label, text in paragraphs)
    return title, content, paragraphs


def find_passage2_start(lines: list[str], last_question_line: int) -> int:
    d_seen = False
    d_text: list[str] = []
    for i in range(last_question_line + 1, len(lines)):
        inline_options = split_inline_options(lines[i])
        if inline_options:
            d_option = next((text for label, text in inline_options if label == "D"), None)
            if d_option is not None:
                d_seen = True
                d_text = [d_option]
                if re.search(r"[.?!]['\"”’)]?\s*$", d_text[0]):
                    for j in range(i + 1, len(lines)):
                        if lines[j].strip():
                            return j
            elif d_seen:
                break
            continue
        if not d_seen:
            continue
        if not lines[i].strip():
            if d_text and re.search(r"[.?!]['\"”’)]?\s*$", " ".join(d_text)):
                for j in range(i + 1, len(lines)):
                    if lines[j].strip():
                        return j
            continue
        if re.search(r"^\s*Part\s+", lines[i], re.I):
            break
        d_text.append(lines[i].strip())
        if re.search(r"[.?!]['\"”’)]?\s*$", " ".join(d_text)):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return j
    raise ValueError("could not locate second careful-reading passage")


def parse_reading(
    lines: list[str], old_numbering: bool, warnings: list[str]
) -> tuple[list[Passage], list[Question]]:
    word_entries: dict[str, str] = {}
    word_line_indices: list[int] = []
    for i, line in enumerate(lines):
        found = WORD_BANK_RE.findall(line)
        if found:
            for label, word in found:
                word_entries[label] = word
            word_line_indices.append(i)
            if len(word_entries) == 15:
                break
    if len(word_entries) != 15 or not word_line_indices:
        raise ValueError(f"expected 15 word-bank entries, found {len(word_entries)}")
    word_start, word_end = min(word_line_indices), max(word_line_indices) + 1
    banked_content = join_lines(strip_leading_directions(lines[:word_start]), paragraph_breaks=True)

    matching_first = 11 if old_numbering else 36
    matching_last = 20 if old_numbering else 45
    careful1_first = 21 if old_numbering else 46
    careful1_last = 25 if old_numbering else 50
    careful2_first = 26 if old_numbering else 51
    careful2_last = 30 if old_numbering else 55
    offset = 25 if old_numbering else 0

    matching_q_start = first_question_line(lines, matching_first, word_end)
    matching_last_line = first_question_line(lines, matching_last, matching_q_start)
    matching_q_end = sentence_end_index(lines, matching_last_line)
    careful1_q_start = first_question_line(lines, careful1_first, matching_q_end)
    careful1_last_line = first_question_line(lines, careful1_last, careful1_q_start)
    passage2_start = find_passage2_start(lines, careful1_last_line)
    careful2_q_start = first_question_line(lines, careful2_first, passage2_start)

    matching_lines = strip_leading_directions(lines[word_end:matching_q_start])
    title, matching_content, paragraphs = parse_matching_passage(matching_lines)
    matching_questions = parse_mcq_block(
        lines[matching_q_start:matching_q_end],
        range(matching_first, matching_last + 1),
        "matching",
        offset,
    )
    careful1_content = join_indented_paragraphs(
        strip_leading_directions(lines[matching_q_end:careful1_q_start])
    )
    careful1_questions = parse_mcq_block(
        lines[careful1_q_start:passage2_start],
        range(careful1_first, careful1_last + 1),
        "careful_reading",
        offset,
    )
    careful2_content = join_indented_paragraphs(
        strip_leading_directions(lines[passage2_start:careful2_q_start])
    )
    careful2_questions = parse_mcq_block(
        lines[careful2_q_start:],
        range(careful2_first, careful2_last + 1),
        "careful_reading",
        offset,
    )

    banked_questions = [
        Question(
            number=n + offset,
            source_number=n,
            question_type="banked_cloze",
            passage_index=1,
        )
        for n in range(1 if old_numbering else 26, 11 if old_numbering else 36)
    ]
    for question in matching_questions:
        question.passage_index = 2
    for question in careful1_questions:
        question.passage_index = 3
    for question in careful2_questions:
        question.passage_index = 4

    questions = banked_questions + matching_questions + careful1_questions + careful2_questions
    expected_numbers = list(range(26, 56))
    parsed_numbers = [question.number for question in questions]
    if parsed_numbers != expected_numbers:
        warnings.append(f"reading question numbers: {parsed_numbers}")
    for question in careful1_questions + careful2_questions:
        if len(question.options) != 4:
            warnings.append(
                f"reading question {question.number}: parsed {len(question.options)} options"
            )
    passages = [
        Passage(
            "banked_cloze",
            1,
            "Banked Cloze",
            banked_content,
            word_bank=sorted(word_entries.items()),
        ),
        Passage("matching", 1, title, matching_content, paragraphs=paragraphs),
        Passage("careful_reading", 1, "Passage 1", careful1_content),
        Passage("careful_reading", 2, "Passage 2", careful2_content),
    ]
    return passages, questions


def parse_translation(lines: list[str]) -> tuple[str, str]:
    chinese_start = next((i for i, line in enumerate(lines) if CHINESE_RE.search(line)), None)
    if chinese_start is None:
        raise ValueError("translation source text not found")
    instructions = join_lines(lines[:chinese_start])
    source = join_lines(lines[chinese_start:], paragraph_breaks=True)
    source = re.sub(r"\s+", "", source)
    return instructions, source


def parse_exam(pdf_path: Path, archive_path: Path, inner_name: str) -> Exam:
    match = PDF_NAME_RE.search(pdf_path.name)
    if not match:
        raise ValueError(f"unexpected PDF filename: {pdf_path.name}")
    year = int(match.group("year"))
    month = int(match.group("month"))
    set_number = SET_NUMBER[match.group("set_cn")]
    title_re = re.compile(
        rf"{year}年{month}月大学英语四级考试题[（(][一二三][）)]"
    )
    result = subprocess.run(
        ["/usr/bin/pdftotext", "-layout", "-nopgbrk", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = compact_lines(clean_line(line, title_re) for line in result.stdout.splitlines())
    indices = find_part_indices(lines)
    writing_lines = lines[indices["writing"] + 1 : indices["listening"]]
    listening_lines = lines[indices["listening"] + 1 : indices["reading"]]
    reading_lines = lines[indices["reading"] + 1 : indices["translation"]]
    translation_lines = lines[indices["translation"] + 1 :]

    warnings: list[str] = []
    writing_prompt = join_lines(writing_lines, paragraph_breaks=True)
    counts = re.search(
        r"at\s+least\s+([0-9lI]+)\s+words?\s*,?\s*(?:but\s+)?no\s+more\s+than\s+([0-9lI]+)\s+words?",
        writing_prompt,
        re.I,
    )
    normalize_ocr_number = lambda value: int(value.lower().replace("l", "1").replace("i", "1"))
    writing_min = normalize_ocr_number(counts.group(1)) if counts else 120
    writing_max = normalize_ocr_number(counts.group(2)) if counts else 180
    if not counts:
        warnings.append("writing word-count range not found; defaulted to 120-180")

    listening_groups = parse_listening(listening_lines, warnings)
    if year <= 2015 and not listening_groups:
        warnings.append("source PDF contains no listening questions or transcript")
    elif sum(len(group.questions) for group in listening_groups) != 25:
        warnings.append(
            f"parsed {sum(len(group.questions) for group in listening_groups)} listening questions"
        )
    warnings.append("source PDF contains no answer key")
    warnings.append("source PDF contains no listening transcript")

    passages, reading_questions = parse_reading(reading_lines, year <= 2015, warnings)
    translation_instructions, translation_source = parse_translation(translation_lines)
    source_path = f"{archive_path}::{inner_name}"
    return Exam(
        year=year,
        month=month,
        set_number=set_number,
        filename=pdf_path.name,
        source_path=source_path,
        writing_prompt=writing_prompt,
        writing_min=writing_min,
        writing_max=writing_max,
        translation_instructions=translation_instructions,
        translation_source=translation_source,
        listening_groups=listening_groups,
        passages=passages,
        reading_questions=reading_questions,
        warnings=warnings,
    )


def sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "''")
    return f"'{text}'"


def insert_sql(table: str, columns: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return ""
    values = ",\n".join(
        "(" + ",".join(sql_value(value) for value in row) + ")" for row in rows
    )
    quoted_columns = ",".join(f"`{column}`" for column in columns)
    return f"INSERT INTO `{table}` ({quoted_columns}) VALUES\n{values};\n"


def render_sql(exams: list[Exam]) -> str:
    exam_rows: list[list[object]] = []
    section_rows: list[list[object]] = []
    writing_rows: list[list[object]] = []
    group_rows: list[list[object]] = []
    passage_rows: list[list[object]] = []
    question_rows: list[list[object]] = []
    option_rows: list[list[object]] = []
    paragraph_rows: list[list[object]] = []
    word_rows: list[list[object]] = []
    translation_rows: list[list[object]] = []

    section_types = [
        ("writing", "Writing", 30),
        ("listening", "Listening Comprehension", 25),
        ("reading", "Reading Comprehension", 40),
        ("translation", "Translation", 30),
    ]
    for exam in exams:
        exam_id = exam.exam_id
        title = f"CET4 {exam.year}-{exam.month:02d} Set {exam.set_number}"
        exam_rows.append(
            [exam_id, title, exam.year, exam.month, exam.set_number, "CET4", exam.source_path, "", 0, 0]
        )
        section_ids: dict[str, int] = {}
        for order, (section_type, name, duration) in enumerate(section_types, start=1):
            section_id = exam_id * 10 + order
            section_ids[section_type] = section_id
            section_rows.append([section_id, exam_id, section_type, name, order, duration])
        writing_rows.append(
            [exam_id, exam_id, section_ids["writing"], exam.writing_prompt, exam.writing_min, exam.writing_max]
        )
        translation_rows.append(
            [exam_id, exam_id, section_ids["translation"], exam.translation_instructions, exam.translation_source]
        )

        group_id_by_index: dict[int, int] = {}
        for group_index, group in enumerate(exam.listening_groups, start=1):
            group_id = exam_id * 10 + group_index
            group_id_by_index[group_index] = group_id
            group_rows.append(
                [
                    group_id,
                    exam_id,
                    section_ids["listening"],
                    group.group_type,
                    group.group_number,
                    f"{group.group_type.replace('_', ' ').title()} {group.group_number}",
                    group.start,
                    group.end,
                    group.instructions,
                    group_index,
                ]
            )
            for question in group.questions:
                question_id = exam_id * 100 + question.number
                question_rows.append(
                    [
                        question_id,
                        exam_id,
                        section_ids["listening"],
                        group_id,
                        None,
                        question.number,
                        question.question_type,
                        question.stem,
                        question.number,
                    ]
                )
                for option_order, option in enumerate(question.options, start=1):
                    option_rows.append(
                        [question_id * 10 + option_order, question_id, option.label, option.text, option_order]
                    )

        passage_id_by_index: dict[int, int] = {}
        for global_index, passage in enumerate(exam.passages, start=1):
            passage_id = exam_id * 10 + global_index
            passage_id_by_index[global_index] = passage_id
            passage_rows.append(
                [
                    passage_id,
                    exam_id,
                    section_ids["reading"],
                    passage.passage_type,
                    passage.passage_index,
                    passage.title,
                    passage.content,
                    global_index,
                ]
            )
            for order, (label, text) in enumerate(passage.paragraphs, start=1):
                paragraph_rows.append([passage_id * 100 + order, passage_id, label, text, order])
            for order, (label, word) in enumerate(passage.word_bank, start=1):
                word_rows.append([passage_id * 100 + order, passage_id, label, word, order])

        for question in exam.reading_questions:
            question_id = exam_id * 100 + question.number
            passage_id = passage_id_by_index[question.passage_index or 1]
            question_rows.append(
                [
                    question_id,
                    exam_id,
                    section_ids["reading"],
                    None,
                    passage_id,
                    question.number,
                    question.question_type,
                    question.stem,
                    question.number,
                ]
            )
            for option_order, option in enumerate(question.options, start=1):
                option_rows.append(
                    [question_id * 10 + option_order, question_id, option.label, option.text, option_order]
                )

    header = """-- Complete CET-4 historical corpus extracted from the user-provided 2014-2019 PDF bundle.
-- Scope: every source field present in the PDFs (writing, listening questions/options when present,
-- banked cloze, paragraph matching, careful reading, and translation).
-- Source limitations: the PDFs contain no answer keys or listening transcripts; 2014-2015 PDFs
-- also omit the listening questions. No missing source content has been inferred or fabricated.
-- The 2014-2015 reading-only numbering 1-30 is normalized to canonical database numbers 26-55.
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS=0;
START TRANSACTION;
"""
    body = "\n".join(
        part
        for part in [
            insert_sql(
                "exams",
                [
                    "id",
                    "title",
                    "year",
                    "month",
                    "set_number",
                    "exam_type",
                    "source_pdf",
                    "source_markdown",
                    "answers_in_source",
                    "listening_transcript_in_source",
                ],
                exam_rows,
            ),
            insert_sql(
                "sections",
                ["id", "exam_id", "section_type", "name", "sort_order", "duration_minutes"],
                section_rows,
            ),
            insert_sql(
                "writing_prompts",
                ["id", "exam_id", "section_id", "prompt_text", "word_count_min", "word_count_max"],
                writing_rows,
            ),
            insert_sql(
                "listening_groups",
                [
                    "id",
                    "exam_id",
                    "section_id",
                    "group_type",
                    "group_number",
                    "title",
                    "question_start",
                    "question_end",
                    "instructions",
                    "sort_order",
                ],
                group_rows,
            ),
            insert_sql(
                "passages",
                [
                    "id",
                    "exam_id",
                    "section_id",
                    "passage_type",
                    "passage_index",
                    "title",
                    "content_text",
                    "sort_order",
                ],
                passage_rows,
            ),
            insert_sql(
                "questions",
                [
                    "id",
                    "exam_id",
                    "section_id",
                    "listening_group_id",
                    "passage_id",
                    "question_number",
                    "question_type",
                    "stem_text",
                    "sort_order",
                ],
                question_rows,
            ),
            insert_sql(
                "options",
                ["id", "question_id", "option_label", "option_text", "sort_order"],
                option_rows,
            ),
            insert_sql(
                "matching_paragraphs",
                ["id", "passage_id", "paragraph_label", "content_text", "sort_order"],
                paragraph_rows,
            ),
            insert_sql(
                "word_bank_entries",
                ["id", "passage_id", "option_label", "word_text", "sort_order"],
                word_rows,
            ),
            insert_sql(
                "translation_prompts",
                ["id", "exam_id", "section_id", "instructions", "source_text"],
                translation_rows,
            ),
        ]
        if part
    )
    return header + "\n" + body + "\nCOMMIT;\nSET FOREIGN_KEY_CHECKS=1;\n"


def audit_record(exam: Exam) -> dict[str, object]:
    listening_questions = sum(len(group.questions) for group in exam.listening_groups)
    listening_options = sum(
        len(question.options) for group in exam.listening_groups for question in group.questions
    )
    reading_options = sum(len(question.options) for question in exam.reading_questions)
    return {
        "year": exam.year,
        "month": exam.month,
        "set_number": exam.set_number,
        "filename": exam.filename,
        "writing_prompt_chars": len(exam.writing_prompt),
        "listening_groups": len(exam.listening_groups),
        "listening_questions": listening_questions,
        "listening_options": listening_options,
        "passages": len(exam.passages),
        "banked_cloze_words": len(exam.passages[0].word_bank),
        "matching_paragraphs": len(exam.passages[1].paragraphs),
        "reading_questions": len(exam.reading_questions),
        "reading_options": reading_options,
        "translation_chars": len(exam.translation_source),
        "warnings": exam.warnings,
    }


def extract_all(archive: Path) -> list[Exam]:
    exams: list[Exam] = []
    with tempfile.TemporaryDirectory(prefix="cet4-historical-") as temp_dir:
        temp_root = Path(temp_dir)
        # This bundle stores UTF-8 filename bytes without setting ZIP's UTF-8
        # flag.  zipfile therefore exposes mojibake decoded as CP437.  Repair
        # the display name while retaining ZipInfo for byte-accurate reads.
        with zipfile.ZipFile(archive) as zf:
            members: list[tuple[str, zipfile.ZipInfo]] = []
            for info in zf.infolist():
                try:
                    repaired = info.filename.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    repaired = info.filename
                if repaired.lower().endswith(".pdf") and "__MACOSX" not in repaired:
                    members.append((repaired, info))
            for member, info in sorted(members, key=lambda item: item[0]):
                destination = temp_root / Path(member).name
                destination.write_bytes(zf.read(info))
                try:
                    exams.append(parse_exam(destination, archive.resolve(), member))
                except Exception as exc:
                    raise RuntimeError(f"failed to parse {member}: {exc}") from exc
    return sorted(exams, key=lambda exam: (exam.year, exam.month, exam.set_number))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("--sql", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()

    exams = extract_all(args.archive)
    if len(exams) != 36:
        raise SystemExit(f"expected 36 PDFs, parsed {len(exams)}")
    args.sql.parent.mkdir(parents=True, exist_ok=True)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.sql.write_text(render_sql(exams), encoding="utf-8")
    audit = {
        "archive": str(args.archive.resolve()),
        "exam_count": len(exams),
        "records": [audit_record(exam) for exam in exams],
    }
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
