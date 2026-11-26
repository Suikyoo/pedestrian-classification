"use strict";

const POLL_MS = 2000;
const WARNINGS_MS = 5000;
const STATUS_STALE_S = 150;
const SAMPLE_STALE_S = 10;
const GAP_S = 10;
const SAMPLES_PER_CAMERA = 48;
// JavaScript Date supports 100 million days on either side of the epoch.
const MAX_DATE_SECONDS = 8_640_000_000_000;
const state = {
  configured: false, paused: false, lastId: 0, camera: null, sampleId: null,
  devices: [], devicePollAt: null, warnings: [], samples: new Map(), loaded: new Set(),
  health: { status: null, warnings: null },
};
const deviceRows = new Map();
const warningRows = new Map();
const chartDataRows = new Map();
let chartView = null;
let thumbRecord = null;
let pollGeneration = 0;

const $ = id => document.getElementById(id);
const finite = Number.isFinite;
const validTimestamp = ts => finite(ts) && Math.abs(ts) <= MAX_DATE_SECONDS;
const timeFormat = new Intl.DateTimeFormat([], {hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23"});
const dateFormat = new Intl.DateTimeFormat([], {year: "numeric", month: "short", day: "numeric"});
const clock = ts => validTimestamp(ts) ? timeFormat.format(ts * 1000) : "—";
const date = ts => validTimestamp(ts) ? dateFormat.format(ts * 1000) : "—";
const stamp = ts => validTimestamp(ts) ? date(ts) + " · " + clock(ts) : "—";
const score = n => finite(n) ? n.toFixed(2) : "—";
const seconds = n => finite(n) ? n.toLocaleString(undefined, {maximumFractionDigits: 2}) + " s" : "—";
const chronological = (a, b) => a.ts - b.ts || a.id - b.id;
const classification = r => r.positive === true ? "Pedestrian" : r.positive === false ? "Clear" : "—";

function element(tag, className, label) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (label !== undefined) node.textContent = label;
  return node;
}

function write(node, value) {
  if (node.textContent !== value) node.textContent = value;
}

function svg(tag, attributes, label) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (label !== undefined) node.textContent = label;
  return node;
}

async function getJSON(url) {
  const response = await fetch(url, {cache: "no-store"});
  if (!response.ok) throw new Error(url + " returned " + response.status);
  return response.json();
}

function renderConnection() {
  const values = Object.values(state.health);
  const down = values.includes(false);
  const live = values.every(v => v === true);
  const label = state.paused ? "Paused" : down ? "Reconnecting" : live ? "Live" : "Connecting";
  $("link-state").dataset.state = down && !state.paused ? "down" : label.toLowerCase();
  write($("link-state"), label);
  $("banner").hidden = !down || state.paused;
  if (state.devicePollAt !== null) renderDevices();
  else if (state.health.status === false) {
    write($("fleet-title"), "Status unavailable");
    write($("fleet-detail"), "Waiting for a device status update.");
  }
}

function cameraStatus(d, now) {
  if (!d.online) return ["offline", "Offline"];
  if (!validTimestamp(d.last_seen_ts) || now - d.last_seen_ts > STATUS_STALE_S) return ["stale", "No signal"];
  if (d.detect_ok === false) return ["fault", "Detector fault"];
  if (validTimestamp(d.last_warning_ts) && now - d.last_warning_ts < Math.max(d.cooldown_s ?? 30, SAMPLE_STALE_S)) {
    return ["warning", "◇ Recorded warning"];
  }
  if (!validTimestamp(d.last_ts) || now - d.last_ts > SAMPLE_STALE_S) return ["idle", "No recent sample"];
  if (d.last_positive == null) return ["idle", "No classification"];
  return d.last_positive ? ["pedestrian", "Pedestrian"] : ["clear", "Clear"];
}

