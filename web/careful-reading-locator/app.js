const STORAGE_KEY = "cet4-locator-training-v2";

const dom = {};
let corpus = null;
let currentPassageIndex = 0;
let currentQuestionIndex = 0;
let pendingArticleSelection = null;
let pendingQuestionSelection = null;
let state = loadState();
let toastTimer = null;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheDom();
  bindEvents();
  try {
    const response = await fetch("data/corpus.json");
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
    "pairSelectionButton", "cancelSelectionButton", "questionNav", "questionBadge",
    "questionStatus", "questionStem", "questionSelectionToolbar", "questionSelectionPreview",
    "useAsLocatorButton", "useAsPhraseButton", "cancelQuestionSelectionButton",
    "optionsDetails", "optionsList", "locatorChips", "noLocatorButton",
    "locatorSentenceButton", "evidenceList", "pairDraft", "pairList", "propositionInput",
    "answerLocked", "answerRevealed", "revealAnswerButton", "answerLetter", "answerText",
    "previousButton", "completeButton", "toast"
  ].forEach((id) => { dom[id] = document.getElementById(id); });
}

function bindEvents() {
  dom.passageSelect.addEventListener("change", () => {
    currentPassageIndex = Number(dom.passageSelect.value);
    currentQuestionIndex = 0;
    hideSelectionToolbars();
    renderAll();
  });
  dom.modeSelect.addEventListener("change", applyMode);
  dom.questionNav.addEventListener("click", (event) => {
    const button = event.target.closest("[data-question-index]");
    if (!button) return;
    currentQuestionIndex = Number(button.dataset.questionIndex);
    hideSelectionToolbars();
    renderAll();
  });

  dom.articleBody.addEventListener("mouseup", captureArticleSelection);
  dom.articleBody.addEventListener("click", chooseLocatorSentence);
  dom.saveSelectionButton.addEventListener("click", savePendingEvidence);
  dom.pairSelectionButton.addEventListener("click", finishPhrasePair);
  dom.cancelSelectionButton.addEventListener("click", hideArticleToolbar);

  const questionCard = dom.questionStem.closest(".question-card");
  questionCard.addEventListener("mouseup", captureQuestionSelection);
  dom.useAsLocatorButton.addEventListener("click", useQuestionSelectionAsLocator);
  dom.useAsPhraseButton.addEventListener("click", useQuestionSelectionAsPhrase);
  dom.cancelQuestionSelectionButton.addEventListener("click", hideQuestionToolbar);

  dom.optionsList.addEventListener("click", handleOptionClick);
  dom.locatorChips.addEventListener("click", removeLocator);
  dom.noLocatorButton.addEventListener("click", toggleNoLocator);
  dom.locatorSentenceButton.addEventListener("click", () => {
    dom.articleBody.focus();
    dom.articleBody.classList.add("awaiting-sentence");
    showToast("请点击左侧文章中最先定位到的句子");
  });
  dom.evidenceList.addEventListener("click", removeEvidence);
  dom.pairDraft.addEventListener("click", clearPairDraft);
  dom.pairList.addEventListener("click", removePair);
  dom.propositionInput.addEventListener("input", () => updateCurrent({ proposition: dom.propositionInput.value }));
  dom.clearEvidenceButton.addEventListener("click", clearEvidence);
  dom.revealAnswerButton.addEventListener("click", revealAnswer);
  dom.previousButton.addEventListener("click", previousQuestion);
  dom.completeButton.addEventListener("click", completeAndNext);
  dom.exportButton.addEventListener("click", exportProgress);
  dom.importInput.addEventListener("change", importProgress);

  document.addEventListener("mousedown", (event) => {
    if (!dom.selectionToolbar.contains(event.target) && !dom.articleBody.contains(event.target)) hideArticleToolbar();
    if (!dom.questionSelectionToolbar.contains(event.target) && !questionCard.contains(event.target)) hideQuestionToolbar();
  });
}

