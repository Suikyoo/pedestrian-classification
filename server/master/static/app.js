// Dashboard: polls the read-only API. Device-provided text is set with textContent only.
const POLL_MS = 2000;
const SIDE_MS = 10000;
const MAX_CARDS = 200;

const state = { lastId: 0, paused: false, mac: "", cfg: null };
const $ = (sel) => document.querySelector(sel);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json();
}

function setReachable(ok) {
  $("#banner").hidden = ok;
}

function timeOf(ts) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function openViewer(url) {
  if (!url) return;
  const dialog = $("#viewer");
  dialog.querySelector("img").src = url;
  dialog.showModal();
}

function card(r) {
  const node = el("article", "card" + (r.alerted ? " alert" : ""));
  const img = el("img");
  img.src = r.thumb_url;
  img.loading = "lazy";
  img.alt = "Frame";
  img.addEventListener("click", () => openViewer(r.thumb_url));
  node.append(img);

  const meta = el("div", "meta");
  const top = el("div", "row");
  top.append(el("span", "conf", r.conf.toFixed(2)));
  top.append(el("span", "badge " + (r.positive ? "pos" : "neg"), r.positive ? "PED" : "–"));
  if (r.alerted) top.append(el("span", "badge alert", "ALERT"));
  meta.append(top);

  const bar = el("div", "bar");
  const fill = el("span");
  fill.style.width = `${Math.round(Math.min(1, Math.max(0, r.conf)) * 100)}%`;
  bar.append(fill);
  meta.append(bar);

  if (r.positive && state.cfg) {
    meta.append(el("div", "small", `dwell ${r.dwell_s.toFixed(1)} / ${state.cfg.dwell_s} s`));
  }
  const foot = el("div", "row small");
  foot.append(el("span", "", r.mac));
  foot.append(el("span", "", timeOf(r.ts)));
  meta.append(foot);
  node.append(meta);
  return node;
}

async function pollInferences(limit = 100) {
  const mac = state.mac;
  const params = new URLSearchParams({ limit: String(limit), after_id: String(state.lastId) });
  if (mac) params.set("mac", mac);
  const rows = await getJSON(`/api/inferences?${params}`);
  if (mac !== state.mac) return; // filter changed while the request was in flight
  const grid = $("#grid");
  for (const r of rows.slice().reverse()) {
    grid.prepend(card(r));
    state.lastId = Math.max(state.lastId, r.id);
  }
  while (grid.children.length > MAX_CARDS) grid.lastElementChild.remove();
  $("#empty").hidden = grid.children.length > 0;
}

async function refreshSide() {
  const [devices, alerts] = await Promise.all([getJSON("/api/devices"), getJSON("/api/alerts")]);

  const select = $("#device");
  const current = select.value;
  select.replaceChildren(el("option", "", "All devices"));
  select.firstChild.value = "";
  for (const d of devices) {
    const opt = el("option", "", `${d.mac} (${d.count})`);
    opt.value = d.mac;
    select.append(opt);
  }
  select.value = current;

  const list = $("#alerts");
  list.replaceChildren();
  if (alerts.length === 0) list.append(el("li", "muted", "No alerts yet"));
  for (const a of alerts) {
    const item = el("li");
    item.append(el("div", "row", ""));
    item.firstChild.append(el("span", "", timeOf(a.ts)));
    item.firstChild.append(el("span", "conf", a.max_conf.toFixed(2)));
    item.append(el("div", "small", `${a.mac} · ${a.dwell_s.toFixed(1)} s`));
    item.addEventListener("click", () => openViewer(a.snapshot_url));
    list.append(item);
  }
}

async function loop(fn, ms) {
  if (!state.paused) {
    try {
      await fn();
      setReachable(true);
    } catch (err) {
      console.warn(err);
      setReachable(false);
    }
  }
  setTimeout(() => loop(fn, ms), ms);
}

async function init() {
  try {
    state.cfg = await getJSON("/api/config");
    $("#config").textContent = `threshold ${state.cfg.threshold} · dwell ${state.cfg.dwell_s} s`;
  } catch (err) {
    setReachable(false);
  }
  $("#device").addEventListener("change", (e) => {
    state.mac = e.target.value;
    state.lastId = 0;
    $("#grid").replaceChildren();
    pollInferences().catch(() => setReachable(false));
  });
  $("#pause").addEventListener("click", (e) => {
    state.paused = !state.paused;
    e.target.textContent = state.paused ? "Resume" : "Pause";
  });
  $("#viewer").addEventListener("click", () => $("#viewer").close());
  loop(pollInferences, POLL_MS);
  loop(refreshSide, SIDE_MS);
}

init();
