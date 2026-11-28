const STORAGE_KEY = "cet4-locator-training-v2";

const dom = {};
let corpus = null;
let currentPassageIndex = 0;
let currentQuestionIndex = 0;
let pendingArticleSelection = null;
let state = loadState();
let toastTimer = null;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheDom();
  bindEvents();
  try {
    const response = await fetch("data/corpus.json?v=2014-2026-150-underlines", { cache: "no-store" });
    if (!response.ok) throw new Error("题库文件读取失败");
    corpus = await response.json();
    populatePassageSelect();
    selectDefaultPassage();
    renderAll();
  } catch (error) {
    dom.datasetStats.textContent = "题库载入失败，请刷新页面";
    showToast(error.message);
  }
}

function cacheDom() {
  [
    "modeSelect", "exportButton", "importInput", "datasetStats", "passageSelect",
    "progressText", "progressBar", "passageMeta", "passageTitle", "clearEvidenceButton",
    "articleBody", "selectionToolbar", "selectionPreview", "saveSelectionButton",
    "cancelSelectionButton", "questionNav", "questionBadge",
    "questionStatus", "questionStem", "clearStemButton",
    "optionsDetails", "optionsList", "clearOptionMarksButton",
    "locatorSentenceButton", "evidenceList", "propositionInput",
    "answerLocked", "answerRevealed", "revealAnswerButton", "answerLetter", "answerText",
    "previousButton", "completeButton", "toast"
  ].forEach((id) => { dom[id] = document.getElementById(id); });
}

function bindEvents() {
  dom.passageSelect.addEventListener("change", () => {
    currentPassageIndex = Number(dom.passageSelect.value);
    currentQuestionIndex = 0;
    hideArticleToolbar();
    renderAll();
  });
  dom.modeSelect.addEventListener("change", applyMode);
  dom.questionNav.addEventListener("click", (event) => {
    const button = event.target.closest("[data-question-index]");
    if (!button) return;
    currentQuestionIndex = Number(button.dataset.questionIndex);
    hideArticleToolbar();
    renderAll();
  });

  dom.articleBody.addEventListener("mouseup", captureArticleSelection);
  dom.articleBody.addEventListener("click", chooseLocatorSentence);
  dom.saveSelectionButton.addEventListener("click", savePendingEvidence);
  dom.cancelSelectionButton.addEventListener("click", hideArticleToolbar);
  dom.questionStem.addEventListener("mouseup", captureStemSelection);
  dom.clearStemButton.addEventListener("click", () => {
    updateCurrent({ stemUnderlines: [] });
    renderQuestionStem(question(), record());
  });

  dom.optionsList.addEventListener("mouseup", captureOptionSelection);
  dom.optionsList.addEventListener("click", handleOptionClick);
  dom.clearOptionMarksButton.addEventListener("click", () => {
    updateCurrent({ optionUnderlines: {} });
    renderOptions(question(), record());
  });
  dom.locatorSentenceButton.addEventListener("click", () => {
    dom.articleBody.focus();
    dom.articleBody.classList.add("awaiting-sentence");
    showToast("请点击左侧文章中最先定位到的句子");
  });
  dom.evidenceList.addEventListener("click", removeEvidence);
  dom.propositionInput.addEventListener("input", () => updateCurrent({ proposition: dom.propositionInput.value }));
  dom.clearEvidenceButton.addEventListener("click", clearEvidence);
  dom.revealAnswerButton.addEventListener("click", revealAnswer);
  dom.previousButton.addEventListener("click", previousQuestion);
  dom.completeButton.addEventListener("click", completeAndNext);
  dom.exportButton.addEventListener("click", exportProgress);
  dom.importInput.addEventListener("change", importProgress);

  document.addEventListener("mousedown", (event) => {
    if (!dom.selectionToolbar.contains(event.target) && !dom.articleBody.contains(event.target)) hideArticleToolbar();
  });
}

