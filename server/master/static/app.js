// Pedestrian warnings dashboard. Polls the read-only API; device-provided text is set with textContent only.
"use strict";

const POLL_MS = 2000;
const WARNINGS_MS = 3000;
const STALE_S = 10;
const STATUS_STALE_S = 150; // devices send status every 60 s
const LOG_SIZE = 20;
const FRAMES_PER_DEVICE = 48; // a collapsed reel shows one row of these; the selected camera shows all
const SVG_NS = "http://www.w3.org/2000/svg";

const state = {
  cfg: { threshold: 0.6, history: 200 },
  cfgLoaded: false,
  selected: "",
  lastId: 0,
  paused: false,
  online: true,
  newestAlertId: null,
  newestAlert: null,
  summary: null, // camera counts from the last status poll
  cameras: new Map(), // mac -> tile parts
  strips: new Map(), // mac -> frame reel parts
  thumbs: new Map(), // mac -> { id, url, ts } of the newest frame
  cooldowns: new Map(), // mac -> cooldown_s the device reported
};

// A warning counts as current for the same window the camera tile shows "Warning".
function warningIsCurrent(a) {
  if (!a) return false;
  const spanS = Math.max(state.cooldowns.get(a.mac) ?? 30, STALE_S);
  return Date.now() / 1000 - a.ts < spanS;
}

const $ = (sel) => document.querySelector(sel);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function useIcon(id, className) {
  const icon = document.createElementNS(SVG_NS, "svg");
  icon.setAttribute("class", className || "icon");
  icon.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#${id}`);
  icon.append(use);
  return { icon, use };
}

const ICON_FOR = { warning: "i-alert", pedestrian: "i-walk", clear: "i-check", nosignal: "i-offline", past: "i-alert" };

function fillBadge(node, kind, label) {
  node.dataset.kind = kind;
  node.replaceChildren(useIcon(ICON_FOR[kind]).icon, document.createTextNode(label));
  return node;
}

