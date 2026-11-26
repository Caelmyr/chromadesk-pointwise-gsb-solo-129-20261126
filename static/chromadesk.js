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
  for (const band of report.bands) {
    const row = body.insertRow();
    const cell = row.insertCell();
    const button = document.createElement("button");
    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = "rgb(" + band.rgb.join(",") + ")";
    button.type = "button";
    button.append(swatch, band.rf.toFixed(3));
    button.addEventListener("click", guarded(() => inspectRange("/probe", {x: probeColumn(), y: band.peak_y})));
    cell.append(button);
    for (const value of [band.first_y + "–" + band.last_y, band.width + " px", band.density.toFixed(3)]) {
      row.insertCell().textContent = value;
    }
  }
  if (!report.bands.length) {
    const cell = body.insertRow().insertCell();
    cell.colSpan = 4;
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

async function inspectRange(route, params) {
  const active = ++pointRequest;
  const result = await json(cardPath(route, params));
  if (active !== pointRequest) return;
  const {x, y, rgb, density, rf} = result;
  state.point = {x, y};
  byId("point-x").value = x;
  byId("point-y").value = y;
  const fraction = rf === null ? "无 Rf（点在量带或行程外）" : "Rf " + rf.toFixed(4);
  byId("readout").textContent = "原点 (" + x + ", " + y + ") · RGB " + rgb.join(" / ") +
    " · 光密度 " + density.toFixed(4) + " · " + fraction;
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