function passage() { return corpus.passages[currentPassageIndex]; }
function question() { return passage().questions[currentQuestionIndex]; }
function recordKey() { return `${passage().id}:${question().id}`; }
function defaultRecord() {
  return {
    stemUnderlines: [], optionUnderlines: {}, locatorSentence: null, evidence: [],
    selectedAnswer: "", proposition: "",
    revealed: false, completed: false,
  };
}
function record() {
  if (!state.records[recordKey()]) state.records[recordKey()] = defaultRecord();
  return state.records[recordKey()];
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return saved?.version === 2 && saved.records ? saved : { version: 2, records: {} };
  } catch (_) {
    return { version: 2, records: {} };
  }
}
function saveState() { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); }
function updateCurrent(patch) {
  Object.assign(record(), patch);
  saveState();
  renderProgress();
  renderNav();
  renderStatus();
}

function populatePassageSelect() {
  const groups = new Map();
  corpus.passages.forEach((item, index) => {
    if (!groups.has(item.year)) groups.set(item.year, []);
    groups.get(item.year).push(
      `<option value="${index}">${item.month} 月 · 第 ${item.set} 套 · Passage ${item.passage}</option>`
    );
  });
  dom.passageSelect.innerHTML = [...groups.entries()].map(([year, options]) =>
    `<optgroup label="${year} 年">${options.join("")}</optgroup>`
  ).join("");
  const years = corpus.passages.map((item) => item.year);
  const range = `${Math.min(...years)}–${Math.max(...years)}`;
  dom.datasetStats.textContent = `${range} · ${corpus.meta.passageCount} 篇去重文章 · ${corpus.meta.questionCount} 道题`;
}
function selectDefaultPassage() {
  const preferred = corpus.passages.findIndex((item) => item.year === 2024 && item.month === 12 && item.set === 2 && item.passage === 1);
  currentPassageIndex = preferred >= 0 ? preferred : 0;
  dom.passageSelect.value = String(currentPassageIndex);
}

function renderAll() {
  renderArticle();
  renderNav();
  renderQuestion();
  renderProgress();
  applyMode();
}