function renderFleet(states) {
  const total = states.length;
  const counts = new Map();
  for (const kind of states) counts.set(kind, (counts.get(kind) || 0) + 1);
  const online = total - (counts.get("offline") || 0) - (counts.get("stale") || 0);
  let label = "Awaiting cameras";
  if (counts.has("warning")) label = "Recorded warning";
  else if (counts.has("pedestrian")) label = "Pedestrian in view";
  else if (counts.has("fault")) label = "Detector fault";
  else if (counts.has("clear")) label = "Monitoring";
  else if (online) label = "No recent sample";
  else if (total) label = "No signal";
  $("fleet-title").parentElement.classList.toggle("has-warning", counts.has("warning"));
  write($("fleet-title"), label);
  const active = counts.get("warning") || 0;
  let detail = total ? online + " of " + total + (total === 1 ? " camera online" : " cameras online") : "No devices have reported.";
  if (active) detail += " · " + active + " with a recent warning";
  if ((state.paused || state.health.status === false) && state.devicePollAt !== null) {
    detail += " · As of " + stamp(state.devicePollAt);
  }
  write($("fleet-detail"), detail);
}

function makeDeviceRow(mac) {
  const row = element("div", "camera");
  const head = element("div", "camera-head");
  const button = element("button", "", mac);
  button.type = "button";
  button.addEventListener("click", () => selectCamera(mac));
  const status = element("span", "camera-status");
  head.append(button, status);
  const data = element("dl", "camera-data");
  const parts = {};
  for (const [key, label] of Object.entries({score: "Device score", capture: "Captured at", seen: "Last seen", warning: "Last warning", cutoff: "Device cutoff", limit: "Dwell limit", streaming: "Reported streaming"})) {
    const group = element("div");
    parts[key] = element("dd");
    group.append(element("dt", "", label), parts[key]);
    data.append(group);
  }
  row.append(head, data);
  return {row, button, status, ...parts};
}

function removeMissing(nodes, ids) {
  for (const [id, parts] of nodes) {
    if (!ids.has(id)) {
      parts.row.remove();
      nodes.delete(id);
    }
  }
}

function renderDevices() {
  const now = Date.now() / 1000;
  const states = [];
  const ids = new Set();
  for (const d of state.devices) {
    ids.add(d.mac);
    if (!deviceRows.has(d.mac)) {
      const parts = makeDeviceRow(d.mac);
      deviceRows.set(d.mac, parts);
      $("devices").append(parts.row);
    }
    const parts = deviceRows.get(d.mac);
    const [kind, label] = cameraStatus(d, now);
    const selected = d.mac === state.camera;
    states.push(kind);
    parts.row.classList.toggle("is-selected", selected);
    parts.button.setAttribute("aria-pressed", String(selected));
    parts.status.dataset.kind = kind;
    write(parts.status, label);
    write(parts.score, score(d.last_device_score));
    write(parts.capture, stamp(d.last_ts));
    write(parts.seen, stamp(d.last_seen_ts));
    write(parts.warning, stamp(d.last_warning_ts));
    write(parts.cutoff, score(d.threshold));
    write(parts.limit, seconds(d.dwell_s));
    write(parts.streaming, d.streaming === true ? "On" : d.streaming === false ? "Off" : "—");
  }
  removeMissing(deviceRows, ids);
  $("devices-empty").hidden = ids.size > 0;
  write($("camera-count"), String(ids.size));
  renderFleet(states);

  const d = state.devices.find(device => device.mac === state.camera);
  const dwell = d?.last_dwell_s;
  const limit = d?.dwell_s;
  write($("dwell-camera"), state.camera ?? "No focused camera");
  write($("dwell-value"), seconds(dwell));
  write($("dwell-limit"), "Limit " + seconds(limit));
  const fraction = finite(dwell) && finite(limit) && limit > 0 ? Math.max(0, Math.min(1, dwell / limit)) : 0;
  $("dwell-fill").style.width = fraction * 100 + "%";
  let captureTime = d?.last_ts == null ? "No capture" : "Capture time unavailable";
  if (validTimestamp(d?.last_ts)) {
    captureTime = (now - d.last_ts > SAMPLE_STALE_S ? "Last capture " : "Captured ") + stamp(d.last_ts);
  }
  write($("dwell-time"), captureTime);
}

