// Inference dashboard. Polls the read-only API; device-provided text is set with textContent only.
"use strict";

const POLL_MS = 2000;
const WARNINGS_MS = 5000;
const STALE_S = 10;
const MAX_FRAMES = 200;
const SVG_NS = "http://www.w3.org/2000/svg";
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  cfg: { threshold: 0.6, dwell_s: 5, max_gap_s: 3, cooldown_s: 30, history: 200 },
  cfgLoaded: false,
  selected: "",
  lastId: 0,
  generation: 0,
  seen: new Set(),
  paused: false,
  online: true,
  rows: new Map(), // mac -> row parts
};

const $ = (sel) => document.querySelector(sel);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svg(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v));
  return node;
}

function warnIcon() {
  const icon = svg("svg", { class: "icon", viewBox: "0 0 24 24", "aria-hidden": "true" });
  icon.append(svg("path", { d: "M12 3 2 21h20L12 3Z" }), svg("path", { d: "M12 10v5M12 18v.01" }));
  return icon;
}

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

const timeFmt = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const clock = (ts) => timeFmt.format(new Date(ts * 1000));
const secs = (s) => `${s.toFixed(1)} s`;
const conf = (c) => c.toFixed(2);

/* ---------- connection state ---------- */

function setOnline(ok) {
  if (state.online === ok) return;
  state.online = ok;
  $("#banner").hidden = ok;
  renderLinkState();
}

function renderLinkState() {
  const node = $("#link-state");
  if (!state.online) {
    node.textContent = "Reconnecting";
    node.dataset.state = "down";
  } else {
    node.textContent = state.paused ? "Paused" : "Live";
    node.dataset.state = state.paused ? "paused" : "live";
  }
}

/* ---------- station clock (signature: stops at 12 while the server is unreachable) ---------- */

function buildTicks(group, count, major, inner, outer, cls) {
  for (let i = 0; i < count; i++) {
    const a = (i / count) * 2 * Math.PI;
    const isMajor = major && i % major === 0;
    const r1 = isMajor ? inner - 6 : inner;
    group.append(svg("line", {
      class: isMajor ? `${cls} major` : cls,
      x1: 50 + r1 * Math.sin(a), y1: 50 - r1 * Math.cos(a),
      x2: 50 + outer * Math.sin(a), y2: 50 - outer * Math.cos(a),
    }));
  }
}

function tickStationClock() {
  const now = new Date();
  $("#now").textContent = timeFmt.format(now);
  const s = now.getSeconds() + now.getMilliseconds() / 1000;
  const m = now.getMinutes() + s / 60;
  const h = (now.getHours() % 12) + m / 60;
  // Swiss station clocks sweep the seconds hand in 58.5 s and rest at 12 for 1.5 s.
  const secAngle = state.online ? Math.min(s / 58.5, 1) * 360 : 0;
  $("#hand-second").style.transform = `rotate(${REDUCED_MOTION ? Math.floor(secAngle / 6) * 6 : secAngle}deg)`;
  $("#hand-minute").style.transform = `rotate(${Math.floor(m) * 6}deg)`;
  $("#hand-hour").style.transform = `rotate(${h * 30}deg)`;
}

function startStationClock() {
  buildTicks($("#station-ticks"), 60, 5, 40, 45, "clock__tick");
  const loop = () => { tickStationClock(); requestAnimationFrame(loop); };
  if (REDUCED_MOTION) { tickStationClock(); setInterval(tickStationClock, 1000); } else loop();
}

/* ---------- settings ---------- */

async function loadConfig() {
  const cfg = await getJSON("/api/config");
  state.cfg = cfg;
  state.cfgLoaded = true;
  $("#set-threshold").textContent = cfg.threshold.toFixed(2);
  $("#set-dwell").textContent = `${cfg.dwell_s} s`;
  $("#set-gap").textContent = `${cfg.max_gap_s} s`;
  $("#set-cooldown").textContent = `${cfg.cooldown_s} s`;
}

/* ---------- devices timetable ---------- */

function deviceState(d, nowS) {
  if (nowS - d.last_ts > STALE_S) return { kind: "nosignal", label: "No signal", detail: "", rank: 3 };
  if (d.last_positive && d.last_dwell_s >= state.cfg.dwell_s) {
    return { kind: "warning", label: "Warning", detail: secs(d.last_dwell_s), rank: 0 };
  }
  if (d.last_positive) {
    return { kind: "pedestrian", label: "Pedestrian", detail: `${secs(d.last_dwell_s)} of ${state.cfg.dwell_s} s`, rank: 1 };
  }
  return { kind: "clear", label: "Clear", detail: "", rank: 2 };
}