function articleStructure(text) {
  const paragraphs = [];
  const paragraphPattern = /[^\n]+(?:\n(?!\n)[^\n]+)*/g;
  let paragraphMatch;
  let globalSentence = 0;
  while ((paragraphMatch = paragraphPattern.exec(text)) !== null) {
    const raw = paragraphMatch[0].trim();
    if (!raw) continue;
    const paragraphStart = text.indexOf(raw, paragraphMatch.index);
    const sentences = [];
    const boundary = /[.!?](?:["'”’)]*)(?:\s+|$)(?=[A-Z0-9"'“‘(]|$)/g;
    let localStart = 0;
    let match;
    while ((match = boundary.exec(raw)) !== null) {
      const end = match.index + match[0].trimEnd().length;
      globalSentence += 1;
      sentences.push({
        start: paragraphStart + localStart,
        end: paragraphStart + end,
        paragraph: paragraphs.length + 1,
        sentenceInParagraph: sentences.length + 1,
        globalSentence,
      });
      localStart = match.index + match[0].length;
    }
    if (localStart < raw.length) {
      globalSentence += 1;
      sentences.push({
        start: paragraphStart + localStart,
        end: paragraphStart + raw.length,
        paragraph: paragraphs.length + 1,
        sentenceInParagraph: sentences.length + 1,
        globalSentence,
      });
    }
    paragraphs.push({ start: paragraphStart, end: paragraphStart + raw.length, sentences });
  }
  return paragraphs;
}

function renderArticle() {
  const item = passage();
  dom.passageMeta.textContent = `${item.year} 年 ${item.month} 月 · 第 ${item.set} 套 · PASSAGE ${item.passage} · ${item.paragraphCount || articleStructure(item.text).length} 段`;
  dom.passageTitle.textContent = item.title || `Passage ${item.passage}`;
  renderArticleHighlights();
}

function allEvidenceForPassage() {
  const entries = [];
  passage().questions.forEach((item, qIndex) => {
    const saved = state.records[`${passage().id}:${item.id}`];
    (saved?.evidence || []).forEach((evidence) => entries.push({ ...evidence, qIndex, number: item.number }));
  });
  return entries;
}

function renderArticleHighlights() {
  const text = passage().text;
  const evidence = allEvidenceForPassage().filter((item) => item.start < item.end);
  const selected = record().locatorSentence;
  const fragment = document.createDocumentFragment();
  articleStructure(text).forEach((paragraph) => {
    const block = document.createElement("p");
    block.className = "article-paragraph";
    block.dataset.paragraph = String(paragraph.sentences[0]?.paragraph || "");
    paragraph.sentences.forEach((sentence, index) => {
      if (index > 0) {
        const previous = paragraph.sentences[index - 1];
        block.appendChild(document.createTextNode(text.slice(previous.end, sentence.start)));
      }
      const wrapper = document.createElement("span");
      wrapper.className = "sentence";
      wrapper.dataset.start = String(sentence.start);
      wrapper.dataset.end = String(sentence.end);
      wrapper.dataset.paragraph = String(sentence.paragraph);
      wrapper.dataset.sentence = String(sentence.sentenceInParagraph);
      wrapper.dataset.globalSentence = String(sentence.globalSentence);
      if (selected?.globalSentence === sentence.globalSentence) wrapper.classList.add("locator-selected");
      appendHighlightedText(wrapper, text, sentence, evidence);
      block.appendChild(wrapper);
    });
    fragment.appendChild(block);
  });
  dom.articleBody.replaceChildren(fragment);
}

function appendHighlightedText(wrapper, text, sentence, evidence) {
  const boundaries = [...new Set([
    sentence.start, sentence.end,
    ...evidence.flatMap((item) => [Math.max(sentence.start, item.start), Math.min(sentence.end, item.end)])
      .filter((offset) => offset > sentence.start && offset < sentence.end),
  ])].sort((a, b) => a - b);
  for (let index = 0; index < boundaries.length - 1; index += 1) {
    const start = boundaries[index];
    const end = boundaries[index + 1];
    const covering = evidence.filter((item) => item.start <= start && item.end >= end);
    const node = document.createTextNode(text.slice(start, end));
    if (!covering.length) {
      wrapper.appendChild(node);
      continue;
    }
    const current = covering.find((item) => item.qIndex === currentQuestionIndex) || covering[0];
    const mark = document.createElement("mark");
    if (current.qIndex !== currentQuestionIndex) mark.className = "evidence-other";
    mark.title = covering.map((item) => `Q${item.number}`).join("、") + " 的证据";
    mark.appendChild(node);
    wrapper.appendChild(mark);
  }
}

function renderNav() {
  dom.questionNav.innerHTML = passage().questions.map((item, index) => {
    const saved = state.records[`${passage().id}:${item.id}`];
    const status = saved?.completed ? "complete" : hasWork(saved) ? "partial" : "";
    return `<button class="question-tab ${index === currentQuestionIndex ? "active" : ""} ${status}" data-question-index="${index}" type="button">Q${item.number}</button>`;
  }).join("");
}

function mergeUnderlineRanges(ranges) {
  const merged = [];
  for (const [start, end] of [...ranges].sort((a, b) => a[0] - b[0])) {
    const previous = merged.at(-1);
    if (previous && start <= previous[1]) {
      previous[1] = Math.max(previous[1], end);
    } else {
      merged.push([start, end]);
    }
  }
  return merged;
}

function validUnderlineRanges(text, ranges) {
  return Array.isArray(ranges) ? mergeUnderlineRanges(ranges.filter((range) => Array.isArray(range) && range.length === 2
    && range.every(Number.isInteger) && range[0] >= 0 && range[0] < range[1] && range[1] <= text.length)) : [];
}

function stemRanges(stem, saved) {
  // Older practice records saved manually chosen words as strings.
  const ranges = saved.stemUnderlines ?? (saved.locators || []).flatMap((word) => {
    const start = typeof word === "string" && word ? stem.indexOf(word) : -1;
    return start < 0 ? [] : [[start, start + word.length]];
  });
  return validUnderlineRanges(stem, ranges);
}

function renderUnderlines(element, text, ranges) {
  const fragment = document.createDocumentFragment();
  let cursor = 0;
  for (const [start, end] of ranges) {
    fragment.append(text.slice(cursor, start));
    const underline = document.createElement("u");
    underline.className = "manual-underline";
    underline.textContent = text.slice(start, end);
    fragment.append(underline);
    cursor = end;
  }
  fragment.append(text.slice(cursor));
  element.replaceChildren(fragment);
}

function renderQuestionStem(item, saved) {
  const ranges = stemRanges(item.stem, saved);
  renderUnderlines(dom.questionStem, item.stem, ranges);
  dom.clearStemButton.disabled = !ranges.length;
}

function selectedUnderlineRange(element) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) return null;
  const raw = range.toString();
  const text = raw.trim();
  if (!text) return null;

  const prefix = document.createRange();
  prefix.selectNodeContents(element);
  prefix.setEnd(range.startContainer, range.startOffset);
  const start = prefix.toString().length + raw.indexOf(text);
  return [start, start + text.length];
}