function selectCamera(mac) {
  if (state.camera === mac) return;
  const lastCamera = state.camera;
  state.camera = mac;
  state.sampleId = null;
  trimPinnedSample(lastCamera);
  renderDevices();
  renderChart();
}

function retainSamples(mac, incoming) {
  const previous = state.samples.get(mac) || [];
  const byId = new Map(previous.map(r => [r.id, r]));
  for (const r of incoming) if (finite(r.ts)) byId.set(r.id, r);
  const sorted = [...byId.values()].sort(chronological);
  const recent = sorted.slice(-SAMPLES_PER_CAMERA);
  // Keep the inspected record even after it ages out of the normal window.
  const pinned = mac === state.camera ? byId.get(state.sampleId) : null;
  if (pinned && !recent.some(r => r.id === pinned.id)) recent.unshift(pinned);
  state.samples.set(mac, recent);
}

function trimPinnedSample(mac) {
  const rows = state.samples.get(mac);
  if (rows?.length > SAMPLES_PER_CAMERA) retainSamples(mac, []);
}

function currentSample() {
  const rows = state.samples.get(state.camera) || [];
  if (state.sampleId === null) return rows.at(-1);
  return rows.find(r => r.id === state.sampleId);
}

function inspect(id) {
  if (id === state.sampleId) return;
  state.sampleId = id;
  trimPinnedSample(state.camera);
  renderChart();
  const r = currentSample();
  if (r) write($("selection-announcement"), stamp(r.ts) + " · " + classification(r) + " · Device score " + score(r.device_score) + " · YOLO score " + score(r.conf));
}

function navigate(delta) {
  const rows = state.samples.get(state.camera) || [];
  const index = rows.indexOf(currentSample());
  if (rows[index + delta]) inspect(rows[index + delta].id);
}

function evidence(r) {
  write($("sample-time"), r ? stamp(r.ts) + (r.alerted ? " · ◇ Recorded warning" : "") : "No sample selected");
  write($("sample-device"), score(r?.device_score));
  write($("sample-yolo"), score(r?.conf));
  write($("sample-dwell"), seconds(r?.dwell_s));
  write($("sample-class"), r ? classification(r) : "—");
  // Updating other cameras or receiving an identical poll must not reload the image.
  const key = r?.thumb_url || null;
  if (key === thumbRecord) return;
  thumbRecord = key;
  const button = $("thumb-open");
  button.querySelector("img")?.remove();
  button.hidden = !key;
  $("thumb-missing").hidden = Boolean(key);
  write($("thumb-missing"), "No capture");
  if (key) {
    const image = element("img");
    image.alt = "Selected capture from " + r.mac;
    image.addEventListener("error", () => {
      if (image.parentElement !== button) return;
      button.hidden = true;
      $("thumb-missing").hidden = false;
      write($("thumb-missing"), "Image unavailable");
    });
    image.src = key;
    button.prepend(image);
  }
}

function timeWindow(rows, warnings) {
  const records = rows.length ? rows : warnings;
  if (!records.length) return null;
  let start = records[0].ts, end = records.at(-1).ts;
  if (rows.length && warnings.length) {
    // Warnings keep extending the timeline even after streaming stops.
    end = Math.max(end, warnings.at(-1).ts);
    const firstVisible = warnings.find(w => w.ts >= start - GAP_S);
    if (firstVisible) start = Math.min(start, firstVisible.ts);
  }
  if (start === end) return [Math.max(-MAX_DATE_SECONDS, start - 1), Math.min(MAX_DATE_SECONDS, end + 1)];
  return [start, end];
}

function plotSeries(layer, rows, field, name, x, y, selected, detached) {
  let previous = null;
  const path = [];
  const points = [];
  for (const r of rows) {
    if (!finite(r[field])) {
      previous = null;
      continue;
    }
    const px = x(r.ts), py = y(r[field]);
    const join = previous !== null && r.ts - previous.ts <= GAP_S;
    path.push((join ? "L" : "M") + px + " " + py);
    points.push(svg("circle", {cx: px, cy: py, r: r.id === selected?.id ? 3.6 : 2.2, class: "point-" + name}));
    // The retained selection can be separated from the newest window by discarded records.
    previous = r === detached ? null : r;
  }
  if (path.length) layer.append(svg("path", {class: "series series-" + name, d: path.join(" ")}), ...points);
}