async function getJSON(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

const timeFmt = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const clock = (ts) => timeFmt.format(new Date(ts * 1000));
const secs = (s) => `${s.toFixed(1)} s`;
const score = (s) => (s == null ? "–" : s.toFixed(2));

function ago(ts) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h} h ${m % 60} min ago`;
  return `${Math.floor(h / 24)} d ago`;
}

/* ---------- connection and summary ---------- */

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

function renderSummary() {
  const node = $("#summary");
  const c = state.summary;
  node.dataset.tone = c && c.warning ? "warning" : "";
  if (!c) {
    node.textContent = "Connecting to the server";
  } else if (c.total === 0) {
    node.textContent = "Waiting for cameras";
  } else {
    const cams = `${c.total} ${c.total === 1 ? "camera" : "cameras"}`;
    const parts = [];
    if (c.warning) parts.push(`${c.warning} warning`);
    if (c.pedestrian) parts.push(`${c.pedestrian} with someone in view`);
    if (c.nosignal) parts.push(`${c.nosignal} offline`);
    node.textContent = parts.length ? `${cams}: ${parts.join(", ")}` : `All clear on ${cams}`;
  }
}

function tick() {
  $("#now").textContent = timeFmt.format(new Date());
  renderBoardTiming();
  renderSummary();
}

/* ---------- settings ---------- */

async function loadConfig() {
  const cfg = await getJSON("/api/config");
  state.cfg = cfg;
  state.cfgLoaded = true;
  $("#set-threshold").textContent = cfg.threshold.toFixed(2);
  $("#set-history").textContent = String(cfg.history);
}

/* ---------- camera state ---------- */

// Devices decide warnings themselves. Frames (and so "Someone in view") exist only in stream mode.
function cameraState(d, nowS) {
  if (!d.online) return { kind: "nosignal", label: "Offline", detail: "", rank: 3 };
  if (d.last_seen_ts == null || nowS - d.last_seen_ts > STATUS_STALE_S) {
    return { kind: "nosignal", label: "No signal", detail: "", rank: 3 };
  }
  if (d.detect_ok === false) return { kind: "nosignal", label: "Detector fault", detail: "", rank: 3 };
  const cooldown = d.cooldown_s ?? 30;
  if (d.last_warning_ts != null && nowS - d.last_warning_ts < Math.max(cooldown, STALE_S)) {
    return { kind: "warning", label: "Warning", detail: `Warned at ${clock(d.last_warning_ts)}`, rank: 0 };
  }
  const fresh = d.last_ts != null && nowS - d.last_ts <= STALE_S;
  if (fresh && d.last_device_score != null && d.threshold != null && d.last_device_score >= d.threshold) {
    const limit = d.dwell_s == null ? "" : ` of ${d.dwell_s} s`;
    return { kind: "pedestrian", label: "Someone in view", detail: `In view ${secs(d.last_dwell_s ?? 0)}${limit}`, rank: 1 };
  }
  return { kind: "clear", label: "Clear", detail: "", rank: 2 };
}

/* ---------- camera tiles ---------- */

function selectCamera(mac) {
  state.selected = state.selected === mac ? "" : mac;
  for (const [m, parts] of state.cameras) parts.button.setAttribute("aria-pressed", String(m === state.selected));
  $("#frames-scope").textContent = state.selected ? `Camera ${state.selected}` : "All cameras";
  $("#show-all").hidden = !state.selected;
  renderStripVisibility();
  if (state.selected) {
    const smooth = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    $("#frames").scrollIntoView({ behavior: smooth ? "smooth" : "auto" });
  }
}

function buildTile(mac) {
  const li = el("li");
  const button = el("button", "tile");
  button.type = "button";
  button.setAttribute("aria-pressed", "false");
  const media = el("span", "tile__media");
  const placeholder = useIcon("i-camera", "tile__media-icon").icon;
  const badge = el("span", "badge");
  media.append(placeholder, badge);
  const body = el("span", "tile__body");
  const name = el("span", "tile__name", mac);
  const detail = el("span", "tile__detail");
  const meter = el("span", "meter");
  const fill = el("span", "meter__fill");
  meter.append(fill);
  const scores = el("span", "tile__scores");
  const age = el("span", "tile__age");
  body.append(name, detail, meter, scores);
  button.append(media, body);
  button.addEventListener("click", () => selectCamera(mac));
  li.append(button);
  return { li, button, media, placeholder, img: null, thumbId: null, badge, detail, fill, scores, age, fraction: 0 };
}

function scoreItem(label, value) {
  const span = el("span");
  span.append(document.createTextNode(`${label} `), el("b", "", value));
  return span;
}

function updateMeter(parts, kind, dwell, limit) {
  const progress = limit > 0 ? Math.min(dwell / limit, 1) : 1;
  const fraction = kind === "pedestrian" ? progress : kind === "warning" ? 1 : 0;
  // The meter only fills forward; when a run resets it snaps back without animating.
  const snapping = fraction < parts.fraction;
  parts.fill.classList.toggle("is-snapping", snapping);
  parts.fill.style.transform = `scaleX(${fraction})`;
  if (snapping) {
    parts.fill.getBoundingClientRect();
    requestAnimationFrame(() => parts.fill.classList.remove("is-snapping"));
  }
  parts.fraction = fraction;
}

function updateTileThumb(mac) {
  const parts = state.cameras.get(mac);
  const thumb = state.thumbs.get(mac);
  if (!parts || !thumb || parts.thumbId === thumb.id) return;
  const img = el("img");
  img.alt = "";
  img.src = thumb.url;
  img.decode().catch(() => {}).then(() => {
    if (parts.img) parts.img.replaceWith(img);
    else parts.media.prepend(img);
    parts.img = img;
    parts.placeholder.remove();
  });
  parts.thumbId = thumb.id;
}

function renderCameras(devices) {
  const nowS = Date.now() / 1000;
  const list = $("#cameras");
  const decorated = devices.map((d) => ({ d, st: cameraState(d, nowS) }));
  decorated.sort((a, b) => a.st.rank - b.st.rank || (b.d.last_dwell_s ?? 0) - (a.d.last_dwell_s ?? 0) || a.d.mac.localeCompare(b.d.mac));

  const present = new Set();
  for (const { d, st } of decorated) {
    present.add(d.mac);
    let parts = state.cameras.get(d.mac);
    if (!parts) {
      parts = buildTile(d.mac);
      state.cameras.set(d.mac, parts);
      parts.button.setAttribute("aria-pressed", String(d.mac === state.selected));
    }
    parts.button.dataset.kind = st.kind;
    fillBadge(parts.badge, st.kind, st.label);
    let detail = st.detail;
    if (!detail) {
      detail = d.threshold != null && d.dwell_s != null
        ? `Warns after ${d.dwell_s} s at ${d.threshold.toFixed(2)}`
        : "Settings not reported yet";
    }
    parts.detail.textContent = detail;
    updateMeter(parts, st.kind, d.last_dwell_s ?? 0, d.dwell_s ?? 0);
    if (d.cooldown_s != null) state.cooldowns.set(d.mac, d.cooldown_s);
    const scores = [scoreItem("Device", score(d.last_device_score))];
    if (d.last_conf != null) scores.push(scoreItem("YOLO", score(d.last_conf)));
    if (d.temp_c != null) scores.push(scoreItem("Chip", `${Math.round(d.temp_c)} °C`));
    // Home convention: say how fresh the picture is rather than how it is delivered.
    parts.age.textContent = d.streaming && d.last_ts != null ? ago(d.last_ts) : "Not streaming";
    scores.push(parts.age);
    parts.scores.replaceChildren(...scores);
    parts.button.setAttribute("aria-label", `Camera ${d.mac}: ${st.label}. ${detail}. Show its frames.`);
    updateTileThumb(d.mac);
    list.append(parts.li); // moves existing tiles into sorted order
  }
  for (const [mac, parts] of state.cameras) {
    if (!present.has(mac)) { parts.li.remove(); state.cameras.delete(mac); }
  }

  $("#cameras-empty").hidden = devices.length > 0;
  const counts = { total: devices.length, warning: 0, pedestrian: 0, nosignal: 0 };
  for (const { st } of decorated) if (st.kind in counts) counts[st.kind] += 1;
  state.summary = counts;
  $("#cameras-meta").textContent = devices.length ? `${devices.length} ${devices.length === 1 ? "camera" : "cameras"}` : "";
  renderSummary();
  return decorated;
}

/* ---------- hero: the latest warning ---------- */

function renderBoardTiming() {
  const a = state.newestAlert;
  if (!a) return;
  const board = $("#board");
  const active = warningIsCurrent(a);
  const next = active ? "active" : "archived";
  if (board.dataset.state !== next) {
    board.dataset.state = next;
    $("#board-title").textContent = active ? "Pedestrian warning" : "Last warning";
    fillBadge($("#board-badge"), active ? "warning" : "past", active ? "Warning now" : "Earlier");
  }
  $("#board-ago").textContent = ago(a.ts);
}

function renderBoard(alerts) {
  const board = $("#board");
  const a = alerts[0] || null;
  state.newestAlert = a;
  if (!a) {
    board.dataset.state = "empty";
    $("#board-title").textContent = "No warnings yet";
    $("#board-photo").hidden = true;
    $("#board-placeholder").hidden = false;
    $("#board-badge").hidden = true;
    $("#board-time-wrap").hidden = true;
    $("#board-facts").hidden = true;
    $("#board-note").hidden = false;
    state.newestAlertId = null;
    return;
  }
  $("#board-note").hidden = true;
  $("#board-badge").hidden = false;
  $("#board-time-wrap").hidden = false;
  $("#board-facts").hidden = false;
  if (a.id === state.newestAlertId) { renderBoardTiming(); return; }

  const first = state.newestAlertId === null;
  state.newestAlertId = a.id;
  $("#board-time").textContent = clock(a.ts);
  $("#board-camera").textContent = a.mac;
  $("#board-dwell").textContent = secs(a.dwell_s);
  $("#board-score").textContent = a.max_conf.toFixed(2);
  const photo = $("#board-photo");
  if (a.snapshot_url) {
    const img = el("img");
    img.alt = `Snapshot from camera ${a.mac} at ${clock(a.ts)}`;
    img.src = a.snapshot_url;
    photo.replaceChildren(img);
    photo.hidden = false;
    $("#board-placeholder").hidden = true;
    photo.setAttribute("aria-label", `Enlarge snapshot from camera ${a.mac} at ${clock(a.ts)}`);
    photo.onclick = () => openViewer(a.snapshot_url, `Warning from camera ${a.mac} at ${clock(a.ts)}, in view ${secs(a.dwell_s)}`);
  } else {
    photo.replaceChildren();
    photo.hidden = true;
    $("#board-placeholder").hidden = false;
  }
  board.dataset.state = "";
  renderBoardTiming();
  if (!first && board.dataset.state === "active") {
    board.classList.remove("is-arriving");
    board.getBoundingClientRect();
    board.classList.add("is-arriving");
  }
}

/* ---------- recent warnings ---------- */

function renderLog(alerts) {
  const earlier = alerts.slice(1, 1 + LOG_SIZE);
  const items = earlier.map((a) => {
    const li = el("li");
    const button = el("button", "row");
    button.type = "button";
    const caption = `Warning from camera ${a.mac} at ${clock(a.ts)}, in view ${secs(a.dwell_s)}`;
    button.setAttribute("aria-label", `Enlarge snapshot: ${caption}`);
    if (a.snapshot_url) {
      const img = el("img", "row__thumb");
      img.alt = "";
      img.loading = "lazy";
      img.src = a.snapshot_url;
      button.append(img);
      button.addEventListener("click", () => openViewer(a.snapshot_url, caption));
    } else {
      button.append(el("span", "row__thumb"));
      button.disabled = true;
    }
    const main = el("span", "row__main");
    main.append(el("span", "row__time", clock(a.ts)), el("span", "row__camera", a.mac));
    const dwell = el("span", "row__num");
    dwell.append(el("b", "", secs(a.dwell_s)), document.createTextNode("in view"));
    const conf = el("span", "row__num row__num--score");
    conf.append(el("b", "", a.max_conf.toFixed(2)), document.createTextNode("score"));
    button.append(main, dwell, conf);
    li.append(button);
    return li;
  });
  $("#log").replaceChildren(...items);
  $("#log-empty").hidden = earlier.length > 0;
  fitLog();
}

// Show only whole rows; say how many older warnings did not fit.
function fitLog() {
  const list = $("#log");
  const rows = [...list.children];
  rows.forEach((li) => { li.hidden = false; });
  const more = $("#log-more");
  more.hidden = true;
  if (list.scrollHeight <= list.clientHeight + 1) return;
  more.hidden = false; // reserve its line before measuring
  const bottom = list.getBoundingClientRect().bottom;
  let hiddenCount = 0;
  for (const li of rows) {
    if (li.getBoundingClientRect().bottom > bottom + 0.5) { li.hidden = true; hiddenCount += 1; }
  }
  more.textContent = `${hiddenCount} older ${hiddenCount === 1 ? "warning" : "warnings"} not shown`;
  more.hidden = hiddenCount === 0;
}

/* ---------- frames: one reel per camera, newest on the left ---------- */

function noteThumb(r) {
  const cur = state.thumbs.get(r.mac);
  if (!cur || r.id > cur.id) {
    state.thumbs.set(r.mac, { id: r.id, url: r.thumb_url });
    updateTileThumb(r.mac);
  }
}

function frameItem(r, img) {
  const li = el("li", "frame");
  li.dataset.id = String(r.id);
  if (r.alerted) li.classList.add("frame--warning");

  const button = el("button", "frame__image");
  button.type = "button";
  button.setAttribute("aria-label", `Enlarge frame from camera ${r.mac} at ${clock(r.ts)}`);
  button.append(img);
  if (r.alerted) button.append(fillBadge(el("span", "badge"), "warning", "Warning"));
  const caption = `Camera ${r.mac} at ${clock(r.ts)}: YOLO ${score(r.conf)}, device ${score(r.device_score)}`;
  button.addEventListener("click", () => openViewer(r.thumb_url, caption));
  li.append(button);

  const meta = el("div", "frame__meta");
  const flag = el("span", `frame__flag${r.positive ? " frame__flag--pedestrian" : ""}`);
  if (r.positive) flag.append(useIcon("i-walk").icon, document.createTextNode(secs(r.dwell_s)));
  else flag.textContent = "Clear";
  const scores = el("span", "frame__scores");
  scores.append(scoreItem("YOLO", score(r.conf)), scoreItem("Device", score(r.device_score)));
  meta.append(el("span", "frame__time", clock(r.ts)), flag, scores);
  li.append(meta);
  return li;
}

function buildStrip(mac) {
  const section = el("section", "reel");
  section.setAttribute("aria-label", `Frames from camera ${mac}`);
  const head = el("div", "reel-head");
  const badge = el("span", "badge");
  head.append(el("span", "reel-head__name", mac), badge);
  const list = el("ol", "frame-list");
  section.append(head, list);
  return { section, badge, list, ids: new Set(), loaded: false };
}

async function addFrames(strip, rows) {
  // Decode every thumbnail before it enters the reel so no tile shows blank.
  const fresh = rows.filter((r) => !strip.ids.has(r.id));
  const ready = await Promise.all(fresh.map(async (r) => {
    const img = el("img");
    img.alt = "";
    img.src = r.thumb_url;
    try { await img.decode(); } catch { /* broken image: keep the empty tile */ }
    return frameItem(r, img);
  }));
  for (const li of ready) {
    const id = Number(li.dataset.id);
    if (strip.ids.has(id)) continue;
    strip.ids.add(id);
    let before = null;
    for (const child of strip.list.children) {
      if (Number(child.dataset.id) < id) { before = child; break; }
    }
    strip.list.insertBefore(li, before);
  }
  while (strip.list.children.length > FRAMES_PER_DEVICE) {
    const last = strip.list.lastElementChild;
    strip.ids.delete(Number(last.dataset.id));
    last.remove();
  }
  syncInert(strip);
}

function visibleSlots(strip) {
  if (strip.section.classList.contains("reel--expanded")) return Infinity;
  const cols = getComputedStyle(strip.list).gridTemplateColumns.split(" ").filter(Boolean).length;
  return Math.max(1, cols);
}

// Tiles clipped out of a collapsed reel must not take focus or reach the accessibility tree.
function syncInert(strip) {
  const visible = visibleSlots(strip);
  [...strip.list.children].forEach((li, i) => { li.inert = i >= visible; });
}

function renderStripVisibility() {
  for (const [mac, strip] of state.strips) {
    strip.section.hidden = Boolean(state.selected) && mac !== state.selected;
    strip.section.classList.toggle("reel--expanded", mac === state.selected);
    syncInert(strip);
  }
}

async function renderStrips(decorated) {
  const container = $("#strips");
  const present = new Set();
  const backfills = [];
  for (const { d, st } of decorated) {
    if (!d.count) continue; // never streamed: no frames to show
    present.add(d.mac);
    let strip = state.strips.get(d.mac);
    if (!strip) {
      strip = buildStrip(d.mac);
      state.strips.set(d.mac, strip);
    }
    fillBadge(strip.badge, st.kind, st.label);
    // Reels keep the order cameras first appeared in, so photos never jump when a status changes.
    if (!strip.section.isConnected) container.append(strip.section);
    if (!strip.loaded) {
      strip.loaded = true;
      const params = new URLSearchParams({ mac: d.mac, limit: String(FRAMES_PER_DEVICE) });
      backfills.push(getJSON(`/api/inferences?${params}`).then((rows) => {
        rows.forEach(noteThumb);
        return addFrames(strip, rows);
      }));
    }
  }
  for (const [mac, strip] of state.strips) {
    if (!present.has(mac)) { strip.section.remove(); state.strips.delete(mac); }
  }
  renderStripVisibility();
  await Promise.all(backfills);
  $("#frames-empty").hidden = state.strips.size > 0;
}

async function pollNewFrames() {
  const params = new URLSearchParams({ limit: "100", after_id: String(state.lastId) });
  const rows = await getJSON(`/api/inferences?${params}`);
  const byMac = new Map();
  for (const r of rows) {
    state.lastId = Math.max(state.lastId, r.id);
    noteThumb(r);
    const strip = state.strips.get(r.mac);
    if (!strip) continue; // its backfill will load it
    if (!byMac.has(r.mac)) byMac.set(r.mac, []);
    byMac.get(r.mac).push(r);
  }
  await Promise.all([...byMac].map(([mac, list]) => addFrames(state.strips.get(mac), list)));
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
  const decorated = renderCameras(await getJSON("/api/devices"));
  await renderStrips(decorated);
  await pollNewFrames();
}

async function pollWarnings() {
  const alerts = await getJSON(`/api/alerts?limit=${LOG_SIZE + 1}`);
  renderBoard(alerts);
  renderLog(alerts);
  renderSummary();
}

function init() {
  renderLinkState();
  tick();
  setInterval(tick, 1000);
  $("#pause").addEventListener("click", (e) => {
    state.paused = !state.paused;
    e.currentTarget.setAttribute("aria-pressed", String(state.paused));
    $("#pause-label").textContent = state.paused ? "Resume" : "Pause";
    $("#pause-icon").setAttribute("href", state.paused ? "#i-play" : "#i-pause");
    renderLinkState();
  });
  $("#show-all").addEventListener("click", () => selectCamera(state.selected));
  $("#viewer").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
  $("#board").addEventListener("animationend", (e) => e.currentTarget.classList.remove("is-arriving"));
  window.addEventListener("resize", () => {
    for (const strip of state.strips.values()) syncInert(strip);
    fitLog();
  });
  every(POLL_MS, pollStatus);
  every(WARNINGS_MS, pollWarnings);
}

init();