function captureStemSelection(event) {
  if (event.button !== 0) return;
  const range = selectedUnderlineRange(dom.questionStem);
  if (!range) return;
  const stem = question().stem;
  clearBrowserSelection();
  updateCurrent({ stemUnderlines: mergeUnderlineRanges([...stemRanges(stem, record()), range]) });
  renderQuestionStem(question(), record());
}

function captureOptionSelection(event) {
  if (event.button !== 0) return;
  const element = event.target.closest("[data-option-text]");
  if (!element) return;
  const range = selectedUnderlineRange(element);
  if (!range) return;
  const label = element.dataset.optionText;
  const option = question().options.find((item) => item.label === label);
  if (!option) return;
  const saved = record().optionUnderlines;
  const ranges = mergeUnderlineRanges([...validUnderlineRanges(option.text, saved?.[label]), range]);
  clearBrowserSelection();
  updateCurrent({ optionUnderlines: { ...saved, [label]: ranges } });
  renderUnderlines(element, option.text, ranges);
  dom.clearOptionMarksButton.disabled = false;
}

function renderOptions(item, saved) {
  dom.optionsList.innerHTML = item.options.map((option) => {
    const classes = [saved.selectedAnswer === option.label ? "selected" : ""];
    if (saved.revealed && option.label === item.answer.label) classes.push("correct");
    if (saved.revealed && saved.selectedAnswer === option.label && option.label !== item.answer.label) classes.push("wrong");
    return `<li class="${classes.join(" ")}">
      <button class="option-choice" data-answer-option="${escapeHtml(option.label)}" type="button"
        aria-pressed="${saved.selectedAnswer === option.label}" aria-label="选择 ${escapeHtml(option.label)} 项">
        ${escapeHtml(option.label)}
      </button>
      <span class="option-text" data-option-text="${escapeHtml(option.label)}"></span>
    </li>`;
  }).join("");
  let hasMarks = false;
  dom.optionsList.querySelectorAll("[data-option-text]").forEach((element, index) => {
    const { label, text } = item.options[index];
    const ranges = validUnderlineRanges(text, saved.optionUnderlines?.[label]);
    renderUnderlines(element, text, ranges);
    if (ranges.length) hasMarks = true;
  });
  dom.clearOptionMarksButton.disabled = !hasMarks;
}

function renderQuestion() {
  const item = question();
  const saved = record();
  dom.questionBadge.textContent = `Q${item.number}`;
  renderQuestionStem(item, saved);
  renderOptions(item, saved);
  dom.propositionInput.value = saved.proposition;
  dom.answerLocked.hidden = saved.revealed;
  dom.answerRevealed.hidden = !saved.revealed;
  dom.answerLetter.textContent = item.answer.label || "—";
  dom.answerText.textContent = item.answer.text || item.options.find((option) => option.label === item.answer.label)?.text || "暂无答案文本";
  dom.optionsDetails.open = dom.modeSelect.value !== "blind";
  renderLocatorSentence();
  renderEvidenceList();
  renderArticleHighlights();
  renderStatus();
}