function makeChart(rows, alerts, selected) {
  const chart = $("chart");
  const width = Math.max(140, chart.clientWidth);
  const height = 168, left = 38, right = width - 18, top = 23, bottom = height - 30;
  const timedRows = rows.filter(r => validTimestamp(r.ts));
  const detached = rows.length > SAMPLES_PER_CAMERA ? rows[0] : null;
  const span = timeWindow(timedRows, alerts);
  const events = span ? alerts.filter(a => a.ts >= span[0] && a.ts <= span[1]) : [];
  const x = ts => left + (ts - span[0]) / (span[1] - span[0]) * (right - left);
  const y = value => bottom - Math.min(1, Math.max(0, value)) * (bottom - top);
  const layer = document.createDocumentFragment();
  for (const value of [1, .5, 0]) {
    layer.append(svg("line", {class: "grid", x1: left, x2: right, y1: y(value), y2: y(value)}));
    layer.append(svg("text", {class: "axis", x: left - 7, y: y(value) + 4, "text-anchor": "end"}, value.toFixed(1)));
  }
  const ticks = width < 430 ? 2 : 4;
  for (let i = 0; i <= ticks; i++) {
    const px = left + i / ticks * (right - left);
    layer.append(svg("line", {class: "grid minor", x1: px, x2: px, y1: top, y2: bottom}));
    if (span) {
      const ts = Math.min(span[1], span[0] + i / ticks * (span[1] - span[0]));
      // The endpoints remain legible at phone widths. The data table gives full timestamps.
      const label = span[1] - span[0] >= 86400 ? new Date(ts * 1000).toLocaleDateString(undefined, {month: "short", day: "numeric"}) : clock(ts);
      const anchor = i === 0 ? "start" : i === ticks ? "end" : "middle";
      layer.append(svg("text", {class: "axis", x: px, y: height - 9, "text-anchor": anchor}, label));
    }
  }
  if (span) {
    if (validTimestamp(selected?.ts)) layer.append(svg("line", {class: "selector", x1: x(selected.ts), x2: x(selected.ts), y1: top - 4, y2: bottom}));
    plotSeries(layer, timedRows, "device_score", "device", x, y, selected, detached);
    plotSeries(layer, timedRows, "conf", "yolo", x, y, selected, detached);
    for (const a of events) {
      const px = x(a.ts);
      const marker = svg("g", {"data-warning": a.id});
      marker.append(svg("title", {}, "Recorded warning · " + stamp(a.ts)));
      marker.append(svg("rect", {x: px - 8, y: 1, width: 16, height: 20, fill: "transparent"}));
      marker.append(svg("path", {class: "event", d: "M" + px + " 5l5 5-5 5-5-5z"}));
      layer.append(marker);
    }
  }
  chart.replaceChildren(layer);
  chartView = {rows, timedRows, events, x};
  $("plot-empty").hidden = timedRows.some(r => finite(r.conf) || finite(r.device_score));
  const empty = timedRows.length ? "No scores reported" : rows.length ? "Capture time unavailable" : "Waiting for samples";
  write($("plot-empty"), empty);
}

function renderChartData() {
  if (!$("chart-details").open || !chartView) return;
  const {rows, events} = chartView;
  const records = [
    ...rows.map(r => ({key: "sample-" + r.id, ts: r.ts, fields: [stamp(r.ts), score(r.device_score), score(r.conf), classification(r)]})),
    ...events.map(a => ({key: "warning-" + a.id, ts: a.ts, fields: [stamp(a.ts), "—", "—", "◇ Recorded warning"]})),
  ].sort((a, b) => a.ts - b.ts);
  const body = $("chart-data");
  removeMissing(chartDataRows, new Set(records.map(record => record.key)));
  let next = body.firstElementChild;
  for (const {key, fields} of records) {
    if (!chartDataRows.has(key)) {
      const row = element("tr");
      const cells = fields.map(() => element("td"));
      row.append(...cells);
      chartDataRows.set(key, {row, cells});
    }
    const {row, cells} = chartDataRows.get(key);
    fields.forEach((value, index) => write(cells[index], value));
    if (row !== next) body.insertBefore(row, next);
    next = row.nextElementSibling;
  }
}

