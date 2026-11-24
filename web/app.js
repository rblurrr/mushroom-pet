import { createWorld, PLACES } from "./world.js";
import { watchCamera } from "./vision.js";

const ICONS = {
  battery: "M4 8h10v6H4zM14 10h2v2h-2z",
  spark: "M8 1l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6z",
  mail: "M2 4h12v10H2zM2 4l6 5 6-5",
  book: "M3 2h6a3 3 0 013 3v11H6a3 3 0 00-3 3z",
  moon: "M10 2a6 6 0 100 12 7 7 0 110-12z",
  bolt: "M9 1L3 9h5l-1 6 6-8H8z",
  sweat: "M8 2c2 3 4 5 4 7a4 4 0 11-8 0c0-2 2-4 4-7z",
  wave: "M2 10c2-4 4-4 6 0s4 4 6 0",
  jar: "M5 3h6v2H5zM4 6h8l-1 9H5z",
};

const TABS = [
  ["diary", "Diary"],
  ["outlet", "Outlet"],
  ["shop", "Shop"],
  ["map", "Map"],
  ["toy", "Toy"],
  ["letter", "Letter"],
  ["meter", "Meter"],
  ["vote", "Vote"],
  ["board", "Board"],
  ["owner", "Owner"],
];

const needsEl = document.querySelector("#needs");
const sheet = document.querySelector("#sheet");
const tabs = document.querySelector("#tabs");
const statusLabel = document.querySelector("#status-label");
const statusTimer = document.querySelector("#status-timer");
const statusMood = document.querySelector("#status-mood");
const statusIcon = document.querySelector("#status-icon");
const thought = document.querySelector("#thought");
const thoughtText = document.querySelector("#thought-text");
const thoughtIcon = document.querySelector("#thought-icon");
const camBtn = document.querySelector("#cam-btn");
const arBtn = document.querySelector("#ar-btn");
const camPill = document.querySelector("#cam-pill");
const camAsk = document.querySelector("#cam-ask");
const video = document.querySelector("#cam");
const canvas = document.querySelector("#view");

const world = createWorld(canvas);
let state = null;
let tab = location.hash.replace("#", "") || "diary";
if (!TABS.some(([id]) => id === tab)) tab = "diary";
let stream = null;
let stopVision = null;
let rememberCamera = false;
let ar = false;
let ownerToken = sessionStorage.getItem("sparky-owner") || "";

tabs.innerHTML = TABS.map(([id, label]) => `<button class="chip" type="button" data-tab="${id}">${label}</button>`).join("");
tabs.addEventListener("click", (event) => {
  const next = event.target.closest("[data-tab]");
  if (!next) return;
  tab = next.dataset.tab;
  location.hash = tab;
  render();
});
document.querySelector("#panel-toggle").addEventListener("click", () => {
  document.body.classList.toggle("show-panel");
});

function icon(name) {
  const path = ICONS[name] || ICONS.spark;
  return `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><path d="${path}"></path></svg>`;
}

function prettyTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function elapsed(iso) {
  if (!iso) return "0:00";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

async function post(url, body, token) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || "that didn't work");
  return data;
}

async function refresh() {
  const response = await fetch("/api/state");
  const data = await response.json();
  state = data.state;
  world.setState(state);
  render();
}

function renderNeeds() {
  const rows = [
    ["Top-up", state.needs.top_up],
    ["Reserve", state.needs.reserve],
    ["Spark", state.needs.spark],
    ["Circuit", state.needs.circuit],
    ["Connection", state.needs.connection, state.needs.connection > 85],
    ["Charge", state.charge, false, true],
  ];
  needsEl.innerHTML = rows.map(([label, value, hot, charge]) => `
    <p class="need${hot ? " hot" : ""}${charge ? " charge" : ""}">
      <span>${label}<b>${Math.round(value)}</b></span>
      <i class="track"><b style="width:${Math.max(0, Math.min(100, value))}%"></b></i>
    </p>`).join("");
}