function buildDial() {
  const dial = svg("svg", { class: "dial", viewBox: "0 0 100 100", "aria-hidden": "true" });
  const ticks = svg("g");
  dial.append(svg("circle", { class: "dial__face", cx: 50, cy: 50, r: 46 }), ticks);
  const hand = svg("g", { class: "dial__hand" });
  hand.append(svg("line", { x1: 50, y1: 58, x2: 50, y2: 18 }), svg("circle", { cx: 50, cy: 18, r: 8 }));
  dial.append(hand);
  return { dial, ticks, hand, tickCount: -1 };
}

function updateDial(parts, kind, dwell) {
  const count = Math.max(1, Math.min(12, Math.round(state.cfg.dwell_s)));
  if (parts.tickCount !== count) {
    parts.ticks.replaceChildren();
    buildTicks(parts.ticks, count, 0, 36, 44, "dial__tick");
    parts.tickCount = count;
  }
  parts.dial.dataset.kind = kind;
  const fraction = kind === "pedestrian" ? Math.min(dwell / state.cfg.dwell_s, 1) : kind === "warning" ? 1 : 0;
  parts.hand.style.transform = `rotate(${fraction * 360}deg)`;
}

function selectDevice(mac) {
  state.selected = state.selected === mac ? "" : mac;
  for (const [m, parts] of state.rows) parts.tr.setAttribute("aria-selected", String(m === state.selected));
  $("#frames-scope").textContent = state.selected ? `Device ${state.selected}` : "All devices";
  $("#show-all").hidden = !state.selected;
  resetFrames();
}

function buildRow(mac) {
  const tr = el("tr");
  tr.setAttribute("aria-selected", "false");
  const dialParts = buildDial();
  const tdDial = el("td");
  tdDial.append(dialParts.dial);
  const tdDevice = el("td");
  const button = el("button", "device-select", mac);
  button.type = "button";
  button.setAttribute("aria-label", `Show frames from device ${mac}`);
  button.addEventListener("click", (e) => { e.stopPropagation(); selectDevice(mac); });
  tdDevice.append(button);
  const tdStatus = el("td");
  const tdConf = el("td", "num");
  const tdLast = el("td", "num hide-sm");
  const tdWarn = el("td", "num hide-sm");
  tr.append(tdDial, tdDevice, tdStatus, tdConf, tdLast, tdWarn);
  tr.addEventListener("click", () => selectDevice(mac));
  return { tr, ...dialParts, tdStatus, tdConf, tdLast, tdWarn };
}

function renderStatus(td, st) {
  const span = el("span", `status status--${st.kind}`);
  if (st.kind === "warning") span.append(warnIcon());
  span.append(document.createTextNode(st.label));
  td.replaceChildren(span);
  if (st.detail) td.append(document.createTextNode(" "), el("span", "status__detail", st.detail));
}

function renderDevices(devices) {
  const nowS = Date.now() / 1000;
  const tbody = $("#devices");
  const decorated = devices.map((d) => ({ d, st: deviceState(d, nowS) }));
  decorated.sort((a, b) => a.st.rank - b.st.rank || b.d.last_dwell_s - a.d.last_dwell_s || a.d.mac.localeCompare(b.d.mac));

  const present = new Set();
  for (const { d, st } of decorated) {
    present.add(d.mac);
    let parts = state.rows.get(d.mac);
    if (!parts) {
      parts = buildRow(d.mac);
      parts.tr.setAttribute("aria-selected", String(d.mac === state.selected));
      state.rows.set(d.mac, parts);
    }
    updateDial(parts, st.kind, d.last_dwell_s);
    parts.tr.classList.toggle("is-warning", st.kind === "warning");
    renderStatus(parts.tdStatus, st);
    parts.tdConf.textContent = conf(d.last_conf);
    parts.tdLast.textContent = clock(d.last_ts);
    parts.tdWarn.textContent = d.last_warning_ts ? clock(d.last_warning_ts) : "–";
    tbody.append(parts.tr); // moves existing rows into sorted order
  }
  for (const [mac, parts] of state.rows) {
    if (!present.has(mac)) { parts.tr.remove(); state.rows.delete(mac); }
  }

  $("#devices-empty").hidden = devices.length > 0;
  const counts = { warning: 0, pedestrian: 0 };
  for (const { st } of decorated) if (st.kind in counts) counts[st.kind] += 1;
  const parts = [`${devices.length} ${devices.length === 1 ? "device" : "devices"}`];
  if (counts.pedestrian) parts.push(`${counts.pedestrian} with pedestrian`);
  if (counts.warning) parts.push(`${counts.warning} warning`);
  $("#devices-meta").textContent = parts.join(" · ");
}

/* ---------- frames ---------- */

