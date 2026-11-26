"use strict";

const byId = (id) => document.getElementById(id);
const sheet = byId("photo");
const plot = byId("plot");
const state = {card: null, draft: null, image: null, report: null, mode: "probe", point: null, drag: null};
let photoRequest = 0;
let pointRequest = 0;

function status(message, error = false) {
  byId("status").textContent = message;
  byId("status").dataset.error = String(error);
}

async function json(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "请求未完成");
  return data;
}

function guarded(fn) {
  return async (...args) => {
    try { await fn(...args); }
    catch (error) { status(error.message, true); }
  };
}

function send(method, body) {
  return {method, headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
}

function cardPath(suffix = "", params = {}) {
  return "/chroma/cards/" + state.card.id + suffix + "?" +
    new URLSearchParams({rev: state.card.revision, ...params}).toString();
}

async function refreshArchive(selected = "") {
  const {cards} = await json("/chroma/cards");
  byId("cards").replaceChildren(new Option("请选择", ""), ...cards.map((card) =>
    new Option(card.name + (card.synthetic ? " · 合成" : ""), card.id)));
  byId("cards").value = selected;
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll("[data-tool]").forEach((button) =>
    button.setAttribute("aria-pressed", String(button.dataset.tool === mode)));
}

function showBounds() {
  for (const [id, name] of [["lane", "量带"], ["paper", "清纸"]]) {
    const b = state.draft[id];
    byId(id).textContent = name + " " + (b.right - b.left) + " × " + (b.bottom - b.top) +
      " px，左上 (" + b.left + ", " + b.top + ")";
  }
}

function draw() {
  if (!state.image) return;
  const ctx = sheet.getContext("2d");
  ctx.drawImage(state.image, 0, 0, sheet.width, sheet.height);
  ctx.lineWidth = Math.max(1.2, sheet.width / 430);
  for (const [name, color] of [["lane", "#339365"], ["paper", "#7843bd"]]) {
    let b = state.draft[name];
    if (state.drag && state.mode === name) b = dragBox(state.drag.start, state.drag.end);
    ctx.strokeStyle = color;
    ctx.strokeRect(b.left, b.top, b.right - b.left, b.bottom - b.top);
  }
  const lane = state.draft.lane;
  for (const [name, color] of [["front", "#236bae"], ["origin", "#926122"]]) {
    ctx.strokeStyle = color;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(lane.left, state.draft[name] + 0.5);
    ctx.lineTo(lane.right, state.draft[name] + 0.5);
    ctx.stroke();
  }
  ctx.setLineDash([]);
  if (state.point) {
    const {x, y} = state.point;
    ctx.lineWidth = Math.max(1.6, sheet.width / 360);
    ctx.strokeStyle = "#faf9f0";
    ctx.beginPath();
    ctx.arc(x + .5, y + .5, Math.max(4, sheet.width / 105), 0, Math.PI * 2);
    ctx.stroke();
    ctx.strokeStyle = "#242019";
    ctx.beginPath();
    ctx.arc(x + .5, y + .5, Math.max(3, sheet.width / 130), 0, Math.PI * 2);
    ctx.stroke();
  }
}

async function loadPhoto() {
  if (!state.card) return;
  const generation = ++photoRequest;
  const file = byId("view").value === "source" ? "/source.png" : "/density.png";
  const image = new Image();
  image.src = cardPath(file);
  await image.decode();
  if (generation !== photoRequest) return;
  state.image = image;
  [sheet.width, sheet.height] = state.card.size;
  byId("placeholder").hidden = true;
  sheet.hidden = false;
  draw();
}

const chart = {left: 58, right: 737, top: 17, bottom: 179};

function formatColumnRanges(columns) {
  if (!columns) return "无共同完整可见原列";
  if (columns.ranges && columns.ranges.length === 1) {
    const range = columns.ranges[0];
    return "原列 " + range.first_x + "–" + range.last_x;
  }
  if (columns.ranges && columns.ranges.length > 1) {
    return columns.count + " 个共同原列（" + columns.ranges.length + " 段）";
  }
  if (columns.first_x !== null && columns.first_x !== undefined) {
    return "原列 " + columns.first_x + "–" + columns.last_x;
  }
  return "无共同完整可见原列";
}

function showReport() {
  const report = state.report;
  const card = state.card;
  const ctx = plot.getContext("2d");
  const rows = report.rows;
  const maxDensity = Math.max(0.08, state.card.settings.threshold, ...rows.map((row) => row.density)) * 1.12;
  const plotX = (rf) => chart.left + rf * (chart.right - chart.left);
  const plotY = (density) => chart.bottom - density / maxDensity * (chart.bottom - chart.top);
  ctx.clearRect(0, 0, plot.width, plot.height);
  ctx.font = "14px sans-serif";
  ctx.fillStyle = "#586558";
  ctx.strokeStyle = "#d8d9cc";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 5; i += 1) {
    const x = plotX(i / 5);
    ctx.beginPath();
    ctx.moveTo(x, chart.top);
    ctx.lineTo(x, chart.bottom);
    ctx.stroke();
    ctx.fillText((i / 5).toFixed(1), x - 10, chart.bottom + 20);
  }
  for (let i = 0; i < 4; i += 1) {
    const value = maxDensity * i / 4;
    const y = plotY(value);
    ctx.beginPath();
    ctx.moveTo(chart.left, y);
    ctx.lineTo(chart.right, y);
    ctx.stroke();
    ctx.fillText(value.toFixed(2), 12, y + 5);
  }
  ctx.strokeStyle = "#ba8048";
  ctx.setLineDash([6, 5]);
  ctx.beginPath();
  ctx.moveTo(chart.left, plotY(card.settings.threshold));
  ctx.lineTo(chart.right, plotY(card.settings.threshold));
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.strokeStyle = "#315942";
  ctx.lineWidth = 2.8;
  ctx.beginPath();
  rows.forEach((row, index) => {
    const x = plotX(row.rf);
    const y = plotY(row.density);
    if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
  ctx.fillText("Rf", chart.right - 17, plot.height - 4);

  byId("report-meta").textContent = "采样 " + report.sampled_columns + " 列 · 清纸 RGB " +
    report.white.map((v) => v.toFixed(1)).join(" / ");
  const body = byId("band-body");
  body.replaceChildren();
  report.bands.forEach((band, index) => {
    const measured = band.measured_peak || band.narrow_peak || {};
    const row = body.insertRow();
    row.dataset.bandIndex = String(index);
    row.dataset.candidateYs = JSON.stringify(band.candidate_ys || []);
    row.dataset.peakStatus = band.peak_y !== null && band.peak_y !== undefined
      ? (band.density_is_lower_bound ? "lower-bound" : "evidenced")
      : (measured.known ? "measured-narrow" : "undetermined");
    const cell = row.insertCell();
    const button = document.createElement("button");
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = "rgb(" + band.rgb.join(",") + ")";
    button.type = "button";
    button.className = "band-peak-button";
    button.dataset.bandIndex = String(index);
    if (band.peak_y !== null && band.peak_y !== undefined) {
      button.dataset.peakStatus = band.density_is_lower_bound ? "lower-bound" : "evidenced";
      button.append(swatch, document.createTextNode(band.rf.toFixed(3) + (band.density_is_lower_bound ? " ≥" : "")));
      button.title = "整带宽度下唯一不能排除的原行；点击后按当前原列核查有证峰";
    } else if (measured.known && measured.rf !== null && measured.rf !== undefined) {
      button.append(swatch, document.createTextNode("峰未定 · 窄测 " + measured.rf.toFixed(3)));
      button.title = "整带峰未定；" + measured.message + " 点击后按当前原列核查有证峰";
    } else {
      button.append(swatch, document.createTextNode("峰未定 · 核峰"));
      button.title = (band.message || "多行仍可能最深") + " 点击后按当前原列核查";
    }
    button.dataset.peakStatus = band.peak_y !== null && band.peak_y !== undefined
      ? (band.density_is_lower_bound ? "lower-bound" : "evidenced")
      : (measured.known ? "measured-narrow" : "undetermined");
    button.setAttribute("aria-label", "核查第 " + (index + 1) + " 条色带在当前原列的有证峰");
    button.addEventListener("click", guarded(() => inspectBand(band, index)));
    cell.append(button);
    for (const value of [band.first_y + "–" + band.last_y, band.width + " px", band.trace_density?.toFixed?.(3) ?? band.density?.toFixed?.(3)]) {
      row.insertCell().textContent = value;
    }
    const evidence = row.insertCell();
    evidence.className = "peak-evidence";
    evidence.dataset.testid = "peak-evidence";
    const candidates = document.createElement("div");
    candidates.textContent = "候选原行：" + (band.candidate_ys || []).join("、");
    evidence.append(candidates);
    const narrow = document.createElement("div");
    narrow.className = "evidence-range";
    if (measured.known) {
      narrow.textContent = "窄范围实测 y=" + measured.y + "，" + formatColumnRanges(measured.columns);
    } else if (measured.columns) {
      narrow.textContent = "窄范围同分 y=" + (measured.tied_ys || []).join("、") +
        "，" + formatColumnRanges(measured.columns);
    } else {
      narrow.textContent = measured.message || "无共同完整可见原列";
    }
    evidence.append(narrow);
    const recheckButton = document.createElement("button");
    recheckButton.type = "button";
    recheckButton.className = "recheck-peak-button";
    recheckButton.dataset.bandIndex = String(index);
    recheckButton.textContent = "重核峰位";
    recheckButton.title = "按原点核查中当前填写的原列重核该色带";
    recheckButton.addEventListener("click", guarded(() => inspectBand(band, index)));
    evidence.append(recheckButton);
  });
  if (!report.bands.length) {
    const cell = body.insertRow().insertCell();
    cell.colSpan = 5;
    cell.textContent = "没有达到当前门槛的连续色带。";
  }
  byId("strip").href = cardPath("/strip.png");
  byId("trace").href = cardPath("/trace.csv");
  byId("results").hidden = false;
}

async function showCard(card, resetView) {
  const {width, height} = {width: card.size[0], height: card.size[1]};
  state.card = card;
  state.draft = structuredClone(card.settings);
  state.point = null;
  state.peakMarker = null;
  pointRequest += 1;
  if (resetView) {
    byId("view").value = "source";
    byId("point-x").value = String(Math.floor((card.settings.lane.left + card.settings.lane.right) / 2));
    byId("point-y").value = String(card.settings.front);
  }
  byId("point-x").max = String(width - 1);
  byId("point-y").max = String(height - 1);
  byId("front").max = byId("origin").max = String(height - 1);
  byId("card-name").textContent = card.name;
  byId("card-meta").textContent = card.source_name + " · " + width + " × " + height + " px" +
    (card.synthetic ? " · 程序合成练习" : "");
  byId("revision").textContent = "采用 v" + card.revision;
  byId("readout").textContent = "在原片上选一点，或填原列与 Rf 回查。";
  for (const id of ["front", "origin", "threshold"]) byId(id).value = card.settings[id];
  document.querySelectorAll("[data-card]").forEach((node) => { node.disabled = false; });
  setMode("probe");
  showBounds();
  const [report] = await Promise.all([json(cardPath("/report")), loadPhoto(), refreshArchive(card.id)]);
  if (state.card !== card) return;
  state.report = report;
  showReport();
}

function originalPoint(event) {
  const b = sheet.getBoundingClientRect();
  const x = Math.floor((event.clientX - b.left) * sheet.width / b.width);
  const y = Math.floor((event.clientY - b.top) * sheet.height / b.height);
  return {x: Math.max(0, Math.min(sheet.width - 1, x)), y: Math.max(0, Math.min(sheet.height - 1, y))};
}

function dragBox(start, end) {
  return {
    left: Math.min(start.x, end.x), top: Math.min(start.y, end.y),
    right: Math.max(start.x, end.x) + 1, bottom: Math.max(start.y, end.y) + 1,
  };
}

function probeColumn() {
  return byId("point-x").valueAsNumber;
}

function formatProbe(result) {
  const fraction = result.rf === null ? "无 Rf（点在量带或行程外）" : "Rf " + result.rf.toFixed(4);
  const zeroNote = result.density_is_lower_bound
    ? " · 零通道 " + (result.zero_channels || []).join("") + "：密度只能记作至少 " + result.density.toFixed(4)
    : "";
  return "原点 (" + result.x + ", " + result.y + ") · RGB " + result.rgb.join(" / ") +
    " · 光密度 " + result.density.toFixed(4) + " · " + fraction + zeroNote;
}

function showProbe(result) {
  const {x, y} = result;
  state.point = {x, y};
  state.peakMarker = null;
  byId("point-x").value = x;
  byId("point-y").value = y;
  byId("readout").textContent = formatProbe(result);
  draw();
}

async function inspectRange(route, params) {
  const active = ++pointRequest;
  const result = await json(cardPath(route, params));
  if (active !== pointRequest) return;
  showProbe(result);
}

async function inspectBand(band, index) {
  const x = probeColumn();
  if (!Number.isInteger(x)) throw new Error("请先在原点核查中填写有效原列");
  let y = byId("point-y").valueAsNumber;
  if (!Number.isInteger(y) || y < band.first_y || y > band.last_y) {
    y = band.trace_peak_y ?? band.first_y;
  }

  const active = ++pointRequest;
  const result = await json(cardPath("/probe", {x, y, band: index}));
  if (active !== pointRequest) return;
  const check = result.peak_check || result.peak || {};

  const shown = check.known && result.peak_probe ? result.peak_probe : result;
  if (!shown) throw new Error("原 RGB 点读失败");
  state.point = {x: shown.x, y: shown.y};
  state.peakMarker = check.known ? {x: result.x, y: check.peak_y} : null;
  byId("point-x").value = shown.x;
  byId("point-y").value = shown.y;

  byId("readout").replaceChildren();
  const raw = document.createElement("div");
  raw.textContent = formatProbe(shown);
  const verdict = document.createElement("div");
  verdict.id = "peak-verdict";
  verdict.dataset.testid = "peak-status";
  verdict.dataset.state = check.known ? "evidenced" : "undetermined";
  verdict.className = check.known ? "peak-verdict known" : "peak-verdict unknown";
  if (check.known) {
    verdict.textContent = "有证峰：原行 " + check.peak_y + " · Rf " + check.rf.toFixed(4) +
      " · 该列密度 " + check.density.toFixed(4);
  } else {
    verdict.textContent = check.message || "峰未定；原 RGB 还能照常点读。";
  }
  byId("readout").append(raw, verdict);
  draw();
}

sheet.addEventListener("pointerdown", guarded(async (event) => {
  if (!state.card || !state.image || event.button !== 0) return;
  const point = originalPoint(event);
  if (state.mode === "probe") {
    await inspectRange("/probe", point);
  } else if (state.mode === "origin" || state.mode === "front") {
    state.draft[state.mode] = point.y;
    byId(state.mode).value = point.y;
    draw();
    status("已标记，采用之后进入判读。");
  } else {
    sheet.setPointerCapture(event.pointerId);
    state.drag = {start: point, end: point};
    draw();
  }
}));
sheet.addEventListener("pointermove", (event) => {
  if (!state.drag) return;
  state.drag.end = originalPoint(event);
  draw();
});
sheet.addEventListener("pointerup", (event) => {
  if (!state.drag) return;
  state.draft[state.mode] = dragBox(state.drag.start, originalPoint(event));
  state.drag = null;
  showBounds();
  draw();
  status("已标记，采用之后进入判读。");
});
sheet.addEventListener("pointercancel", () => {
  state.drag = null;
  draw();
});

document.querySelectorAll("[data-tool]").forEach((button) =>
  button.addEventListener("click", () => setMode(button.dataset.tool)));
for (const id of ["front", "origin", "threshold"]) {
  byId(id).addEventListener("input", () => {
    if (!Number.isFinite(byId(id).valueAsNumber)) return;
    state.draft[id] = byId(id).valueAsNumber;
    draw();
  });
}
byId("view").addEventListener("change", guarded(loadPhoto));
byId("practice").addEventListener("click", guarded(async () => {
  await showCard(await json("/chroma/practice", send("POST", {sample: byId("sample").value})), true);
  status("已打开并存入合成练习。");
}));
byId("upload").addEventListener("submit", guarded(async (event) => {
  event.preventDefault();
  const data = new FormData(event.currentTarget);
  await showCard(await json("/chroma/cards", {method: "POST", body: data}), true);
  status("已导入原片。");
}));
byId("reopen").addEventListener("click", guarded(async () => {
  const id = byId("cards").value;
  if (!id) throw new Error("请先选择一张层析卡");
  await showCard(await json("/chroma/cards/" + id), true);
  status("已载入上次采用设置。");
}));
byId("settings").addEventListener("submit", guarded(async (event) => {
  event.preventDefault();
  const payload = {revision: state.card.revision, ...state.draft};
  for (const id of ["front", "origin", "threshold"]) payload[id] = byId(id).valueAsNumber;
  await showCard(await json(cardPath(), send("PATCH", payload)), false);
  status("已采用量带设置并保存。");
}));
byId("probe-form").addEventListener("submit", guarded(async (event) => {
  event.preventDefault();
  await inspectRange("/probe", {x: probeColumn(), y: byId("point-y").valueAsNumber});
}));
byId("locate-form").addEventListener("submit", guarded(async (event) => {
  event.preventDefault();
  await inspectRange("/locate", {x: probeColumn(), rf: byId("point-rf").valueAsNumber});
}));
plot.addEventListener("click", guarded(async (event) => {
  if (!state.report) return;
  const rect = plot.getBoundingClientRect();
  const pixel = (event.clientX - rect.left) * plot.width / rect.width;
  const fraction = Math.max(0, Math.min(1, (pixel - chart.left) / (chart.right - chart.left)));
  byId("point-rf").value = fraction.toFixed(4);
  await inspectRange("/locate", {x: probeColumn(), rf: fraction});
}));
byId("prepare").addEventListener("click", guarded(async () => {
  const {url} = await json(cardPath("/prepare"), {method: "POST"});
  location.assign(url);
}));
guarded(refreshArchive)();
