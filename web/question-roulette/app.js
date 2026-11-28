(() => {
  "use strict";

  const TYPES = [
    { id: "writing", label: "作文", detail: "审题 · 模板 · 默写", href: "../writing-template-trainer/" },
    { id: "listening", label: "听力", detail: "新闻 · 对话 · 篇章", href: "" },
    { id: "word-bank", label: "选词填空", detail: "词性 · 候选 · 搭配", href: "../word-class-trainer/" },
    { id: "matching", label: "长篇阅读", detail: "信息匹配 · 关键词 · 定位", href: "" },
    { id: "careful-reading", label: "仔细阅读", detail: "定位 · 证据 · 排除", href: "../careful-reading-locator/" },
    { id: "translation", label: "翻译", detail: "拆句 · 主干 · 表达", href: "" },
  ];
  const COLORS = ["#d9ff66", "#dcecff", "#ffd9ca", "#d9eee7", "#fff0ae", "#dfe0ff"];
  const LAST_TYPE_KEY = "cet4-question-roulette:last-type";
  const els = {
    wheel: document.querySelector("#rouletteWheel"),
    spin: document.querySelector("#spinBtn"),
    spinAgain: document.querySelector("#spinAgainBtn"),
    accept: document.querySelector("#acceptBtn"),
    candidates: document.querySelector("#candidateList"),
    result: document.querySelector("#result"),
  };

  let winner = null;
  let rotation = 0;
  let timer = null;

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function renderTypes() {
    const segment = 360 / TYPES.length;
    const gradient = TYPES.map((_, index) => {
      const start = index * segment;
      return `${COLORS[index]} ${start}deg ${start + segment}deg`;
    }).join(", ");
    els.wheel.style.background = `conic-gradient(from 0deg, ${gradient})`;
    els.wheel.innerHTML = TYPES.map((type, index) => {
      const angle = index * segment + segment / 2;
      return `<span class="roulette-label" style="--angle:${angle}deg;--counter-angle:${-angle}deg"><span class="roulette-label-content"><b>${escapeHtml(type.label)}</b><small>${escapeHtml(type.detail.split(" · ")[0])}</small></span></span>`;
    }).join("");
    els.candidates.innerHTML = TYPES.map((type) => `
      <div class="candidate${type.href ? " ready" : ""}">
        <b>${escapeHtml(type.label)}</b>
        <small>${escapeHtml(type.detail)}</small>
        <span>${type.href ? "可直接训练" : "训练页待补充"}</span>
      </div>`).join("");
  }

  function resetResult() {
    clearTimeout(timer);
    winner = null;
    els.accept.hidden = true;
    els.accept.removeAttribute("href");
    els.spinAgain.hidden = true;
    els.spin.disabled = false;
    els.result.textContent = "点击转盘中央的“开始”，决定下一项练习。";
  }

  function revealWinner() {
    els.spin.disabled = false;
    els.spinAgain.hidden = false;
    localStorage.setItem(LAST_TYPE_KEY, winner.id);
    if (winner.href) {
      els.accept.href = winner.href;
      els.accept.textContent = `进入${winner.label}训练`;
      els.accept.hidden = false;
      els.result.innerHTML = `下一题型：<strong>${escapeHtml(winner.label)}</strong><span>${escapeHtml(winner.detail)} · 训练页面已就绪</span>`;
      els.accept.focus();
    } else {
      els.accept.hidden = true;
      els.result.innerHTML = `下一题型：<strong>${escapeHtml(winner.label)}</strong><span>${escapeHtml(winner.detail)} · 这个训练页尚未创建</span>`;
      els.spinAgain.focus();
    }
  }

  function spin() {
    if (els.spin.disabled) return;
    const winnerIndex = Math.floor(Math.random() * TYPES.length);
    winner = TYPES[winnerIndex];
    const segment = 360 / TYPES.length;
    const target = (360 - (winnerIndex * segment + segment / 2)) % 360;
    const currentAngle = ((rotation % 360) + 360) % 360;
    rotation += 5 * 360 + ((target - currentAngle + 360) % 360);
    els.spin.disabled = true;
    els.spinAgain.hidden = true;
    els.accept.hidden = true;
    els.result.textContent = "转盘正在选择题型……";
    els.wheel.style.transform = `rotate(${rotation}deg)`;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 50 : 3900;
    timer = setTimeout(revealWinner, duration);
  }

  function init() {
    renderTypes();
    resetResult();
    els.spin.addEventListener("click", spin);
    els.spinAgain.addEventListener("click", spin);
  }

  init();
})();
