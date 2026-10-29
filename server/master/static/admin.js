"use strict";

// Field definitions mirror master/protocol.py (ranges are checked again on the server).
const FIELDS = [
  { key: "interval_ms", label: "Frame interval (ms)", type: "int", min: 100, max: 3600000 },
  { key: "jpeg_quality", label: "JPEG quality (lower is better)", type: "int", min: 0, max: 63 },
  { key: "frame_size", label: "Frame size", type: "select" },
  { key: "rotation", label: "Rotation (degrees)", type: "select" },
  { key: "volume", label: "Volume", type: "int", min: 0, max: 100 },
  { key: "threshold", label: "Alert threshold", type: "float", min: 0.05, max: 0.99 },
  { key: "dwell_s", label: "Dwell (s)", type: "float", min: 0, max: 600 },
  { key: "max_gap_s", label: "Max gap (s)", type: "float", min: 0.5, max: 60 },
  { key: "cooldown_s", label: "Cooldown (s)", type: "float", min: 0, max: 3600 },
];

const $ = (sel) => document.querySelector(sel);
const deviceSelect = $("#device");
const stateEl = $("#device-state");
const toastEl = $("#toast");
const fieldsEl = $("#fields");
const hintEl = $("#cfg-hint");

let meta = null;       // {config, defaults, frame_sizes, rotations}
let statusByMac = {};  // from /api/devices, the device's last reported settings
let toastTimer = 0;

function toast(text, tone) {
  toastEl.textContent = text;
  toastEl.dataset.tone = tone || "";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.textContent = ""; }, 5000);
}

async function api(path, body) {
  const opts = body === undefined
    ? {}
    : { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "admin-ui" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  let data = null;
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
  }
  return data;
}

function currentMac() { return deviceSelect.value; }

function initial(f) {
  const status = statusByMac[currentMac()] || {};
  if (meta.config && meta.config[f.key] !== undefined) return meta.config[f.key];
  if (status[f.key] != null) return status[f.key];
  return null;
}

function renderFields() {
  fieldsEl.replaceChildren();
  for (const f of FIELDS) {
    const wrap = document.createElement("label");
    wrap.className = "field";
    const label = document.createElement("span");
    label.className = "field__label";
    label.textContent = f.label;
    let input;
    if (f.type === "select") {
      input = document.createElement("select");
      const options = f.key === "frame_size" ? meta.frame_sizes : meta.rotations;
      for (const o of options) {
        const opt = document.createElement("option");
        opt.value = String(o);
        opt.textContent = String(o);
        input.append(opt);
      }
    } else {
      input = document.createElement("input");
      input.type = "number";
      input.inputMode = f.type === "int" ? "numeric" : "decimal";
      input.step = f.type === "int" ? "1" : "any";
      input.min = f.min;
      input.max = f.max;
    }
    input.name = f.key;
    const value = initial(f);
    if (value !== null) input.value = String(value);
    else if (f.type !== "select") input.placeholder = `default ${meta.defaults[f.key]}`;
    else input.selectedIndex = -1;
    input.dataset.initial = input.value;
    input.addEventListener("input", () => {
      wrap.dataset.dirty = String(input.value !== input.dataset.initial);
      wrap.dataset.invalid = "false";
    });
    wrap.append(label, input);
    if (f.type !== "select") {
      const range = document.createElement("span");
      range.className = "field__range";
      range.textContent = `${f.min} to ${f.max}`;
      wrap.append(range);
    }
    fieldsEl.append(wrap);
  }
  hintEl.textContent = meta.config
    ? "Only the fields you change are sent. The rest keep the camera's saved values."
    : "No saved settings were found for this camera. Only the fields you fill in are sent; the camera keeps the rest.";
}

function collectChanges() {
  const fields = {};
  let bad = false;
  for (const f of FIELDS) {
    const input = fieldsEl.querySelector(`[name="${f.key}"]`);
    if (input.value === input.dataset.initial || input.value === "") continue;
    let v = input.value;
    if (f.type === "int" || f.key === "rotation") v = Number.parseInt(v, 10);
    else if (f.type === "float") v = Number.parseFloat(v);
    if (typeof v === "number" && !Number.isFinite(v)) {
      input.closest(".field").dataset.invalid = "true";
      bad = true;
      continue;
    }
    fields[f.key] = v;
  }
  return bad ? null : fields;
}

async function loadConfig() {
  const mac = currentMac();
  if (!mac) return;
  try {
    meta = await api(`/api/admin/devices/${encodeURIComponent(mac)}/config`);
  } catch (e) {
    stateEl.textContent = e.message;
    stateEl.dataset.tone = "bad";
    return;
  }
  stateEl.dataset.tone = meta.connected ? "" : "bad";
  stateEl.textContent = meta.connected ? "" : "Not connected to the MQTT broker. Commands will fail until it reconnects.";
  renderFields();
}

async function loadDevices() {
  const res = await fetch("/api/devices");
  const devices = res.ok ? await res.json() : [];
  statusByMac = Object.fromEntries(devices.map((d) => [d.mac, d]));
  deviceSelect.replaceChildren();
  for (const d of devices) {
    const opt = document.createElement("option");
    opt.value = d.mac;
    opt.textContent = `${d.mac} (${d.online ? "online" : "offline"})`;
    deviceSelect.append(opt);
  }
  if (!devices.length) {
    stateEl.textContent = "No cameras yet. One appears after its first status message.";
    return;
  }
  await loadConfig();
}

async function run(label, path, body) {
  try {
    await api(path, body);
    toast(`${label} sent to ${currentMac()}`, "good");
  } catch (e) {
    toast(`${label} failed: ${e.message}`, "bad");
  }
}

for (const btn of document.querySelectorAll("[data-action]")) {
  btn.addEventListener("click", () => {
    const action = btn.dataset.action;
    if (action === "reboot" && !confirm(`Reboot ${currentMac()}? It goes offline for a few seconds.`)) return;
    run(btn.textContent.trim(), `/api/admin/devices/${encodeURIComponent(currentMac())}/command`, { action });
  });
}

$("#play-alert").addEventListener("click", () => {
  const repeat = Number.parseInt($("#repeat").value, 10);
  run("Alert sound", `/api/admin/devices/${encodeURIComponent(currentMac())}/alert`, { repeat });
});

$("#config-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const fields = collectChanges();
  if (fields === null) return toast("Fix the highlighted fields first", "bad");
  if (!Object.keys(fields).length) return toast("Nothing changed", "");
  try {
    const res = await api(`/api/admin/devices/${encodeURIComponent(currentMac())}/config`, { fields });
    toast(`Settings sent to ${currentMac()}`, "good");
    meta.config = res.config;
    renderFields();
  } catch (e) {
    toast(`Save failed: ${e.message}`, "bad");
  }
});

$("#reset").addEventListener("click", renderFields);
deviceSelect.addEventListener("change", loadConfig);
loadDevices();