function renderStatus() {
  const saved = record();
  dom.questionStatus.className = "status-pill";
  if (saved.completed) {
    dom.questionStatus.textContent = "已完成";
    dom.questionStatus.classList.add("complete");
  } else if (hasWork(saved)) dom.questionStatus.textContent = "进行中";
  else dom.questionStatus.textContent = "未开始";
}
function hasWork(saved) {
  return Boolean(saved && ((saved.stemUnderlines?.length ?? saved.locators?.length)
    || Object.values(saved.optionUnderlines ?? {}).some((ranges) => ranges?.length)
    || saved.locatorSentence || saved.selectedAnswer || saved.proposition || saved.revealed || saved.evidence?.length));
}
function renderProgress() {
  const completed = passage().questions.filter((item) => state.records[`${passage().id}:${item.id}`]?.completed).length;
  dom.progressText.textContent = `${completed} / ${passage().questions.length}`;
  dom.progressBar.style.width = `${(completed / passage().questions.length) * 100}%`;
}

function chooseLocatorSentence(event) {
  if (!window.getSelection()?.isCollapsed) return;
  const sentence = event.target.closest(".sentence");
  if (!sentence) return;
  const value = {
    globalSentence: Number(sentence.dataset.globalSentence),
    paragraph: Number(sentence.dataset.paragraph),
    sentence: Number(sentence.dataset.sentence),
  };
  updateCurrent({ locatorSentence: value });
  dom.articleBody.classList.remove("awaiting-sentence");
  renderLocatorSentence(); renderArticleHighlights();
  showToast(`粗定位：第 ${value.paragraph} 段第 ${value.sentence} 句`);
}
function renderLocatorSentence() {
  const value = record().locatorSentence;
  dom.locatorSentenceButton.textContent = value ? `第 ${value.paragraph} 段 · 第 ${value.sentence} 句（点击文章可改）` : "点击左侧原文中的句子";
  dom.locatorSentenceButton.classList.toggle("has-value", Boolean(value));
}

function captureArticleSelection(event) {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  if (!dom.articleBody.contains(range.commonAncestorContainer)) return;
  const start = endpointOffset(range.startContainer, range.startOffset);
  const end = endpointOffset(range.endContainer, range.endOffset);
  if (start === null || end === null || end <= start) return;
  const raw = passage().text.slice(start, end);
  const text = raw.trim();
  if (!text) return;
  const trim = raw.indexOf(text);
  pendingArticleSelection = { start: start + trim, end: start + trim + text.length, text };
  dom.selectionPreview.textContent = shorten(text);
  positionToolbar(dom.selectionToolbar, range.getBoundingClientRect(), 390);
  event.stopPropagation();
}

function endpointOffset(container, offset) {
  const element = container.nodeType === Node.ELEMENT_NODE ? container : container.parentElement;
  const sentence = element?.closest?.(".sentence");
  if (!sentence) return null;
  const partial = document.createRange();
  partial.selectNodeContents(sentence);
  partial.setEnd(container, offset);
  return Number(sentence.dataset.start) + partial.toString().length;
}

function savePendingEvidence() {
  if (!pendingArticleSelection) return;
  const saved = record();
  const duplicate = saved.evidence.some((item) => item.start === pendingArticleSelection.start && item.end === pendingArticleSelection.end);
  if (!duplicate) saved.evidence.push({ ...pendingArticleSelection, id: makeId() });
  saveState();
  clearBrowserSelection(); hideArticleToolbar();
  renderQuestion(); renderNav();
  showToast(duplicate ? "这段证据已经保存过了" : "已保存为本题证据");
}

function handleOptionClick(event) {
  const answerButton = event.target.closest("[data-answer-option]");
  if (!answerButton) return;
  const label = answerButton.dataset.answerOption;
  clearBrowserSelection();
  updateCurrent({ selectedAnswer: label });
  renderQuestion();
  dom.optionsList.querySelector('[aria-pressed="true"]')?.focus({ preventScroll: true });
  showToast(`已选择 ${label}`);
}