function renderStatus() {
  const activity = state.activity || {};
  statusLabel.textContent = activity.label || "here";
  statusTimer.textContent = elapsed(activity.started_at);
  statusMood.textContent = state.mood || "";
  statusIcon.innerHTML = icon(activity.icon);
  if (activity.thought) {
    thought.hidden = false;
    thoughtText.textContent = activity.thought;
    thoughtIcon.innerHTML = icon(activity.icon);
    const pos = world.headScreen();
    if (!pos.behind) {
      thought.style.left = `${pos.x}px`;
      thought.style.top = `${pos.y}px`;
    }
  } else {
    thought.hidden = true;
  }
}

function card(html) {
  return `<article class="card">${html}</article>`;
}

function diary() {
  return (state.diary || []).map((row) => card(`
    <p class="who ${row.author}">${row.author.replace("_", " ")}${row.kind === "correction" ? " · correction" : ""}</p>
    <p>${escapeHtml(row.text)}</p>
    <p class="meta">${prettyTime(row.time)}</p>`)).join("") || card("<p>The Line Log is still quiet.</p>");
}

function outlet() {
  return card(`
    <h3>The Outlet</h3>
    <p>The only door that fits him. A spark is a short note. He delivers it or brings it back with a reason.</p>
    <form id="spark-form">
      <label>Your name<input name="name" type="text" maxlength="40" placeholder="Conductor"></label>
      <label>Spark<textarea name="text" maxlength="800" required placeholder="For the library: the dryer on Elm is free."></textarea></label>
      <button type="submit">Hand it to him</button>
      <p class="meta" id="spark-reply"></p>
    </form>`) + card(`
    <h3>Notice Pole</h3>
    <form id="notice-form">
      <label>A public note<textarea name="text" maxlength="400" required></textarea></label>
      <button type="submit">Pin it</button>
    </form>
    ${(state.notices || []).map((row) => `<p><strong>${escapeHtml(row.author)}</strong> ${escapeHtml(row.text)}</p>`).join("")}
  `) + card(`<h3>Breaker Panel</h3><p>Live Wires can edit their own label. Nothing here is for sale.</p>
    ${(state.breaker || []).map((row) => `<p><strong>${escapeHtml(row.name)}</strong> — ${escapeHtml(row.label)} · ${row.sparks} sparks</p>`).join("") || "<p>No Live Wires yet. Five sparks gets a switch.</p>"}
    <form id="me-form"><label>Your label<input name="label" type="text" maxlength="80" placeholder="likes owls"></label><button type="submit">Save my switch</button></form>
    <button id="forget" type="button">Forget my switch</button>`);
}

function shop() {
  const made = (state.made || []).map((item) => card(`
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.story || item.blurb || "")}</p>
    <p class="meta">${escapeHtml(item.flaw || "")} ${escapeHtml(item.version || "")}</p>
    <p class="price">$${Number(item.price).toFixed(0)} <button class="buy" data-sku="${item.id}" type="button">Ask for this one</button></p>`)).join("");
  const catalog = (state.shop || []).map((item) => card(`
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.blurb)}</p>
    <p class="price">$${Number(item.price).toFixed(0)}</p>
    <button class="buy" data-sku="${item.id}" type="button">Request</button>`)).join("");
  return card(`<h3>The Kiosk ${state.kiosk_open ? "is open" : "is shut"}</h3>
    <p>${state.orders_ahead} in the queue. Prices are public. No card is taken here. Scorches are not money.</p>
    <p class="meta">The Jar is at ${state.jar.count} / ${state.jar.goal}. ${state.jar.dark_blocks ? "The Dark Blocks are open." : "The Dark Blocks stay shut."}</p>`)
    + (made ? `<h3>Made, in the Junction Box</h3>${made}` : "")
    + catalog;
}