function frameItem(r) {
  const li = el("li", "frame");
  if (r.alerted) li.classList.add("frame--warning");
  if (r.positive) li.classList.add("frame--positive");

  const button = el("button", "frame__image");
  button.type = "button";
  button.setAttribute("aria-label", `Enlarge frame from ${r.mac} at ${clock(r.ts)}`);
  const img = el("img");
  img.src = r.thumb_url;
  img.alt = "";
  img.loading = "lazy";
  button.append(img);
  if (r.alerted) {
    const stamp = el("span", "frame__stamp");
    stamp.append(warnIcon(), document.createTextNode("Warning fired"));
    button.append(stamp);
  }
  const caption = `${r.mac} · ${clock(r.ts)} · confidence ${conf(r.conf)}`;
  button.addEventListener("click", () => openViewer(r.thumb_url, caption));
  li.append(button);

  const meta = el("div", "frame__meta");
  meta.append(el("span", "frame__time", clock(r.ts)), el("span", "frame__conf", conf(r.conf)));
  const bar = el("span", "conf-bar");
  const fill = el("span");
  fill.style.width = `${Math.round(Math.min(1, Math.max(0, r.conf)) * 100)}%`;
  bar.append(fill);
  meta.append(bar);
  const statusText = r.positive ? `Pedestrian · ${secs(r.dwell_s)}` : "Clear";
  meta.append(el("span", `frame__status${r.positive ? " frame__status--pedestrian" : ""}`, statusText));
  meta.append(el("span", "frame__device", r.mac));
  li.append(meta);
  return li;
}

function resetFrames() {
  state.generation += 1;
  state.lastId = 0;
  state.seen.clear();
  $("#frames").replaceChildren();
  pollFrames().catch(() => setOnline(false));
}

async function pollFrames() {
  const generation = state.generation;
  const params = new URLSearchParams({ limit: "100", after_id: String(state.lastId) });
  if (state.selected) params.set("mac", state.selected);
  const rows = await getJSON(`/api/inferences?${params}`);
  if (generation !== state.generation) return; // filter changed while in flight
  const list = $("#frames");
  for (const r of rows.slice().reverse()) {
    if (state.seen.has(r.id)) continue;
    state.seen.add(r.id);
    list.prepend(frameItem(r));
    state.lastId = Math.max(state.lastId, r.id);
  }
  while (list.children.length > MAX_FRAMES) list.lastElementChild.remove();
  const empty = $("#frames-empty");
  empty.hidden = list.children.length > 0;
  empty.textContent = state.selected ? `No frames from device ${state.selected} yet.` : "No frames yet.";
}

/* ---------- warnings ---------- */

function renderWarnings(alerts) {
  const tbody = $("#warnings");
  tbody.replaceChildren();
  for (const a of alerts) {
    const tr = el("tr");
    tr.append(el("td", "", clock(a.ts)), el("td", "device-id", a.mac), el("td", "num", secs(a.dwell_s)), el("td", "num hide-sm", conf(a.max_conf)));
    const td = el("td", "num");
    if (a.snapshot_url) {
      const view = el("button", "button button--quiet", "View");
      view.type = "button";
      view.setAttribute("aria-label", `View snapshot of warning at ${clock(a.ts)} from ${a.mac}`);
      view.addEventListener("click", () => openViewer(a.snapshot_url, `Warning · ${a.mac} · ${clock(a.ts)} · dwell ${secs(a.dwell_s)}`));
      td.append(view);
    } else {
      td.append(el("span", "status__detail", "No image"));
    }
    tr.append(td);
    tbody.append(tr);
  }
  $("#warnings-empty").hidden = alerts.length > 0;
}

/* ---------- viewer ---------- */

function openViewer(url, caption) {
  const img = el("img");
  img.src = url;
  img.alt = caption;
  $("#viewer-media").replaceChildren(img);
  $("#viewer-caption").textContent = caption;
  $("#viewer").showModal();
}

/* ---------- loops ---------- */

function every(ms, fn) {
  const run = async () => {
    if (!state.paused) {
      try {
        await fn();
        setOnline(true);
      } catch (err) {
        console.warn(err);
        setOnline(false);
      }
    }
    setTimeout(run, ms);
  };
  run();
}

async function pollStatus() {
  if (!state.cfgLoaded) await loadConfig();
  renderDevices(await getJSON("/api/devices"));
  await pollFrames();
}

function init() {
  startStationClock();
  renderLinkState();
  $("#pause").addEventListener("click", (e) => {
    state.paused = !state.paused;
    e.currentTarget.setAttribute("aria-pressed", String(state.paused));
    e.currentTarget.textContent = state.paused ? "Resume" : "Pause";
    renderLinkState();
  });
  $("#show-all").addEventListener("click", () => selectDevice(state.selected));
  $("#viewer").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
  every(POLL_MS, pollStatus);
  every(WARNINGS_MS, async () => renderWarnings(await getJSON("/api/alerts")));
}

init();
