import { Listener, Speaker } from "/js/speech.js";

// Panels that aren't on this page are simply skipped (the test page shows fewer panels).
const $ = (id) => document.getElementById(id) ?? document.createElement("div");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const speaker = new Speaker();
let busy = false;
let lastId = 0; // newest household message already on screen; the poller only adds newer ones
const spoken = new Set(); // message texts already spoken in this tab, never twice

// ---------- conversation ----------

function bubble(kind, text = "") {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  div.textContent = text;
  $("log").append(div);
  $("log").scrollTop = $("log").scrollHeight;
  return div;
}

function logTool(text, bad = false) {
  const div = document.createElement("div");
  div.className = `call ${bad ? "bad" : ""}`;
  div.textContent = text;
  $("toolLog").prepend(div);
}

// Streams one agent turn from the server into the chat: tool progress, then Anyaa's reply.
async function streamTurn(url, body) {
  busy = true;
  let reply = bubble("anyaa");
  reply.innerHTML = `<span class="thinking">thinking…</span>`;
  let started = false;

  try {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop();
      for (const frame of frames) {
        if (!frame.startsWith("data: ")) continue;
        const event = JSON.parse(frame.slice(6));
        if (event.type === "tool") {
          if (started) { reply = bubble("anyaa"); started = false; }
          const slow = ["get_plan", "change_plan"].includes(event.name) ? "planning the next few days…"
            : event.name === "approve_and_fill_cart" ? "filling your Instamart cart…" : "saving…";
          reply.innerHTML = `<span class="thinking">${slow}</span>`;
          logTool(`${event.name}(${JSON.stringify(event.args)})`);
          refreshState();
        } else if (event.type === "reply") {
          if (started) reply = bubble("anyaa");
          reply.textContent = event.text;
          started = true;
          say(event.text); // the whole reply in one go: no gaps between sentences
        }
      }
    }
  } catch (err) {
    bubble("error", `Connection problem: ${err.message}`);
  } finally {
    if (!started) reply.remove();
    // Everything this turn added is already on screen, so the poller mustn't add it again.
    const all = await fetch("/api/household/messages").then((r) => r.json()).catch(() => []);
    if (all.length) lastId = all[all.length - 1].id;
    busy = false;
    refreshState();
  }
}

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  bubble("user", text);
  await streamTurn("/api/household/turn", { text });
}

$("composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("text").value;
  $("text").value = "";
  send(text);
});

// ---------- voice: hold to talk, or tap to start and tap to stop ----------

const listener = new Listener({
  phrases: ["Dadi", "Nani", "Papa", "didi", "dal", "sabzi", "rajma", "karela", "sabudana", "poha", "Ekadashi", "Jain", "Instamart", "mungfali"],
  onInterim: (text) => ($("interim").textContent = text),
});
let listening = false;
let pressedAt = 0;

async function startListening() {
  if (listening || busy) return;
  listening = true;
  speaker.stop();
  $("mic").classList.add("live");
  try { await listener.start(); } catch (err) { bubble("error", `Mic error: ${err.message ?? err}`); stopListening(); }
}
async function stopListening() {
  if (!listening) return;
  listening = false;
  $("mic").classList.remove("live");
  const text = await listener.stop();
  $("interim").textContent = "";
  if (text) send(text);
}
$("mic").addEventListener("pointerdown", () => { pressedAt = Date.now(); listening ? stopListening() : startListening(); });
$("mic").addEventListener("pointerup", () => { if (Date.now() - pressedAt > 400) stopListening(); });
$("mute").addEventListener("change", (e) => speaker.setMuted(e.target.checked));

// ---------- state panel ----------