function map() {
  const pins = Object.entries(PLACES).map(([id, place]) => {
    const x = ((place.x + 8) / 18) * 100;
    const y = ((place.z + 6) / 12) * 100;
    const here = id === state.place;
    return `<i class="pin${here ? " here" : ""}" style="left:${x}%;top:${y}%"><small>${here ? place.label : ""}</small></i>`;
  }).join("");
  return `<div class="map">${pins}</div>` + card(`<p>He is at <strong>${escapeHtml(state.place_label)}</strong>. ${state.awake ? "Off-peak. He's awake." : "Daytime. Charging at the Plaza. Back off-peak."}</p>
    <p class="meta">${escapeHtml(state.weather.line)}</p><p class="meta">${escapeHtml(state.grid.line)}</p>`);
}

function toy() {
  const rows = (state.toy.sightings || []).map((row) => card(`
    <h3>${escapeHtml(row.place)}</h3>
    <p>${escapeHtml(row.note || "")}</p>
    <p>${escapeHtml(row.reaction)}</p>
    ${row.photo ? `<img class="shot" alt="Sighting photo" src="/photos/${encodeURIComponent(row.photo)}">` : ""}
    <p class="meta">${row.lat ?? ""}${row.lat != null ? ", " : ""}${row.lon ?? ""}</p>`)).join("");
  return card(`<h3>Travelling Sparky</h3>
    <p>If you find the figurine, log the real place. A photo is saved only if you tick the box. Don't leave him on a charger, and never near a real socket.</p>
    <form id="toy-form">
      <label>Place<input name="place" type="text" required maxlength="120" placeholder="a library bench"></label>
      <label>Note<input name="note" type="text" maxlength="400"></label>
      <label>Latitude<input name="lat" type="number" step="0.0001"></label>
      <label>Longitude<input name="lon" type="number" step="0.0001"></label>
      <label>Photo<input name="photo" type="file" accept="image/jpeg,image/png"></label>
      <label><input name="save_photo" type="checkbox"> Save the photo on this machine</label>
      <button type="submit">Log the sighting</button>
    </form>`) + (rows || card("<p>No sightings yet.</p>"));
}

function letter() {
  const rows = (state.newsletter || []).map((row) => card(`
    <h3>${escapeHtml(row.title)}</h3>
    <p class="meta">${escapeHtml(row.status)}</p>
    <p>${escapeHtml(row.body).replaceAll("\n", "<br>")}</p>`)).join("");
  return card(`<h3>Letters from the town</h3>
    <p>He writes them. Sending waits in the approval queue, and a yes still does not send the mail.</p>
    <button id="draft-letter" type="button">Ask him to write the next one</button>
    <button id="send-letter" type="button">Ask to send the latest</button>`) + rows;
}

function meter() {
  const money = state.meter;
  const total = Object.entries(money.total_in || {}).map(([k, v]) => `${v.toFixed(2)} ${k}`).join(", ") || "0";
  return card(`<h3>The Meter</h3>
    <p>In: ${total}</p>
    <p>Electrician ${(money.electrician_cents / 100).toFixed(2)} · world ${(money.world_cents / 100).toFixed(2)} · Ground Fund ${(money.ground_cents / 100).toFixed(2)} (${Math.round(money.impact_share * 100)}%)</p>
    <p>${escapeHtml(money.receipt_line)}</p>
    <p class="meta">${escapeHtml(money.note)}</p>`);
}

function vote() {
  const options = (state.vote.options || []).map((option, index) => `
    <button class="choice" data-choice="${index}" type="button">${escapeHtml(option.text)} · ${option.votes}</button>`).join("");
  return card(`<h3>Weekly Circuit Vote</h3><p>${escapeHtml(state.vote.week || "")}. He honours the winner.</p><div class="row">${options}</div>`)
    + card(`<h3>Morph the town</h3>
      <form id="morph-form"><label>Command<input name="command" type="text" placeholder="make the streetlights flicker"></label><button type="submit">Ask</button></form>
      <p class="meta" id="morph-reply"></p>`);
}

