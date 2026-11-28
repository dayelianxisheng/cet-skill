(() => {
  "use strict";

  const DATA = Array.isArray(window.CET4_DATA) ? window.CET4_DATA : [];
  const STORAGE_PREFIX = "cet4-pos-trainer-v1:";
  const LAST_SET_KEY = "cet4-pos-trainer:last-set";
  const COLORS = ["#d9ff66", "#dcecff", "#ffd9ca", "#d9eee7", "#fff0ae", "#dfe0ff", "#cde8d2", "#ffe1ef"];
  const els = {
    wheel: document.querySelector("#rouletteWheel"),
    spin: document.querySelector("#spinBtn"),
    refresh: document.querySelector("#refreshBtn"),
    accept: document.querySelector("#acceptBtn"),
    candidates: document.querySelector("#candidateList"),
    result: document.querySelector("#result"),
    current: document.querySelector("#currentSet"),
  };

  let items = [];
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

  function shuffled(values) {
    const copy = [...values];
    for (let index = copy.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [copy[index], copy[swapIndex]] = [copy[swapIndex], copy[index]];
    }
    return copy;
  }

  function solvedCount(item) {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_PREFIX + item.id));
      return Object.keys(saved?.answers || {}).length;
    } catch {
      return 0;
    }
  }

  function compactLabel(item) {
    return `${String(item.year).slice(-2)}.${String(item.month).padStart(2, "0")} 卷${item.set}`;
  }

  function currentItem() {
    const lastId = localStorage.getItem(LAST_SET_KEY);
    return DATA.find((item) => String(item.id) === String(lastId)) || DATA[0];
  }

  function render() {
    const size = items.length || 1;
    const segment = 360 / size;
    const gradient = items.map((_, index) => {
      const start = index * segment;
      return `${COLORS[index % COLORS.length]} ${start}deg ${start + segment}deg`;
    }).join(", ");
    els.wheel.style.background = `conic-gradient(from 0deg, ${gradient})`;
    els.wheel.innerHTML = items.map((item, index) => {
      const angle = index * segment + segment / 2;
      return `<span class="roulette-label" style="--angle:${angle}deg;--counter-angle:${-angle}deg"><span class="roulette-label-content"><b>${escapeHtml(compactLabel(item))}</b><small>${solvedCount(item)}/${item.blanks.length}</small></span></span>`;
    }).join("");
    els.candidates.innerHTML = items.map((item) => `<div class="candidate"><b>${escapeHtml(compactLabel(item))}</b><small>已完成 ${solvedCount(item)}/${item.blanks.length}</small></div>`).join("");
  }

  function pickCandidates() {
    clearTimeout(timer);
    const current = currentItem();
    const alternatives = DATA.filter((item) => !current || String(item.id) !== String(current.id));
    const unfinished = shuffled(alternatives.filter((item) => solvedCount(item) < item.blanks.length));
    const completed = shuffled(alternatives.filter((item) => solvedCount(item) >= item.blanks.length));
    items = [...unfinished, ...completed].slice(0, 8);
    winner = null;
    rotation = 0;
    els.wheel.style.transition = "none";
    els.wheel.style.transform = "rotate(0deg)";
    els.spin.disabled = false;
    els.refresh.disabled = false;
    els.accept.hidden = true;
    els.result.textContent = "点击转盘中央的“开始”。";
    render();
    requestAnimationFrame(() => { els.wheel.style.transition = ""; });
  }

  function spin() {
    if (!items.length || els.spin.disabled) return;
    const winnerIndex = Math.floor(Math.random() * items.length);
    winner = items[winnerIndex];
    const segment = 360 / items.length;
    const target = (360 - (winnerIndex * segment + segment / 2)) % 360;
    const currentAngle = ((rotation % 360) + 360) % 360;
    rotation += 5 * 360 + ((target - currentAngle + 360) % 360);
    els.spin.disabled = true;
    els.refresh.disabled = true;
    els.accept.hidden = true;
    els.result.textContent = "转盘正在选择……";
    els.wheel.style.transform = `rotate(${rotation}deg)`;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 50 : 3900;
    timer = setTimeout(() => {
      els.spin.disabled = false;
      els.refresh.disabled = false;
      els.accept.hidden = false;
      els.result.innerHTML = `下一套：<strong>${escapeHtml(winner.label)}</strong>`;
      els.accept.focus();
    }, duration);
  }

  function startSelectedSet() {
    if (!winner) return;
    location.href = `../word-class-trainer/?set=${encodeURIComponent(winner.id)}`;
  }

  function init() {
    if (!DATA.length) {
      els.current.textContent = "题库载入失败";
      els.result.textContent = "没有找到选词填空数据。";
      els.spin.disabled = true;
      els.refresh.disabled = true;
      return;
    }
    els.current.textContent = currentItem()?.label || "尚未开始";
    els.spin.addEventListener("click", spin);
    els.refresh.addEventListener("click", pickCandidates);
    els.accept.addEventListener("click", startSelectedSet);
    pickCandidates();
  }

  init();
})();