function renderChart() {
  const rows = state.samples.get(state.camera) || [];
  const selected = currentSample();
  const index = rows.indexOf(selected);
  const alerts = state.warnings.filter(a => a.mac === state.camera && validTimestamp(a.ts)).sort(chronological);
  makeChart(rows, alerts, selected);
  write($("chart-scope"), state.camera ?? "No focused camera");
  write($("sample-position"), selected ? "Sample " + (index + 1) + " of " + rows.length : "No samples");
  $("prev").setAttribute("aria-disabled", String(index <= 0));
  $("next").setAttribute("aria-disabled", String(index < 0 || index >= rows.length - 1));
  $("latest").setAttribute("aria-pressed", String(state.sampleId === null));
  evidence(selected);
  renderChartData();
}

function openViewer(url, caption) {
  if (!url) return;
  const image = element("img");
  image.alt = caption;
  image.src = url;
  $("viewer-media").replaceChildren(image);
  write($("viewer-caption"), caption);
  $("viewer").showModal();
}

function openWarning(w) {
  if (w) openViewer(w.snapshot_url, "Recorded warning · " + w.mac + " · " + stamp(w.ts) + " · Reported dwell " + seconds(w.dwell_s) + " · Max score " + score(w.max_conf));
}

function warningRow(a) {
  const row = element("tr");
  row.append(element("td", "record-mark", "◇ " + stamp(a.ts)), element("td", "", a.mac), element("td", "", seconds(a.dwell_s)), element("td", "", score(a.max_conf)));
  const media = element("td");
  if (a.snapshot_url) {
    const button = element("button", "text-button", "View snapshot");
    button.type = "button";
    button.setAttribute("aria-label", "View recorded warning from " + a.mac + " at " + stamp(a.ts));
    button.addEventListener("click", () => openWarning(a));
    media.append(button);
  } else media.textContent = "No image";
  row.append(media);
  return {row};
}

function renderWarnings(records) {
  state.warnings = records.slice().sort((a, b) => chronological(b, a));
  const newest = state.warnings[0];
  $("recent").classList.toggle("has-warning", Boolean(newest));
  write($("warning-time"), newest ? clock(newest.ts) : "None recorded");
  write($("warning-device"), newest ? date(newest.ts) + " · " + newest.mac : "Across all cameras");
  $("warning-open").hidden = !newest?.snapshot_url;
  const body = $("warnings");
  const ids = new Set(state.warnings.map(a => a.id));
  removeMissing(warningRows, ids);
  let next = body.firstElementChild;
  for (const a of state.warnings) {
    if (!warningRows.has(a.id)) warningRows.set(a.id, warningRow(a));
    const {row} = warningRows.get(a.id);
    // Insert new arrivals without detaching a focused snapshot button.
    if (row !== next) body.insertBefore(row, next);
    next = row.nextElementSibling;
  }
  $("warnings-empty").hidden = Boolean(newest);
  write($("warnings-empty"), "No recorded warnings");
  write($("warning-count"), records.length + (records.length === 1 ? " record" : " records") + " · All cameras");
  renderChart();
}