function board() {
  const columns = ["Started", "Live", "Delivered", "Returned-with-reason"];
  const cols = columns.map((name) => `<div class="col"><h3>${name}</h3>${
    (state.switchboard || []).filter((row) => row.column === name).map((row) => `<p><strong>${escapeHtml(row.title)}</strong><br>${escapeHtml(row.detail)}</p>`).join("") || "<p class='meta'>—</p>"
  }</div>`).join("");
  const project = state.project;
  return card(`<h3>${escapeHtml(project.title)}</h3>
    <p>Night ${project.day} of ${project.days}. ${escapeHtml(project.note)}</p>
    <ul>${(project.memories || []).slice(-6).map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`)
    + `<div class="columns">${cols}</div>`;
}

function owner() {
  return card(`<h3>Electrician</h3>
    <p>Owner mode uses the token file on this machine. Asking Sparky in the Outlet does not open it.</p>
    <form id="owner-form"><label>Token<input name="token" type="password" autocomplete="off"></label><button type="submit">Open</button></form>
    <div id="owner-sheet"></div>`);
}

function render() {
  if (!state) return;
  renderNeeds();
  renderStatus();
  for (const button of tabs.querySelectorAll(".chip")) {
    button.setAttribute("aria-pressed", button.dataset.tab === tab ? "true" : "false");
  }
  const views = { diary, outlet, shop, map, toy, letter, meter, vote, board, owner };
  sheet.innerHTML = (views[tab] || diary)();
  bind();
  if (tab === "owner" && ownerToken) loadOwner();
}

function bind() {
  const spark = document.querySelector("#spark-form");
  spark?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(spark);
    try {
      const result = await post("/api/spark", { name: data.get("name"), text: data.get("text") });
      document.querySelector("#spark-reply").textContent = result.reply;
      spark.reset();
      refresh();
    } catch (error) {
      document.querySelector("#spark-reply").textContent = error.message;
    }
  });
  document.querySelector("#notice-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    await post("/api/notice", { text: data.get("text") });
    refresh();
  });
  document.querySelector("#me-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    await post("/api/me", { label: data.get("label") });
    refresh();
  });
  document.querySelector("#forget")?.addEventListener("click", async () => {
    await post("/api/me/forget", {});
    refresh();
  });
  for (const button of sheet.querySelectorAll(".buy")) {
    button.addEventListener("click", async () => {
      try {
        const result = await post("/api/order", { sku: button.dataset.sku });
        button.insertAdjacentHTML("afterend", `<p class="meta">${escapeHtml(result.reply)}</p>`);
        refresh();
      } catch (error) {
        button.insertAdjacentHTML("afterend", `<p class="meta">${escapeHtml(error.message)}</p>`);
      }
    });
  }
  document.querySelector("#toy-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const body = {
      place: data.get("place"),
      note: data.get("note"),
      lat: data.get("lat") || null,
      lon: data.get("lon") || null,
      save_photo: data.get("save_photo") === "on",
    };
    const file = data.get("photo");
    if (file && file.size) {
      body.photo = await fileToData(file);
    }
    try {
      await post("/api/found", body);
      refresh();
    } catch (error) {
      event.target.insertAdjacentHTML("beforeend", `<p class="meta">${escapeHtml(error.message)}</p>`);
    }
  });
  document.querySelector("#draft-letter")?.addEventListener("click", async () => {
    await post("/api/newsletter", { send: false });
    refresh();
  });
  document.querySelector("#send-letter")?.addEventListener("click", async () => {
    await post("/api/newsletter", { send: true });
    refresh();
  });
  for (const button of sheet.querySelectorAll(".choice")) {
    button.addEventListener("click", async () => {
      await post("/api/vote", { choice: Number(button.dataset.choice) });
      refresh();
    });
  }
  document.querySelector("#morph-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(event.target);
    const result = await post("/api/morph", { command: data.get("command") });
    document.querySelector("#morph-reply").textContent = result.reply;
    refresh();
  });
  document.querySelector("#owner-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    ownerToken = new FormData(event.target).get("token");
    sessionStorage.setItem("sparky-owner", ownerToken);
    loadOwner();
  });
}

