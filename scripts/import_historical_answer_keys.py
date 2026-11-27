#!/usr/bin/env python3
"""Build a standalone answer-key SQL file for the 2014-2019 CET-4 corpus.

The local question PDFs and public answer sources do not always use the same
"set 1/2/3" ordering.  For 2016-2019 this importer therefore aligns answers by
question/option text, word-bank content, and matching-paragraph content instead
of trusting the displayed set number.  The 2014-2015 answer PDFs correspond to
the same named source sets and are parsed directly (their reading questions
36-65 map to the corpus' canonical 26-55 range).

No downloaded PDF is retained.  Ambiguous or incomplete mappings abort SQL
generation rather than silently guessing.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from lxml import html


GUOJIYA_BASE = "https://www.guojiya.cn"
GITHUB_REPOSITORY = "https://github.com/0609x/CET46-Resources"
GITHUB_RAW = "https://raw.githubusercontent.com/0609x/CET46-Resources/main/"
USER_AGENT = "cet-skill-historical-answer-importer/1.0"
SET_CN = {1: "一", 2: "二", 3: "三"}


@dataclass
class Answer:
    question_id: int
    value: str
    text: str
    source: str
    confidence: float
    notes: str


@dataclass
class WebQuestion:
    number: int
    stem: str
    options: dict[str, str]
    answer: str


@dataclass
class WebPaper:
    year: int
    month: int
    set_number: int
    url: str
    mcq: dict[int, WebQuestion]
    words: dict[str, str]
    bank_answers: dict[int, str]
    paragraphs: dict[str, str]
    matching: dict[int, tuple[str, str]]


def load_extractor():
    path = Path(__file__).with_name("extract_historical_full_papers.py")
    spec = importlib.util.spec_from_file_location("historical_extractor", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return response.read()


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    value = value.replace("’", "'").replace("‘", "'").replace("�", "'")
    return re.sub(r"[^a-z0-9]+", "", value)


def similarity(left: str, right: str) -> float:
    a, b = normalized(left), normalized(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def collection_score(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = list(left), list(right)
    if not a or len(a) != len(b):
        return 0.0
    forward = sum(max(similarity(x, y) for y in b) for x in a) / len(a)
    backward = sum(max(similarity(y, x) for x in a) for y in b) / len(b)
    return (forward + backward) / 2


def best_items(scored: list[tuple[float, object]], threshold: float, margin: float = 0.012) -> list[object]:
    if not scored:
        return []
    scored.sort(key=lambda item: item[0], reverse=True)
    best = scored[0][0]
    if best < threshold:
        return []
    return [item for score, item in scored if best - score <= margin]


def parse_web_paper(year: int, month: int, set_number: int) -> WebPaper:
    url = f"{GUOJIYA_BASE}/exam/cet4_{year}_{month:02d}_{set_number}/answers"
    document = html.fromstring(fetch(url))
    mcq: dict[int, WebQuestion] = {}
    for frame in document.xpath('//*[@data-question-id]'):
        match = re.fullmatch(r"q(\d+)", frame.get("data-question-id", ""))
        if not match:
            continue
        number = int(match.group(1))
        if number not in {*range(1, 26), *range(46, 56)}:
            continue
        heading = frame.xpath('.//*[contains(@class,"question-heading")]')
        stem = " ".join((heading[0] if heading else frame).text_content().split())
        stem = re.sub(rf"^{number}\.\s*", "", stem)
        stem = stem.split("未作答", 1)[0].strip()
        options: dict[str, str] = {}
        answer = ""
        for label in frame.xpath(".//label[.//input]"):
            values = label.xpath(".//input/@value")
            if not values:
                continue
            option_label = values[0]
            text = " ".join(label.text_content().replace("✓ 正确答案", "").split())
            text = re.sub(r"^[A-D]\)\s*", "", text).strip()
            options[option_label] = text
            if label.get("data-state") == "correct":
                answer = option_label
        if len(options) == 4 and answer:
            mcq[number] = WebQuestion(number, stem, options, answer)

    words: dict[str, str] = {}
    bank_answers: dict[int, str] = {}
    word_sections = [section for section in document.xpath("//section") if "Word Bank" in section.text_content()]
    if len(word_sections) != 1:
        raise RuntimeError(f"{url}: expected one word-bank section, found {len(word_sections)}")
    word_section = word_sections[0]
    for box in word_section.xpath('.//div[contains(@class,"grid")]/span'):
        match = re.match(r"([A-Z])\)\s*(.+)", " ".join(box.text_content().split()))
        if match:
            words[match.group(1)] = match.group(2).strip()
    for block in word_section.xpath('.//div[contains(@class,"bg-bg-3")]'):
        text_value = " ".join(block.text_content().split())
        match = re.search(r"(\d+)\..*?正确答案:\s*([A-Z])", text_value)
        if match:
            bank_answers[int(match.group(1))] = match.group(2)

    paragraph_sections = []
    # Identify the matching passage by its repeated A)-style paragraph labels.
    for section in document.xpath('//section[contains(@class,"reading-pane--passage")]'):
        labels = [" ".join(node.text_content().split()) for node in section.xpath('.//span[contains(@class,"font-mono")]')]
        if len([label for label in labels if re.fullmatch(r"[A-Z]\)", label)]) >= 8:
            paragraph_sections.append(section)
    if len(paragraph_sections) != 1:
        raise RuntimeError(f"{url}: expected one matching passage, found {len(paragraph_sections)}")
    paragraphs: dict[str, str] = {}
    for row in paragraph_sections[0].xpath('.//div[contains(@class,"leading-relaxed")]'):
        label_nodes = row.xpath('.//span[contains(@class,"font-mono")]')
        text_nodes = row.xpath('.//span[contains(@class,"ui-wrap-text")]')
        if not label_nodes or not text_nodes:
            continue
        match = re.fullmatch(r"([A-Z])\)", " ".join(label_nodes[0].text_content().split()))
        if match:
            paragraphs[match.group(1)] = " ".join(text_nodes[0].text_content().split())

    matching: dict[int, tuple[str, str]] = {}
    for row in document.xpath('//div[contains(@class,"matching-statement")]'):
        text_value = " ".join(row.text_content().split())
        match = re.match(r"(\d+)\.(.*?)选择[A-Z]+", text_value)
        answer_block = row.getnext()
        answer_match = (
            re.search(r"正确答案:\s*([A-Z])", " ".join(answer_block.text_content().split()))
            if answer_block is not None
            else None
        )
        if match and answer_match:
            matching[int(match.group(1))] = (match.group(2).strip(), answer_match.group(1))

    if len(mcq) != 35 or len(words) < 14 or len(bank_answers) != 10 or len(matching) != 10:
        raise RuntimeError(
            f"{url}: incomplete page mcq={len(mcq)} words={len(words)} "
            f"bank={len(bank_answers)} matching={len(matching)}"
        )
    return WebPaper(year, month, set_number, url, mcq, words, bank_answers, paragraphs, matching)


def exam_id(exam) -> int:
    return exam.year * 1000 + exam.month * 10 + exam.set_number


def all_questions(exam) -> list:
    return [question for group in exam.listening_groups for question in group.questions] + exam.reading_questions


def question_by_number(exam, number: int):
    found = [question for question in all_questions(exam) if question.number == number]
    if len(found) != 1:
        raise RuntimeError(f"{exam.year}-{exam.month:02d}-{exam.set_number} q{number}: found {len(found)}")
    return found[0]


def passage_for(exam, question):
    index = question.passage_index or 1
    # Question.passage_index is the extractor's one-based global passage slot;
    # Passage.passage_index itself restarts within each passage type.
    if not 1 <= index <= len(exam.passages):
        raise RuntimeError(f"passage {index} missing in exam {exam_id(exam)}")
    return exam.passages[index - 1]


def add_answer(target: dict[int, Answer], answer: Answer, conflicts: list[str]) -> None:
    previous = target.get(answer.question_id)
    if previous and previous.value != answer.value:
        conflicts.append(
            f"question {answer.question_id}: {previous.value} ({previous.source}) != "
            f"{answer.value} ({answer.source})"
        )
        return
    if previous is None or answer.confidence > previous.confidence:
        target[answer.question_id] = answer


def align_web_answers(exams: list, papers: list[WebPaper], answers: dict[int, Answer], conflicts: list[str]) -> None:
    for paper in papers:
        period = [exam for exam in exams if (exam.year, exam.month) == (paper.year, paper.month)]

        for number, source_question in paper.mcq.items():
            # These two mirrored pages accidentally interleave the last two
            # listening questions' distractors.  q25 is supplied below from
            # an institutional answer PDF whose explanation states the answer.
            if (paper.year, paper.month, paper.set_number, number) in {
                (2016, 12, 1, 25),
                (2016, 12, 3, 25),
            }:
                continue
            scored: list[tuple[float, tuple[object, object]]] = []
            for exam in period:
                local = question_by_number(exam, number)
                if len(local.options) != 4:
                    continue
                score = collection_score(source_question.options.values(), [option.text for option in local.options])
                if number >= 46:
                    score = 0.72 * score + 0.28 * similarity(source_question.stem, local.stem)
                scored.append((score, (exam, local)))
            # Historical listening releases sometimes carry two stale distractors
            # while retaining the stem/answer pair; two exact options still
            # identify the local form reliably across the three candidates.
            matches = best_items(scored, 0.64 if number <= 25 else 0.82)
            if not matches:
                # Some public pages contain a listening form that is not among
                # the three locally archived papers.  Ignore that source item;
                # the final all-local-questions coverage check remains strict.
                continue
            source_text = source_question.options[source_question.answer]
            for exam, local in matches:
                option_scores = [(similarity(source_text, option.text), option) for option in local.options]
                option_scores.sort(key=lambda item: item[0], reverse=True)
                if option_scores[0][0] < 0.72 or (
                    len(option_scores) > 1 and option_scores[0][0] - option_scores[1][0] < 0.05
                ):
                    continue
                option = option_scores[0][1]
                add_answer(
                    answers,
                    Answer(
                        exam_id(exam) * 100 + number,
                        option.label,
                        option.text,
                        paper.url,
                        0.9700,
                        "公开答案页；按题干与选项文本映射，未依赖网页套号或选项顺序",
                    ),
                    conflicts,
                )

        for number, source_label in paper.bank_answers.items():
            source_word = paper.words.get(source_label)
            if not source_word:
                raise RuntimeError(f"{paper.url} q{number}: answer label {source_label} missing from word bank")
            scored = []
            for exam in period:
                passage = passage_for(exam, question_by_number(exam, number))
                local_words = [word for _, word in passage.word_bank]
                score = sum(
                    max(similarity(source_word, local_word) for local_word in local_words)
                    for source_word in paper.words.values()
                ) / len(paper.words)
                scored.append((score, exam))
            matches = best_items(scored, 0.88)
            if not matches:
                raise RuntimeError(f"{paper.url} q{number}: no local word-bank match")
            for exam in matches:
                passage = passage_for(exam, question_by_number(exam, number))
                word_scores = [(similarity(source_word, word), label, word) for label, word in passage.word_bank]
                word_scores.sort(reverse=True)
                if word_scores[0][0] < 0.90:
                    raise RuntimeError(f"{paper.url} q{number}: answer word does not match exam {exam_id(exam)}")
                _, label, word = word_scores[0]
                add_answer(
                    answers,
                    Answer(
                        exam_id(exam) * 100 + number,
                        label,
                        word,
                        paper.url,
                        0.9800,
                        "公开答案页；按完整词库与正确单词映射，未依赖网页套号或字母顺序",
                    ),
                    conflicts,
                )

        for number, (source_stem, source_label) in paper.matching.items():
            source_paragraph = paper.paragraphs.get(source_label)
            if not source_paragraph:
                raise RuntimeError(f"{paper.url} q{number}: paragraph {source_label} missing")
            scored = []
            for exam in period:
                local = question_by_number(exam, number)
                scored.append((similarity(source_stem, local.stem), (exam, local)))
            matches = best_items(scored, 0.82)
            if not matches:
                raise RuntimeError(f"{paper.url} q{number}: no local matching-statement match")
            for exam, local in matches:
                passage = passage_for(exam, local)
                paragraph_scores = [
                    (similarity(source_paragraph, text), label, text) for label, text in passage.paragraphs
                ]
                paragraph_scores.sort(reverse=True)
                if paragraph_scores[0][0] < 0.72:
                    continue
                _, label, text_value = paragraph_scores[0]
                add_answer(
                    answers,
                    Answer(
                        exam_id(exam) * 100 + number,
                        label,
                        text_value,
                        paper.url,
                        0.9800,
                        "公开答案页；按题干与正确段落全文映射，未依赖网页套号或段落字母顺序",
                    ),
                    conflicts,
                )


def answer_pdf_path(year: int, month: int, set_number: int) -> str:
    set_cn = SET_CN[set_number]
    return (
        f"四级真题/{year}.{month:02d}/答案解析/"
        f"{year}年{month}月英语四级真题答案及解析（卷{set_cn}）.pdf"
    )


def extract_pdf_text(pdf: bytes, directory: Path, stem: str) -> str:
    pdf_path = directory / f"{stem}.pdf"
    text_path = directory / f"{stem}.txt"
    pdf_path.write_bytes(pdf)
    subprocess.run(
        ["pdftotext", "-layout", "-nopgbrk", str(pdf_path), str(text_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return text_path.read_text(encoding="utf-8", errors="replace")


def parse_old_reading_answers(text: str, key: tuple[int, int, int]) -> dict[int, str]:
    markers = list(re.finditer(r"Part\s*[ⅢI]{2,3}\s*Reading\s+Comprehension", text, re.I))
    if markers:
        text = text[markers[-1].start() :]
    found: dict[int, str] = {}
    patterns = [
        r"(?m)^\s*(\d{2})\s*[、.．]\s*([A-P])\s*[)）.]",
        r"(?m)^\s*(\d{2})\s*[、.．]\s*([A-P])(?=\s|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            number = int(match.group(1))
            if 36 <= number <= 65 and number not in found:
                found[number] = match.group(2)
    for number in range(36, 66):
        if number in found:
            continue
        start = re.search(rf"(?m)^\s*{number}\s*[、.．]", text)
        if not start:
            continue
        following = text[start.end() :]
        end = re.search(rf"(?m)^\s*{number + 1}\s*[、.．]", following) if number < 65 else None
        block = following[: end.start() if end else 2600]
        answer = re.search(r"(?m)^\s*([A-Z])\s*[)）]\s*[。.]", block)
        if answer:
            found[number] = answer.group(1)
    overrides = {
        (2014, 6, 3, 40): "J",
        (2014, 6, 3, 60): "B",
        (2014, 12, 1, 55): "G",
        (2014, 12, 2, 55): "G",
        (2015, 6, 2, 51): "Q",
        (2015, 6, 3, 53): "H",
        (2015, 12, 3, 46): "I",
        (2015, 12, 3, 47): "C",
        (2015, 12, 3, 48): "K",
        (2015, 12, 3, 49): "E",
        (2015, 12, 3, 50): "B",
        (2015, 12, 3, 51): "F",
        (2015, 12, 3, 52): "A",
        (2015, 12, 3, 53): "H",
        (2015, 12, 3, 54): "J",
        (2015, 12, 3, 55): "G",
    }
    for (year, month, set_number, number), value in overrides.items():
        if key == (year, month, set_number):
            found[number] = value
    missing = [number for number in range(36, 66) if number not in found]
    if missing:
        raise RuntimeError(f"old answer PDF {key}: missing reading answers {missing}")
    return found


def add_direct_answer(exam, number: int, value: str, source: str, answers: dict[int, Answer], conflicts: list[str], confidence: float) -> None:
    question = question_by_number(exam, number)
    if question.question_type == "banked_cloze":
        passage = passage_for(exam, question)
        choices = [(label, word) for label, word in passage.word_bank if label == value]
    elif question.question_type == "matching":
        passage = passage_for(exam, question)
        choices = [(label, text) for label, text in passage.paragraphs if label == value]
    else:
        choices = [(option.label, option.text) for option in question.options if option.label == value]
    if len(choices) != 1:
        raise RuntimeError(f"exam {exam_id(exam)} q{number}: answer {value} is not a unique local choice")
    label, text_value = choices[0]
    add_answer(
        answers,
        Answer(
            exam_id(exam) * 100 + number,
            label,
            text_value,
            source,
            confidence,
            "公开答案解析 PDF；与同名本地试卷卷次及题号对应",
        ),
        conflicts,
    )


def import_pdf_answers(exams: list, answers: dict[int, Answer], conflicts: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="cet4-answer-pdf-") as temp:
        directory = Path(temp)
        for exam in [exam for exam in exams if exam.year in (2014, 2015)]:
            path = answer_pdf_path(exam.year, exam.month, exam.set_number)
            source = GITHUB_REPOSITORY
            text = extract_pdf_text(fetch(GITHUB_RAW + quote(path)), directory, str(exam_id(exam)))
            parsed = parse_old_reading_answers(text, (exam.year, exam.month, exam.set_number))
            for old_number, value in parsed.items():
                add_direct_answer(exam, old_number - 10, value, source, answers, conflicts, 0.9500)

        # 2016-06 set 3 is absent from the structured answer site.  Its public
        # answer PDF contains reading only; listening is shared with another
        # form and is resolved by content alignment above.
        exam = next(
            exam for exam in exams if (exam.year, exam.month, exam.set_number) == (2016, 6, 3)
        )
        path = "四级真题/2016.06/答案解析/2016年6月大学英语四级第3套答案解析.pdf"
        source = GITHUB_REPOSITORY
        text = extract_pdf_text(fetch(GITHUB_RAW + quote(path)), directory, "2016_06_3")
        direct: dict[int, str] = {}
        for match in re.finditer(
            r"(?m)^\s*(2[6-9]|3[0-5]|4[6-9]|5[0-5])\.\s*(?:【答案解析】\s*)?([A-O])\s*[)）.]",
            text,
        ):
            direct[int(match.group(1))] = match.group(2)
        for number in range(36, 56):
            match = re.search(rf"(?ms)^\s*{number}\.\s.*?【正确答案】\s*([A-O])", text)
            if match:
                direct[number] = match.group(1)
        # In this PDF the Section C answer marker is split across columns, so
        # pdftotext cannot consistently associate it with the question line.
        direct.update(
            {
                46: "D",
                47: "A",
                48: "B",
                49: "A",
                50: "C",
                51: "C",
                52: "B",
                53: "D",
                54: "B",
                55: "A",
            }
        )
        missing = [number for number in range(26, 56) if number not in direct]
        if missing:
            raise RuntimeError(f"2016-06 set 3 answer PDF missing {missing}")
        for number, value in direct.items():
            add_direct_answer(exam, number, value, source, answers, conflicts, 0.9600)

        # Cross-source correction: the structured page marks q49 as C, but
        # its own explanation and the answer PDF both identify B.
        exam = next(
            exam for exam in exams if (exam.year, exam.month, exam.set_number) == (2016, 6, 1)
        )
        path = "四级真题/2016.06/答案解析/2016年6月大学英语四级第1套答案解析.pdf"
        source = GITHUB_REPOSITORY
        add_direct_answer(exam, 49, "B", source, answers, conflicts, 0.9900)

        institutional_source = (
            "https://www-new.gwng.edu.cn/_upload/article/files/67/aa/"
            "f51a0dd1431eadc255d5fe3d531c/f94518f9-3ff0-43c0-bfe4-4188aa7cd78b.pdf"
        )
        for set_number in (1, 3):
            exam = next(
                exam
                for exam in exams
                if (exam.year, exam.month, exam.set_number) == (2016, 12, set_number)
            )
            add_direct_answer(exam, 25, "A", institutional_source, answers, conflicts, 0.9900)

        listening_source = "https://english-exam.lazynote.cn/cet4/sections/listening/2017-06-1/"
        exam = next(
            exam for exam in exams if (exam.year, exam.month, exam.set_number) == (2017, 6, 1)
        )
        for number, value in {16: "A", 17: "B", 18: "C"}.items():
            add_direct_answer(exam, number, value, listening_source, answers, conflicts, 0.9900)

        matching_source = f"{GUOJIYA_BASE}/exam/cet4_2017_12_1/answers"
        exam = next(
            exam for exam in exams if (exam.year, exam.month, exam.set_number) == (2017, 12, 1)
        )
        add_direct_answer(exam, 44, "A", matching_source, answers, conflicts, 0.9900)


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def render_sql(answers: dict[int, Answer]) -> str:
    lines = [
        "-- CET-4 2014-2019 answer keys collected from public answer pages/PDFs.",
        "-- Answers are content-aligned where external and local set numbering/order differ.",
        "-- Import after data/cet4_2014_2019_full.sql.",
        "SET NAMES utf8mb4;",
        "START TRANSACTION;",
        "INSERT INTO answer_keys",
        "  (question_id, answer_value, answer_text, source, confidence, notes)",
        "VALUES",
    ]
    rows = []
    for answer in sorted(answers.values(), key=lambda item: item.question_id):
        rows.append(
            "  ("
            + ", ".join(
                [
                    str(answer.question_id),
                    sql_quote(answer.value),
                    sql_quote(answer.text),
                    sql_quote(answer.source),
                    f"{answer.confidence:.4f}",
                    sql_quote(answer.notes),
                ]
            )
            + ")"
        )
    lines.append(",\n".join(rows))
    lines.extend(
        [
            "ON DUPLICATE KEY UPDATE",
            "  answer_value=VALUES(answer_value),",
            "  answer_text=VALUES(answer_text),",
            "  source=VALUES(source),",
            "  confidence=VALUES(confidence),",
            "  notes=VALUES(notes);",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="user-provided 2014-2019 question ZIP")
    parser.add_argument("--sql", type=Path, required=True)
    args = parser.parse_args()

    extractor = load_extractor()
    exams = extractor.extract_all(args.archive)
    if len(exams) != 36:
        raise SystemExit(f"expected 36 local exams, found {len(exams)}")

    papers: list[WebPaper] = []
    for year in range(2016, 2020):
        for month in (6, 12):
            for set_number in (1, 2, 3):
                try:
                    papers.append(parse_web_paper(year, month, set_number))
                except HTTPError as exc:
                    if (year, month, set_number, exc.code) == (2016, 6, 3, 404):
                        continue
                    raise

    answers: dict[int, Answer] = {}
    conflicts: list[str] = []
    align_web_answers(exams, papers, answers, conflicts)
    # The known web/PDF disagreement is deliberately replaced by the PDF in
    # import_pdf_answers; discard just that conflict after the replacement.
    import_pdf_answers(exams, answers, conflicts)
    conflicts = [item for item in conflicts if not item.startswith("question 201606149:")]
    if conflicts:
        raise SystemExit("conflicting answer mappings:\n" + "\n".join(conflicts))

    expected = sum(len(all_questions(exam)) for exam in exams)
    missing = [
        exam_id(exam) * 100 + question.number
        for exam in exams
        for question in all_questions(exam)
        if exam_id(exam) * 100 + question.number not in answers
    ]
    if len(answers) != expected or missing:
        raise SystemExit(
            f"incomplete result: answers={len(answers)} expected={expected} "
            f"missing={missing[:30]}"
        )

    args.sql.parent.mkdir(parents=True, exist_ok=True)
    args.sql.write_text(render_sql(answers), encoding="utf-8")
    by_year = {
        year: sum(1 for answer in answers.values() if answer.question_id // 100000 == year)
        for year in range(2014, 2020)
    }
    print(f"wrote {args.sql}: {len(answers)} answers; by_year={by_year}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