function renderEvidenceList() {
  const evidence = record().evidence;
  if (!evidence.length) {
    dom.evidenceList.className = "evidence-list empty-state";
    dom.evidenceList.textContent = "在左侧划取答案依据，然后点击“保存为本题证据”。";
    return;
  }
  dom.evidenceList.className = "evidence-list";
  dom.evidenceList.innerHTML = evidence.map((item) =>
    `<div class="evidence-item"><span>“${escapeHtml(item.text)}”</span><button type="button" data-remove-evidence="${escapeHtml(item.id)}" aria-label="删除证据">×</button></div>`
  ).join("");
}
function removeEvidence(event) {
  const button = event.target.closest("[data-remove-evidence]");
  if (!button) return;
  record().evidence = record().evidence.filter((item) => item.id !== button.dataset.removeEvidence);
  saveState(); renderQuestion(); renderNav();
}
function clearEvidence() {
  if (!record().evidence.length) return showToast("本题还没有划线证据");
  record().evidence = [];
  saveState(); renderQuestion(); renderNav();
  showToast("已清除本题全部划线");
}

function revealAnswer() {
  if (!record().selectedAnswer) return showToast("请先用鼠标点击一个选项");
  updateCurrent({ revealed: true });
  renderQuestion();
  showToast(record().selectedAnswer === question().answer.label ? "选择正确" : "请回到原文核对选项");
}
function previousQuestion() {
  currentQuestionIndex = currentQuestionIndex > 0 ? currentQuestionIndex - 1 : passage().questions.length - 1;
  hideArticleToolbar(); renderAll();
}
function completeAndNext() {
  const saved = record();
  const missing = [];
  if (!saved.locatorSentence) missing.push("粗定位句");
  if (!saved.evidence.length) missing.push("文章证据");
  if (!saved.selectedAnswer) missing.push("最终选项");
  saved.completed = true;
  saveState();
  showToast(missing.length ? `已完成；可补：${missing.join("、")}` : "本题训练已完成");
  if (currentQuestionIndex < passage().questions.length - 1) currentQuestionIndex += 1;
  hideArticleToolbar(); renderAll();
}

function applyMode() {
  document.body.classList.toggle("blind-mode", dom.modeSelect.value === "blind");
  document.body.classList.toggle("review-mode", dom.modeSelect.value === "review");
  if (dom.modeSelect.value === "review") renderQuestion();
}
function positionToolbar(toolbar, rect, desiredWidth) {
  const width = Math.min(desiredWidth, window.innerWidth - 20);
  toolbar.style.width = `${width}px`;
  toolbar.style.left = `${Math.max(10, Math.min(rect.left, window.innerWidth - width - 10))}px`;
  toolbar.style.top = `${Math.max(10, Math.min(rect.bottom + 9, window.innerHeight - 70))}px`;
  toolbar.hidden = false;
}
function hideArticleToolbar() { pendingArticleSelection = null; dom.selectionToolbar.hidden = true; }
function clearBrowserSelection() { window.getSelection()?.removeAllRanges(); }
function shorten(value) { return value.length > 54 ? `${value.slice(0, 54)}…` : value; }
function makeId() { return crypto.randomUUID?.() || `${Date.now()}-${Math.random()}`; }

function exportProgress() {
  const payload = { ...state, exportedAt: new Date().toISOString(), corpus: corpus.meta };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `cet4-定位训练-${new Date().toISOString().slice(0, 10)}.json`;
  link.click(); URL.revokeObjectURL(link.href);
  showToast("训练记录已导出");
}
async function importProgress(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    if (imported.version !== 2 || !imported.records) throw new Error("请导入新版训练记录");
    state = { version: 2, records: imported.records };
    saveState(); renderAll(); showToast("训练记录已导入");
  } catch (error) { showToast(`导入失败：${error.message}`); }
  finally { event.target.value = ""; }
}
function showToast(message) {
  dom.toast.textContent = message;
  dom.toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => dom.toast.classList.remove("show"), 2600);
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}