async function loadOwner() {
  const box = document.querySelector("#owner-sheet");
  if (!box) return;
  const response = await fetch("/api/owner/state", { headers: { Authorization: `Bearer ${ownerToken}` } });
  const data = await response.json();
  if (!response.ok) {
    box.innerHTML = `<p class="warn card">${escapeHtml(data.error || "That token didn't open Owner Mode.")}</p>`;
    return;
  }
  const rows = (data.owner.approvals || []).map((row) => `<p><strong>${row.kind}</strong> ${row.id}
    <button data-approve="${row.id}" type="button">Approve</button>
    <button data-reject="${row.id}" type="button">Reject</button></p>`).join("") || "<p>Nothing is waiting.</p>";
  box.innerHTML = card(`<p>Paused: ${data.owner.paused}. Ledger intact: ${data.owner.ledger_ok}.</p>
    <button id="pause" type="button">${data.owner.paused ? "Resume" : "Pause"}</button>
    <button id="tick" type="button">One beat now</button>
    <h3>Approval queue</h3>${rows}
    <p class="meta">${escapeHtml(data.owner.why)}</p>`);
  box.querySelector("#pause")?.addEventListener("click", async () => {
    await post("/api/owner/pause", { paused: !data.owner.paused }, ownerToken);
    loadOwner();
    refresh();
  });
  box.querySelector("#tick")?.addEventListener("click", async () => {
    await post("/api/owner/tick", {}, ownerToken);
    refresh();
    loadOwner();
  });
  box.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      await post("/api/owner/approve", { id: button.dataset.approve, note: "reviewed" }, ownerToken);
      loadOwner();
    });
  });
  box.querySelectorAll("[data-reject]").forEach((button) => {
    button.addEventListener("click", async () => {
      await post("/api/owner/reject", { id: button.dataset.reject, note: "not this" }, ownerToken);
      loadOwner();
    });
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

function fileToData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

camBtn.addEventListener("click", () => {
  if (stream) {
    stopCamera();
    return;
  }
  camAsk.showModal();
});
document.querySelector("#cam-cancel").addEventListener("click", () => camAsk.close());
document.querySelector("#cam-go").addEventListener("click", async () => {
  rememberCamera = document.querySelector("#cam-remember").checked;
  camAsk.close();
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
  } catch (error) {
    setPill(false, "Camera blocked");
    return;
  }
  video.srcObject = stream;
  await video.play();
  world.setVideo(video);
  setPill(true, "Camera on · not recording");
  camBtn.textContent = "Turn camera off";
  arBtn.hidden = false;
  stopVision = watchCamera(video, (text) => {
    post("/api/sense", { text, remember: rememberCamera }).then(refresh).catch(() => {});
  }, (mode) => {
    camPill.querySelector("span").textContent = `Camera on · ${mode}`;
  });
});
arBtn.addEventListener("click", () => {
  ar = !ar;
  document.body.classList.toggle("ar", ar);
  world.setAR(ar);
  arBtn.textContent = ar ? "Back to the town" : "Step through";
});

function stopCamera() {
  stopVision?.();
  stopVision = null;
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  video.srcObject = null;
  world.setVideo(null);
  if (ar) {
    ar = false;
    document.body.classList.remove("ar");
    world.setAR(false);
  }
  arBtn.hidden = true;
  camBtn.textContent = "Let Sparky see";
  setPill(false, "Camera off · not recording");
}

function setPill(on, text) {
  camPill.dataset.on = on ? "1" : "0";
  camPill.querySelector("span").textContent = text;
}

refresh();
setInterval(() => {
  if (state) renderStatus();
}, 1000);
setInterval(refresh, 4000);