function passage() { return corpus.passages[currentPassageIndex]; }
function question() { return passage().questions[currentQuestionIndex]; }
function recordKey() { return `${passage().id}:${question().id}`; }
function defaultRecord() {
  return {
    locators: [], noLocator: false, locatorSentence: null, evidence: [],
    pairDraftSource: "", pairs: [], selectedAnswer: "", proposition: "",
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
  dom.passageSelect.innerHTML = corpus.passages.map((item, index) =>
    `<option value="${index}">${item.year} 年 ${item.month} 月 · 第 ${item.set} 套 · Passage ${item.passage}</option>`
  ).join("");
  dom.datasetStats.textContent = `${corpus.meta.passageCount} 篇去重文章 · ${corpus.meta.questionCount} 道题 · 已恢复真实分段`;
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

function renderQuestion() {
  const item = question();
  const saved = record();
  dom.questionBadge.textContent = `Q${item.number}`;
  dom.questionStem.textContent = item.stem;
  dom.optionsList.innerHTML = item.options.map((option) => {
    const classes = [saved.selectedAnswer === option.label ? "selected" : ""];
    if (saved.revealed && option.label === item.answer.label) classes.push("correct");
    if (saved.revealed && saved.selectedAnswer === option.label && option.label !== item.answer.label) classes.push("wrong");
    return `<li class="${classes.join(" ")}" data-option-label="${escapeHtml(option.label)}">
      <span class="option-letter">${escapeHtml(option.label)}.</span>
      <span class="option-text">${escapeHtml(option.text)}</span>
      <button class="option-pair-button" data-option-pair="${escapeHtml(option.label)}" type="button">配对</button>
    </li>`;
  }).join("");
  dom.propositionInput.value = saved.proposition;
  dom.answerLocked.hidden = saved.revealed;
  dom.answerRevealed.hidden = !saved.revealed;
  dom.answerLetter.textContent = item.answer.label || "—";
  dom.answerText.textContent = item.answer.text || item.options.find((option) => option.label === item.answer.label)?.text || "暂无答案文本";
  dom.optionsDetails.open = dom.modeSelect.value !== "blind";
  renderLocators();
  renderLocatorSentence();
  renderEvidenceList();
  renderPairDraft();
  renderPairList();
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
  return Boolean(saved && (saved.locators?.length || saved.noLocator || saved.locatorSentence || saved.selectedAnswer || saved.proposition || saved.revealed || saved.evidence?.length || saved.pairs?.length));
}
function renderProgress() {
  const completed = passage().questions.filter((item) => state.records[`${passage().id}:${item.id}`]?.completed).length;
  dom.progressText.textContent = `${completed} / ${passage().questions.length}`;
  dom.progressBar.style.width = `${(completed / passage().questions.length) * 100}%`;
}

function captureQuestionSelection(event) {
  if (event.target.closest("button") || event.target.closest("summary")) return;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return;
  const range = selection.getRangeAt(0);
  const card = dom.questionStem.closest(".question-card");
  if (!card.contains(range.commonAncestorContainer)) return;
  const text = selection.toString().trim();
  if (!text) return;
  pendingQuestionSelection = text;
  dom.questionSelectionPreview.textContent = shorten(text);
  positionToolbar(dom.questionSelectionToolbar, range.getBoundingClientRect(), 430);
}

function useQuestionSelectionAsLocator() {
  if (!pendingQuestionSelection) return;
  const saved = record();
  if (!saved.locators.includes(pendingQuestionSelection)) saved.locators.push(pendingQuestionSelection);
  saved.noLocator = false;
  saveState();
  clearBrowserSelection();
  hideQuestionToolbar();
  renderLocators(); renderNav(); renderStatus();
  showToast("已从题干保存定位词");
}

function useQuestionSelectionAsPhrase() {
  if (!pendingQuestionSelection) return;
  record().pairDraftSource = pendingQuestionSelection;
  saveState();
  clearBrowserSelection();
  hideQuestionToolbar();
  renderPairDraft();
  showToast("现在去左侧原文划取对应表达");
}

function renderLocators() {
  const saved = record();
  if (saved.noLocator) {
    dom.locatorChips.className = "locator-chips";
    dom.locatorChips.innerHTML = '<span class="locator-chip no-locator-chip">无硬定位词</span>';
    dom.noLocatorButton.textContent = "取消“无硬定位词”";
    return;
  }
  dom.noLocatorButton.textContent = "本题没有硬定位词";
  if (!saved.locators.length) {
    dom.locatorChips.className = "locator-chips empty-state";
    dom.locatorChips.textContent = "尚未划取定位词";
    return;
  }
  dom.locatorChips.className = "locator-chips";
  dom.locatorChips.innerHTML = saved.locators.map((value, index) =>
    `<span class="locator-chip">${escapeHtml(value)}<button data-remove-locator="${index}" type="button" aria-label="删除定位词">×</button></span>`
  ).join("");
}

function removeLocator(event) {
  const button = event.target.closest("[data-remove-locator]");
  if (!button) return;
  record().locators.splice(Number(button.dataset.removeLocator), 1);
  saveState(); renderLocators(); renderNav(); renderStatus();
}
function toggleNoLocator() {
  const saved = record();
  saved.noLocator = !saved.noLocator;
  if (saved.noLocator) saved.locators = [];
  saveState(); renderLocators(); renderNav(); renderStatus();
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
  dom.pairSelectionButton.hidden = !record().pairDraftSource;
  positionToolbar(dom.selectionToolbar, range.getBoundingClientRect(), record().pairDraftSource ? 520 : 390);
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

function finishPhrasePair() {
  if (!pendingArticleSelection || !record().pairDraftSource) return;
  record().pairs.push({ id: makeId(), source: record().pairDraftSource, article: pendingArticleSelection.text });
  record().pairDraftSource = "";
  saveState();
  clearBrowserSelection(); hideArticleToolbar();
  renderPairDraft(); renderPairList(); renderNav(); renderStatus();
  showToast("同义替换已配对");
}

function handleOptionClick(event) {
  const pairButton = event.target.closest("[data-option-pair]");
  if (pairButton) {
    const option = question().options.find((item) => item.label === pairButton.dataset.optionPair);
    if (!option) return;
    record().pairDraftSource = option.text;
    saveState(); renderPairDraft();
    showToast("现在去左侧原文划取对应表达");
    event.stopPropagation();
    return;
  }
  if (!window.getSelection()?.isCollapsed) return;
  const row = event.target.closest("[data-option-label]");
  if (!row) return;
  updateCurrent({ selectedAnswer: row.dataset.optionLabel });
  renderQuestion();
  showToast(`已选择 ${row.dataset.optionLabel}`);
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

function renderPairDraft() {
  const source = record().pairDraftSource;
  if (!source) {
    dom.pairDraft.className = "pair-draft empty-state";
    dom.pairDraft.textContent = "在题干中划取表达，或点击选项右侧的“配对”按钮。";
    return;
  }
  dom.pairDraft.className = "pair-draft active";
  dom.pairDraft.innerHTML = `<span><small>已选题目表达</small>${escapeHtml(source)}</span><button type="button" data-clear-pair-draft>×</button><strong>现在去左侧划取原文表达</strong>`;
}
function clearPairDraft(event) {
  if (!event.target.closest("[data-clear-pair-draft]")) return;
  record().pairDraftSource = "";
  saveState(); renderPairDraft();
}
function renderPairList() {
  dom.pairList.innerHTML = record().pairs.map((item) =>
    `<div class="pair-item"><span>${escapeHtml(item.source)}</span><b>⇄</b><span>${escapeHtml(item.article)}</span><button type="button" data-remove-pair="${escapeHtml(item.id)}" aria-label="删除配对">×</button></div>`
  ).join("");
}
function removePair(event) {
  const button = event.target.closest("[data-remove-pair]");
  if (!button) return;
  record().pairs = record().pairs.filter((item) => item.id !== button.dataset.removePair);
  saveState(); renderPairList(); renderNav(); renderStatus();
}

function revealAnswer() {
  if (!record().selectedAnswer) return showToast("请先用鼠标点击一个选项");
  updateCurrent({ revealed: true });
  renderQuestion();
  showToast(record().selectedAnswer === question().answer.label ? "选择正确" : "请对照证据检查同义替换");
}
function previousQuestion() {
  currentQuestionIndex = currentQuestionIndex > 0 ? currentQuestionIndex - 1 : passage().questions.length - 1;
  hideSelectionToolbars(); renderAll();
}
function completeAndNext() {
  const saved = record();
  const missing = [];
  if (!saved.locators.length && !saved.noLocator) missing.push("定位词");
  if (!saved.locatorSentence) missing.push("粗定位句");
  if (!saved.evidence.length) missing.push("文章证据");
  if (!saved.selectedAnswer) missing.push("最终选项");
  saved.completed = true;
  saveState();
  showToast(missing.length ? `已完成；可补：${missing.join("、")}` : "本题训练已完成");
  if (currentQuestionIndex < passage().questions.length - 1) currentQuestionIndex += 1;
  hideSelectionToolbars(); renderAll();
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
function hideQuestionToolbar() { pendingQuestionSelection = null; dom.questionSelectionToolbar.hidden = true; }
function hideSelectionToolbars() { hideArticleToolbar(); hideQuestionToolbar(); }
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
