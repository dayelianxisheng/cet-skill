(() => {
  "use strict";

  const DATA = Array.isArray(window.CET4_DATA) ? window.CET4_DATA : [];
  const POS = [
    { id: "noun", label: "n. 名词" },
    { id: "verb", label: "v. 动词" },
    { id: "adj", label: "adj. 形容词" },
    { id: "adv", label: "adv. 副词" },
    { id: "prep", label: "prep. 介词" },
    { id: "other", label: "其他" },
  ];
  const STORAGE_PREFIX = "cet4-pos-trainer-v1:";
  const LAST_SET_KEY = "cet4-pos-trainer:last-set";

  const els = {
    select: document.querySelector("#setSelect"),
    setCount: document.querySelector("#setCount"),
    label: document.querySelector("#currentLabel"),
    passage: document.querySelector("#passage"),
    intro: document.querySelector("#stageIntro"),
    task: document.querySelector("#taskArea"),
    reset: document.querySelector("#resetBtn"),
    analysisFile: document.querySelector("#analysisFile"),
    analysisStatus: document.querySelector("#analysisStatus"),
    speak: document.querySelector("#speakBtn"),
    toast: document.querySelector("#toast"),
    template: document.querySelector("#wordCardTemplate"),
  };

  let current = null;
  let state = null;
  let stage = 1;
  let sortEasyFirst = true;
  let toastTimer = null;
  let analysis = { version: 1, sets: {} };

  function blankState() {
    return { wordPos: {}, blankPos: {}, answers: {}, checkedWords: {} };
  }

  function loadState(setId) {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_PREFIX + setId));
      return { ...blankState(), ...(saved || {}) };
    } catch {
      return blankState();
    }
  }

  function saveState() {
    localStorage.setItem(STORAGE_PREFIX + current.id, JSON.stringify(state));
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function showToast(message) {
    clearTimeout(toastTimer);
    els.toast.textContent = message;
    els.toast.classList.add("show");
    toastTimer = setTimeout(() => els.toast.classList.remove("show"), 1900);
  }

  function speak(text) {
    if (!("speechSynthesis" in window)) {
      showToast("当前浏览器不支持语音朗读");
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text.replace(/\[(?:2[6-9]|3[0-5])\]/g, " blank "));
    utterance.lang = "en-US";
    utterance.rate = 0.88;
    const english = speechSynthesis.getVoices().find((voice) => voice.lang.startsWith("en"));
    if (english) utterance.voice = english;
    window.speechSynthesis.speak(utterance);
  }

  function selectedPosFor(word) {
    return Array.isArray(state.wordPos[word.label]) ? state.wordPos[word.label] : [];
  }

  function normalizePos(value) {
    const key = String(value || "").toLowerCase().replaceAll(".", "").trim();
    const aliases = {
      n: "noun", noun: "noun", nouns: "noun",
      v: "verb", verb: "verb", verbs: "verb",
      adj: "adj", adjective: "adj",
      adv: "adv", adverb: "adv",
      prep: "prep", preposition: "prep",
      other: "other",
    };
    return aliases[key] || "";
  }

  function normalizePosList(value) {
    const values = Array.isArray(value) ? value : value ? [value] : [];
    return [...new Set(values.map(normalizePos).filter(Boolean))];
  }

  function currentAnalysis() {
    const sets = analysis?.sets || {};
    const dateKey = `${current.year}-${String(current.month).padStart(2, "0")}-${current.set}`;
    return sets[current.id] || sets[String(current.id)] || sets[dateKey] || sets[current.label] || {};
  }

  function wordAnalysis(word) {
    const words = currentAnalysis().words || {};
    return words[word.label] || words[word.word] || words[word.word.toLowerCase()] || null;
  }

  function blankAnalysis(blank) {
    const blanks = currentAnalysis().blanks || {};
    return blanks[blank] || blanks[String(blank)] || null;
  }

  function systemPosFor(word) {
    const preset = wordAnalysis(word);
    const tagged = normalizePosList(preset?.pos ?? preset?.partsOfSpeech);
    return tagged.length ? tagged : word.suggestedPos;
  }

  function expectedBlankPos(blank) {
    const preset = blankAnalysis(blank);
    return normalizePos(preset?.pos ?? preset?.requiredPos);
  }

  function analysisDetail(preset) {
    if (!preset) return "";
    const details = [];
    const pos = normalizePos(preset.pos ?? preset.requiredPos);
    if (pos) details.push(posLabel(pos));
    const form = preset.form ?? preset.requiredForm;
    if (form) details.push(String(form));
    if (preset.reason) details.push(String(preset.reason));
    return details.join(" · ");
  }

  function effectivePosFor(word) {
    const selected = selectedPosFor(word);
    return selected.length ? selected : systemPosFor(word);
  }

  function candidatesFor(blank) {
    const needed = state.blankPos[blank];
    const words = needed
      ? current.words.filter((word) => effectivePosFor(word).includes(needed))
      : current.words;
    return words;
  }

  function progressMarkup(done, total, suffix = "") {
    const percent = total ? Math.round((done / total) * 100) : 0;
    return `<div class="progress"><span>${done}/${total}${suffix}</span><div class="progress-bar"><i style="width:${percent}%"></i></div></div>`;
  }

  function setIntro(title, description, done, total, suffix = "") {
    els.intro.innerHTML = `<div><p class="eyebrow">STAGE ${String(stage).padStart(2, "0")}</p><h3>${title}</h3><p>${description}</p></div>${progressMarkup(done, total, suffix)}`;
  }

  function splitIntoParagraphs(text) {
    const dot = "\uE000";
    let safe = text
      .replace(/\b(Mr|Mrs|Ms|Dr|Prof|St|No)\./g, `$1${dot}`)
      .replace(/\b([A-Z])\.([A-Z])\./g, `$1${dot}$2${dot}`)
      .replace(/\b(e\.g|i\.e)\./gi, (value) => value.replaceAll(".", dot))
      .replace(/(\d)\.(\d)/g, `$1${dot}$2`);
    const sentences = safe
      .split(/(?<=[.!?])\s+(?=[“\"']?[A-Z])/)
      .map((sentence) => sentence.replaceAll(dot, ".").trim())
      .filter(Boolean);
    if (sentences.length <= 3) return [text];
    const paragraphs = [];
    let currentParagraph = [];
    let currentLength = 0;
    sentences.forEach((sentence, index) => {
      currentParagraph.push(sentence);
      currentLength += sentence.length;
      const remaining = sentences.length - index - 1;
      const shouldBreak = currentParagraph.length >= 3 || currentLength >= 390;
      if (shouldBreak && remaining >= 2) {
        paragraphs.push(currentParagraph.join(" "));
        currentParagraph = [];
        currentLength = 0;
      }
    });
    if (currentParagraph.length) paragraphs.push(currentParagraph.join(" "));
    return paragraphs;
  }

  function passagePartHtml(part) {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match) return escapeHtml(part);
    const blank = match[1];
    const answer = state.answers[blank];
    const tagged = state.blankPos[blank];
    const className = answer ? "solved" : tagged ? "tagged" : "";
    const label = answer ? `${blank} · ${answer}` : blank;
    return `<button class="blank-token ${className}" data-blank="${blank}" type="button" title="查看第 ${blank} 空">${escapeHtml(label)}</button>`;
  }

  function renderPassage() {
    els.label.textContent = current.label;
    els.passage.innerHTML = splitIntoParagraphs(current.content).map((paragraph) => {
      const parts = paragraph.split(/(\[(?:2[6-9]|3[0-5])\])/g);
      return `<p>${parts.map(passagePartHtml).join("")}</p>`;
    }).join("");
    els.passage.querySelectorAll(".blank-token").forEach((button) => {
      button.addEventListener("click", () => {
        if (stage === 1) setStage(2);
        requestAnimationFrame(() => {
          document.querySelector(`[data-blank-card="${button.dataset.blank}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      });
    });
  }

  function renderStageOne() {
    const done = current.words.filter((word) => selectedPosFor(word).length).length;
    setIntro("给 15 个词贴词性标签", "只判断 n.、v.、adj.、adv. 等基础词性。v-s、n-s、v-ing、v-ed 只在分析提示中出现。", done, current.words.length);
    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.innerHTML = `<button class="button primary" data-action="check" type="button">检查词性</button><button class="button ghost" data-action="suggest" type="button">采用分析建议</button><button class="button lime" data-action="next" type="button">下一步：判空格</button>`;
    const grid = document.createElement("div");
    grid.className = "word-grid";

    current.words.forEach((word) => {
      const card = els.template.content.firstElementChild.cloneNode(true);
      card.dataset.word = word.label;
      card.classList.toggle("complete", selectedPosFor(word).length > 0);
      card.querySelector(".word-label").textContent = word.label;
      card.querySelector(".word-text").textContent = word.word;
      card.querySelector(".mini-speak").addEventListener("click", () => speak(word.word));
      const container = card.querySelector(".pos-buttons");
      POS.forEach((pos) => {
        const button = document.createElement("button");
        button.className = "pos-chip";
        button.classList.toggle("selected", selectedPosFor(word).includes(pos.id));
        button.type = "button";
        button.textContent = pos.label;
        button.addEventListener("click", () => {
          const selected = new Set(selectedPosFor(word));
          selected.has(pos.id) ? selected.delete(pos.id) : selected.add(pos.id);
          state.wordPos[word.label] = [...selected];
          delete state.checkedWords[word.label];
          saveState();
          render();
        });
        container.append(button);
      });
      const feedback = card.querySelector(".word-feedback");
      if (state.checkedWords[word.label]) {
        const chosen = selectedPosFor(word);
        const systemPos = systemPosFor(word);
        const preset = wordAnalysis(word);
        const overlap = chosen.some((item) => systemPos.includes(item));
        const form = preset?.form ? `；形式：${preset.form}` : "";
        feedback.textContent = overlap
          ? `与分析建议一致：${systemPos.map(posLabel).join(" / ")}${form}`
          : `分析建议：${systemPos.map(posLabel).join(" / ")}${form}`;
        feedback.className = `word-feedback ${overlap ? "good" : "warn"}`;
      } else {
        feedback.textContent = selectedPosFor(word).length ? "已保存，可继续多选" : "尚未判断";
      }
      grid.append(card);
    });

    els.task.replaceChildren(toolbar, grid);
    toolbar.querySelector('[data-action="check"]').addEventListener("click", () => {
      current.words.forEach((word) => { state.checkedWords[word.label] = true; });
      saveState();
      render();
    });
    toolbar.querySelector('[data-action="suggest"]').addEventListener("click", () => {
      current.words.forEach((word) => { state.wordPos[word.label] = [...systemPosFor(word)]; });
      saveState();
      showToast("已填入分析建议，可手动修正");
      render();
    });
    toolbar.querySelector('[data-action="next"]').addEventListener("click", () => setStage(2));
  }

  function posLabel(id) {
    return POS.find((pos) => pos.id === id)?.label || id;
  }

  function contextFor(blank) {
    const marker = `[${blank}]`;
    const index = current.content.indexOf(marker);
    if (index < 0) return marker;
    const left = current.content.slice(Math.max(0, index - 115), index);
    const right = current.content.slice(index + marker.length, index + marker.length + 115);
    return `${index > 115 ? "…" : ""}${left}<mark>${marker}</mark>${right}${index + marker.length + 115 < current.content.length ? "…" : ""}`;
  }

  function blankCardBase(blank, easy = false) {
    const card = document.createElement("article");
    card.className = `blank-card${easy ? " easy" : ""}`;
    card.dataset.blankCard = blank;
    return card;
  }

  function renderStageTwo() {
    const done = current.blanks.filter((blank) => state.blankPos[blank]).length;
    setIntro("判断每一空需要什么词性", "先看空格前后的冠词、介词、系动词和修饰关系。选择后，系统只保留同词性的候选词。", done, current.blanks.length);
    const list = document.createElement("div");
    list.className = "blank-list";
    const fallbackCount = current.words.filter((word) => !selectedPosFor(word).length).length;
    if (fallbackCount) {
      const note = document.createElement("p");
      note.className = "notice";
      note.innerHTML = `<strong>${fallbackCount} 个词尚未手动标注。</strong> 候选筛选暂用 JSON 分析或内置词形建议，回到第一步标注后会自动更新。`;
      list.append(note);
    }

    current.blanks.forEach((blank) => {
      const candidates = candidatesFor(blank);
      const card = blankCardBase(blank);
      card.innerHTML = `<div class="blank-top"><span class="blank-number">${blank}</span><span class="candidate-count">${state.blankPos[blank] ? `${posLabel(state.blankPos[blank])} · ${candidates.length} 个候选` : "请选择所需词性"}</span></div><p class="context">${contextFor(blank)}</p><div class="pos-buttons"></div><div class="candidate-pool"></div>`;
      const posButtons = card.querySelector(".pos-buttons");
      POS.forEach((pos) => {
        const button = document.createElement("button");
        button.className = `pos-chip${state.blankPos[blank] === pos.id ? " selected" : ""}`;
        button.type = "button";
        button.textContent = pos.label;
        button.addEventListener("click", () => {
          state.blankPos[blank] = state.blankPos[blank] === pos.id ? "" : pos.id;
          if (state.answers[blank] && !candidatesFor(blank).some((word) => word.label === state.answers[blank])) delete state.answers[blank];
          saveState();
          render();
        });
        posButtons.append(button);
      });
      const pool = card.querySelector(".candidate-pool");
      if (state.blankPos[blank]) {
        candidates.forEach((word) => {
          const chip = document.createElement("span");
          chip.className = "candidate preview";
          chip.textContent = `${word.label} ${word.word}`;
          pool.append(chip);
        });
      }
      const preset = blankAnalysis(blank);
      const expected = expectedBlankPos(blank);
      if (preset && state.blankPos[blank]) {
        const feedback = document.createElement("p");
        const matches = !expected || expected === state.blankPos[blank];
        feedback.className = `analysis-feedback ${matches ? "good" : "warn"}`;
        feedback.textContent = `${matches ? "词性判断符合分析" : "词性需要调整"}：${analysisDetail(preset) || "预设分析未提供详细说明"}`;
        card.append(feedback);
      }
      list.append(card);
    });
    const toolbar = document.createElement("div");
    toolbar.className = "toolbar sticky-actions";
    toolbar.innerHTML = `<button class="button ghost" data-action="back" type="button">返回词库</button><button class="button lime" data-action="next" type="button">下一步：定答案</button>`;
    els.task.replaceChildren(list, toolbar);
    toolbar.querySelector('[data-action="back"]').addEventListener("click", () => setStage(1));
    toolbar.querySelector('[data-action="next"]').addEventListener("click", () => setStage(3));
  }

  function renderStageThree() {
    const done = current.blanks.filter((blank) => state.answers[blank]).length;
    setIntro("从候选最少的空开始锁定", "优先完成最确定的空；选中的词会在其他空自动标为已使用。你仍可随时修改词性或答案。", done, current.blanks.length);
    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.innerHTML = `<button class="button ${sortEasyFirst ? "primary" : "ghost"}" data-action="sort" type="button">${sortEasyFirst ? "✓ " : ""}简单优先</button><button class="button ghost" data-action="original" type="button">按题号</button><button class="button ghost" data-action="back" type="button">修改空格词性</button>`;

    const list = document.createElement("div");
    list.className = "blank-list";
    const ordered = [...current.blanks];
    if (sortEasyFirst) ordered.sort((a, b) => candidatesFor(a).length - candidatesFor(b).length || a - b);
    const used = new Map(Object.entries(state.answers).map(([blank, label]) => [label, blank]));

    ordered.forEach((blank) => {
      const candidates = candidatesFor(blank);
      const card = blankCardBase(blank, state.blankPos[blank] && candidates.length <= 4);
      const answerLabel = state.answers[blank];
      const answerWord = current.words.find((word) => word.label === answerLabel);
      card.innerHTML = `<div class="blank-top"><div><span class="blank-number">${blank}</span>${state.blankPos[blank] ? `<span class="pos-badge">${escapeHtml(posLabel(state.blankPos[blank]))}</span>` : ""}</div><span class="candidate-count">${candidates.length} 个候选${answerWord ? ` · 已选 ${escapeHtml(answerWord.word)}` : ""}</span></div><p class="context">${contextFor(blank)}</p><div class="candidate-pool"></div>`;
      const pool = card.querySelector(".candidate-pool");
      if (!state.blankPos[blank]) {
        const note = document.createElement("p");
        note.className = "empty-note compact";
        note.textContent = "尚未判断所需词性，当前显示全部词。建议先回第二步。";
        pool.append(note);
      }
      candidates.forEach((word) => {
        const owner = used.get(word.label);
        const button = document.createElement("button");
        button.type = "button";
        button.className = `candidate${answerLabel === word.label ? " selected" : ""}${owner && String(owner) !== String(blank) ? " used" : ""}`;
        button.textContent = `${word.label}  ${word.word}`;
        button.title = owner && String(owner) !== String(blank) ? `已用于第 ${owner} 空；点击可移到本空` : `选择 ${word.word}`;
        button.addEventListener("click", () => chooseAnswer(blank, word.label));
        pool.append(button);
      });
      if (answerLabel) {
        const clear = document.createElement("button");
        clear.type = "button";
        clear.className = "clear-answer";
        clear.textContent = "清除此空答案";
        clear.addEventListener("click", () => {
          delete state.answers[blank];
          saveState();
          render();
        });
        card.append(clear);
      }
      const preset = blankAnalysis(blank);
      const presetAnswer = String(preset?.answer || "").toUpperCase();
      if (answerLabel && preset) {
        const feedback = document.createElement("p");
        const correct = !presetAnswer || presetAnswer === answerLabel;
        feedback.className = `analysis-feedback ${correct ? "good" : "warn"}`;
        const verdict = presetAnswer
          ? correct ? "答案符合预设分析" : `预设答案为 ${presetAnswer}`
          : "已读取本空分析";
        feedback.textContent = `${verdict}${analysisDetail(preset) ? `：${analysisDetail(preset)}` : ""}`;
        card.append(feedback);
      }
      list.append(card);
    });

    const sheet = document.createElement("section");
    sheet.className = "answer-sheet";
    const answerText = current.blanks.map((blank) => {
      const label = state.answers[blank];
      const word = current.words.find((item) => item.label === label);
      return `${blank}${label ? `${label}(${word?.word || ""})` : "—"}`;
    }).join("  ");
    const presetAnswerCount = current.blanks.filter((blank) => blankAnalysis(blank)?.answer).length;
    const answerNote = presetAnswerCount
      ? `当前 JSON 含 ${presetAnswerCount} 个预设答案，选词后会自动显示分析。`
      : "当前分析没有预设答案；页面只整理推理结果，不伪造对错判分。";
    sheet.innerHTML = `<h4>我的最终答案</h4><p class="answer-code">${escapeHtml(answerText)}</p><div class="toolbar"><button class="button lime" data-action="copy" type="button">复制答案</button></div><p class="answer-note">${answerNote}</p>`;

    els.task.replaceChildren(toolbar, list, sheet);
    toolbar.querySelector('[data-action="sort"]').addEventListener("click", () => { sortEasyFirst = true; render(); });
    toolbar.querySelector('[data-action="original"]').addEventListener("click", () => { sortEasyFirst = false; render(); });
    toolbar.querySelector('[data-action="back"]').addEventListener("click", () => setStage(2));
    sheet.querySelector('[data-action="copy"]').addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(`${current.label}\n${answerText}`);
        showToast("答案已复制");
      } catch {
        showToast("复制失败，请手动选择答案文本");
      }
    });
  }

  function chooseAnswer(blank, label) {
    if (state.answers[blank] === label) {
      delete state.answers[blank];
    } else {
      const oldBlank = Object.keys(state.answers).find((key) => state.answers[key] === label);
      if (oldBlank && String(oldBlank) !== String(blank)) {
        delete state.answers[oldBlank];
        showToast(`${label} 已从第 ${oldBlank} 空移到第 ${blank} 空`);
      }
      state.answers[blank] = label;
    }
    saveState();
    render();
  }

  function render() {
    renderPassage();
    document.querySelectorAll(".stage-tab").forEach((button) => button.classList.toggle("active", Number(button.dataset.stage) === stage));
    if (stage === 1) renderStageOne();
    if (stage === 2) renderStageTwo();
    if (stage === 3) renderStageThree();
  }

  function setStage(next) {
    stage = next;
    render();
    document.querySelector(".stage-tabs").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function switchSet(id) {
    current = DATA.find((item) => String(item.id) === String(id)) || DATA[0];
    if (!current) return;
    state = loadState(current.id);
    localStorage.setItem(LAST_SET_KEY, current.id);
    els.select.value = current.id;
    stage = 1;
    render();
  }

  function setAnalysis(value, source) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("分析文件必须是 JSON 对象");
    analysis = { version: value.version || 1, sets: value.sets || {} };
    const setCount = Object.keys(analysis.sets).length;
    els.analysisStatus.textContent = setCount ? `${source} · ${setCount} 套解析` : `${source} · 暂无预设解析`;
  }

  async function loadPresetAnalysis() {
    if (location.protocol === "file:") {
      setAnalysis({ version: 1, sets: {} }, "本地模式");
      return;
    }
    try {
      const response = await fetch("analysis.json", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      setAnalysis(await response.json(), "analysis.json");
    } catch {
      setAnalysis({ version: 1, sets: {} }, "内置词形建议");
    }
  }

  async function init() {
    if (!DATA.length) {
      els.task.innerHTML = '<p class="empty-note">没有载入题库数据，请重新生成 dataset.js。</p>';
      return;
    }
    els.setCount.textContent = DATA.length;
    DATA.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.id;
      option.textContent = item.label;
      els.select.append(option);
    });
    els.select.addEventListener("change", () => switchSet(els.select.value));
    els.analysisFile.addEventListener("change", async () => {
      const file = els.analysisFile.files?.[0];
      if (!file) return;
      try {
        setAnalysis(JSON.parse(await file.text()), file.name);
        render();
        showToast("分析 JSON 已读取");
      } catch (error) {
        showToast(`分析 JSON 无法读取：${error.message}`);
      } finally {
        els.analysisFile.value = "";
      }
    });
    document.querySelectorAll(".stage-tab").forEach((button) => button.addEventListener("click", () => setStage(Number(button.dataset.stage))));
    els.speak.addEventListener("click", () => speak(current.content));
    els.reset.addEventListener("click", () => {
      if (!window.confirm(`确定清空“${current.label}”的全部训练记录吗？`)) return;
      localStorage.removeItem(STORAGE_PREFIX + current.id);
      state = blankState();
      stage = 1;
      render();
      showToast("本卷训练记录已清空");
    });
    await loadPresetAnalysis();
    const last = localStorage.getItem(LAST_SET_KEY);
    switchSet(last || DATA[0].id);
  }

  init();
})();