async function refreshState() {
  const [state, im, tg] = await Promise.all([
    fetch("/api/state").then((r) => r.json()),
    fetch("/api/instamart/status").then((r) => r.json()),
    fetch("/api/telegram/status").then((r) => r.json()).catch(() => ({ enabled: false })),
  ]);

  $("phase").textContent = state.household.phase.toLowerCase().replace("_", " ");
  $("steps").innerHTML = renderSteps(state.household.phase);
  $("instamartBadge").textContent = `Instamart: ${im.active}`;
  $("instamartBadge").className = `pill ${im.active === "mcp" ? "live" : ""}`;

  const prefsFor = (name) => state.preferences.filter((p) => (p.member ?? "").toLowerCase() === (name ?? "").toLowerCase());
  const chip = (p) => p.detail.toLowerCase() === "none"
    ? `<span class="chip" title="${esc(p.quote)}">${esc(p.category)}: none</span>`
    : `<span class="chip ${p.strict ? "allergy" : ""}" title="${esc(p.quote)}">${esc(p.category)}: ${esc(p.detail)}</span>`;

  $("members").innerHTML = state.members.length
    ? state.members.map((m) => `<div class="member"><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation ?? "")} · ${m.age_group} · ${m.diet} · spice ${m.spice_level}</span><div>${prefsFor(m.name).map(chip).join("")}</div></div>`).join("")
    : `<span class="muted">Nobody yet.</span>`;
  const household = state.preferences.filter((p) => !p.member);
  $("rules").innerHTML = household.length ? `<div class="member"><b>Whole house</b><div>${household.map(chip).join("")}</div></div>` : "";

  const cook = state.cook;
  $("cook").innerHTML = !cook ? `<span class="muted">Not set yet.</span>`
    : cook.household_cooks ? "No cook, the family cooks."
    : `<b>${esc(cook.name ?? "Cook")}</b>` + cook.visits.map((v) => `<div class="muted">${esc(v.label)} ${v.start.slice(0, 5)} · ${v.minutes} min · ${v.meals.join(", ")}</div>`).join("")
      + (cook.days_off.length ? `<div class="muted">Off: ${cook.days_off.join(", ")}</div>` : "")
      + (cook.known_dishes.length ? `<div>${cook.known_dishes.map((d) => `<span class="chip">${esc(d)}</span>`).join("")}</div>` : "")
      + telegramLine(cook, tg);

  $("plan").innerHTML = renderPlan(state.plan);
  $("clock").textContent = new Date(state.clock).toLocaleString("en-IN", { weekday: "short", hour: "2-digit", minute: "2-digit" });

  $("meals").innerHTML = state.household.meals_set ? state.household.meals.join(", ") : `<span class="muted">Not set yet.</span>`;

  $("instamart").innerHTML = !im.logged_in
    ? `<a href="/api/instamart/login"><button class="primary">Connect Instamart</button></a>`
    : im.address_id ? `<span class="pill live">Connected · address chosen</span>` : `<span class="pill live">Connected</span> <span class="muted">· address not chosen yet</span>`;
}

function telegramLine(cook, tg) {
  if (!tg.enabled || cook.household_cooks) return "";
  if (!cook.phone) return `<div class="muted">Telegram: no number yet</div>`;
  const last10 = cook.phone.replace(/\D/g, "").slice(-10);
  const linked = (tg.contacts || []).some((c) => c.phone === last10);
  return linked
    ? `<div><span class="pill live">Telegram connected</span></div>`
    : `<div class="muted">Telegram: ask the cook to open <a target="_blank" href="${tg.bot_link}">${tg.bot_link.replace("https://", "")}</a> and tap Start</div>`;
}

const NODES = ["FAMILY", "FOOD_NEEDS", "TASTES", "KITCHEN", "CONFIRM", "MEAL_PLAN", "GROCERIES", "RUNNING"];

function renderSteps(phase) {
  const at = NODES.indexOf(phase);
  return NODES.map((n, i) => `<span class="step ${i < at ? "done" : i === at ? "now" : ""}">${n.toLowerCase().replace("_", " ")}</span>`).join("");
}