async function pollStatus(generation) {
  if (!state.configured) {
    const cfg = await getJSON("/api/config");
    if (generation !== pollGeneration) return;
    write($("set-threshold"), score(cfg.threshold));
    write($("set-history"), String(cfg.history ?? "—"));
    state.configured = true;
  }
  const devices = await getJSON("/api/devices");
  if (generation !== pollGeneration) return;
  state.devices = devices;
  state.devicePollAt = Date.now() / 1000;
  const present = new Set(state.devices.map(d => d.mac));
  const withSamples = new Set(state.devices.filter(d => d.count).map(d => d.mac));
  if (!present.has(state.camera)) {
    const fallback = state.devices.find(d => d.count) || state.devices[0];
    state.camera = fallback?.mac ?? null;
    state.sampleId = null;
  }
  for (const mac of state.loaded) {
    if (!withSamples.has(mac)) {
      state.loaded.delete(mac);
      state.samples.delete(mac);
      if (state.camera === mac) state.sampleId = null;
    }
  }
  renderDevices();
  renderChart();
  const backfills = await Promise.allSettled([...withSamples].filter(mac => !state.loaded.has(mac)).map(async mac => {
    const params = new URLSearchParams({mac, limit: String(SAMPLES_PER_CAMERA)});
    const samples = await getJSON("/api/inferences?" + params);
    if (generation !== pollGeneration) return;
    retainSamples(mac, samples);
    state.loaded.add(mac);
    if (mac === state.camera) renderChart();
  }));
  if (generation !== pollGeneration) return;
  const params = new URLSearchParams({limit: "100", after_id: String(state.lastId)});
  const fresh = await getJSON("/api/inferences?" + params);
  if (generation !== pollGeneration) return;
  const batches = new Map();
  for (const r of fresh) {
    state.lastId = Math.max(state.lastId, r.id);
    if (!present.has(r.mac)) continue;
    if (!batches.has(r.mac)) batches.set(r.mac, []);
    batches.get(r.mac).push(r);
  }
  for (const [mac, batch] of batches) retainSamples(mac, batch);
  if (batches.has(state.camera)) renderChart();
  const failed = backfills.find(result => result.status === "rejected");
  if (failed) throw failed.reason;
}

function every(ms, name, operation) {
  async function poll() {
    const generation = pollGeneration;
    try {
      if (state.paused) return;
      try {
        await operation(generation);
        if (generation !== pollGeneration) return;
        state.health[name] = true;
      } catch (error) {
        if (generation !== pollGeneration) return;
        console.warn(error);
        state.health[name] = false;
      }
      renderConnection();
    } finally {
      setTimeout(poll, ms);
    }
  }
  poll();
}

$("pause").addEventListener("click", () => {
  state.paused = !state.paused;
  if (state.paused) pollGeneration++;
  $("pause").setAttribute("aria-pressed", String(state.paused));
  write($("pause"), state.paused ? "Resume" : "Pause");
  renderConnection();
});
$("prev").addEventListener("click", () => navigate(-1));
$("next").addEventListener("click", () => navigate(1));
$("latest").addEventListener("click", () => inspect(null));
$("plot").addEventListener("keydown", event => {
  if (event.key === "ArrowLeft") navigate(-1);
  else if (event.key === "ArrowRight") navigate(1);
  else if (event.key === "Home" && chartView?.rows.length) inspect(chartView.rows[0].id);
  else if (event.key === "End") inspect(null);
  else return;
  event.preventDefault();
});
$("chart").addEventListener("click", event => {
  const marker = event.target.closest("[data-warning]");
  if (marker) {
    openWarning(chartView.events.find(a => String(a.id) === marker.dataset.warning));
    return;
  }
  if (!chartView?.timedRows.length) return;
  const {timedRows, x} = chartView;
  const px = event.clientX - $("chart").getBoundingClientRect().left;
  const nearest = timedRows.reduce((a, b) => Math.abs(x(b.ts) - px) < Math.abs(x(a.ts) - px) ? b : a);
  inspect(nearest.id);
});
$("warning-open").addEventListener("click", () => openWarning(state.warnings[0]));
$("thumb-open").addEventListener("click", () => {
  const r = currentSample();
  if (r) openViewer(r.thumb_url, "Selected sample · " + r.mac + " · " + stamp(r.ts));
});
$("viewer").addEventListener("click", event => {
  if (event.target === $("viewer")) $("viewer").close();
});
$("chart-details").addEventListener("toggle", renderChartData);
new ResizeObserver(renderChart).observe($("plot"));
function tick() { write($("now"), timeFormat.format(new Date())); }
tick();
setInterval(tick, 1000);
every(POLL_MS, "status", pollStatus);
every(WARNINGS_MS, "warnings", async generation => {
  const warnings = await getJSON("/api/alerts");
  if (generation !== pollGeneration) return;
  renderWarnings(warnings);
});