function renderPlan(stored) {
  if (!stored) return `<span class="muted">Comes after setup.</span>`;
  const { plan, status, issues, cart } = stored;
  const days = {};
  for (const m of plan.meals) (days[m.day] ??= []).push(m);
  const label = (d) => new Date(d + "T00:00").toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "short" });
  const { stage } = stored;
  let html = `<span class="pill ${status === "agreed" ? "live" : ""}">${stage === "week" ? "whole week" : "today + tomorrow"} · ${status}</span>`;
  if (issues.length) html += issues.map((i) => `<div class="warn">⚠ ${esc(i.problem)}</div>`).join("");
  html += plan.prep_ahead.map((p) => `<div class="prep">⏰ ${esc(p)}</div>`).join("");
  for (const [day, meals] of Object.entries(days)) {
    html += `<div class="day">${label(day)}</div>`;
    for (const m of meals) {
      html += `<div class="meal"><span class="label">${m.meal}</span> · ` +
        m.dishes.map((d) => `${esc(d.name)}${d.for_whom.includes("everyone") || d.for_whom.length > 3 ? "" : ` <span class="muted">(${d.for_whom.map(esc).join(", ")})</span>`}`).join(" + ") +
        m.dishes.filter((d) => d.cook_note).map((d) => `<div class="note">↳ ${esc(d.cook_note)}</div>`).join("") + `</div>`;
    }
  }
  const g = plan.groceries;
  html += `<div class="muted" style="margin-top:8px">Groceries: ${g.filter((x) => x.where === "instamart").length} Instamart · ${g.filter((x) => x.where === "sabziwala").length} sabziwala</div>`;
  if (cart) {
    html += `<div style="margin-top:6px"><b>Cart</b> (${cart.mode}): ${cart.items.length} items, ₹${Math.round(cart.total)}</div>`;
    if (cart.sabziwala.length) html += `<a class="button" target="_blank" href="${cart.sabziwala_link}">Send ${cart.sabziwala.length} items to sabziwala on WhatsApp</a>`;
  }
  return html;
}

// ---------- start ----------

$("reset").addEventListener("click", async () => {
  if (busy) return;
  await fetch("/api/household/reset", { method: "POST" });
  $("log").innerHTML = "";
  $("toolLog").innerHTML = "";
  lastId = 0; // a fresh household numbers its messages from 1 again
  spoken.clear();
  await loadHistory();
  refreshState();
});

// Speak only in the tab you're looking at, and never the same message twice.
function say(text) {
  if (document.visibilityState !== "visible" || spoken.has(text)) return;
  spoken.add(text);
  speaker.say(text);
}

async function loadHistory() {
  const history = await fetch("/api/household/messages").then((r) => r.json());
  for (const m of history) bubble(m.role === "user" ? "user" : "anyaa", m.content);
  if (history.length) lastId = history[history.length - 1].id;
  await streamTurn("/api/household/start"); // if the current part hasn't started, Anyaa opens it
}

// Messages that arrive on their own (e.g. "the cook says paneer ran out, I've swapped it").
async function pollHousehold() {
  if (busy) return;
  const history = await fetch("/api/household/messages").then((r) => r.json());
  for (const m of history.filter((m) => m.id > lastId)) {
    if (m.role !== "user") { bubble("anyaa", m.content); say(m.content); }
  }
  if (history.length) lastId = history[history.length - 1].id;
}

// ---------- cook panel (test page) ----------

async function refreshCook() {
  const box = document.getElementById("cookLog");
  if (!box) return;
  const messages = await fetch("/api/cook/messages").then((r) => r.json());
  box.innerHTML = messages.map((m) => `<div class="cmsg ${m.role === "user" ? "cook" : "anyaa"}">${esc(m.content)}</div>`).join("")
    || `<span class="muted">Nothing yet. Press "Next step" once the week is agreed: the family is checked with first, then the cook is briefed.</span>`;
  box.scrollTop = box.scrollHeight;
}

document.getElementById("advance")?.addEventListener("click", async (e) => {
  e.target.disabled = true;
  e.target.textContent = "⏳ sending…";
  const r = await fetch("/api/clock/advance", { method: "POST" }).then((r) => r.json()).catch(() => ({}));
  e.target.disabled = false;
  e.target.textContent = "⏩ Next step";
  logTool(`clock → ${r.now ?? "?"} · ${r.event ?? "nothing upcoming"}`);
  refreshCook(); refreshState();
});

document.getElementById("cookForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("cookText");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  document.getElementById("cookLog").insertAdjacentHTML("beforeend", `<div class="cmsg cook">${esc(text)}</div><div class="cmsg anyaa thinking">…</div>`);
  await fetch("/api/cook/say", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  refreshCook(); refreshState(); pollHousehold();
});

setInterval(() => { pollHousehold(); refreshCook(); }, 6000);

loadHistory();
refreshState();
refreshCook();
speaker.warm();
