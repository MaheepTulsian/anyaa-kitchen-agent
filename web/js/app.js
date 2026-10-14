import { Listener, Speaker } from "/js/speech.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const speaker = new Speaker();
let busy = false;

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

async function send(text) {
  text = text.trim();
  if (!text || busy) return;
  busy = true;
  bubble("user", text);
  const reply = bubble("anyaa");
  reply.innerHTML = `<span class="thinking">thinking…</span>`;
  let started = false;

  try {
    const res = await fetch("/api/household/turn", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
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
        if (event.type === "delta") {
          if (!started) { reply.textContent = ""; started = true; }
          reply.textContent += event.text;
          speaker.feed(event.text);
          $("log").scrollTop = $("log").scrollHeight;
        } else if (event.type === "tool") {
          if (!started) reply.innerHTML = `<span class="thinking">saving…</span>`;
        } else if (event.type === "tool_result") {
          const r = event.result;
          logTool(`${event.name}(${JSON.stringify(event.args)}) → ${r.ok ? "ok" : r.error}`, !r.ok);
          refreshState();
        } else if (event.type === "error") {
          bubble("error", `Something went wrong: ${event.message}`);
        }
      }
    }
  } catch (err) {
    bubble("error", `Connection problem: ${err.message}`);
  } finally {
    speaker.flush();
    if (!started) reply.remove();
    busy = false;
    refreshState();
  }
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
  const [state, im] = await Promise.all([
    fetch("/api/state").then((r) => r.json()),
    fetch("/api/instamart/status").then((r) => r.json()),
  ]);

  $("phase").textContent = state.phase.toLowerCase();
  $("instamartBadge").textContent = `Instamart: ${im.active}`;
  $("instamartBadge").className = `pill ${im.active === "mcp" ? "live" : ""}`;

  const rulesFor = (id) => state.constraints.filter((c) => c.member_id === id);
  const chip = (c) => {
    if (c.kind === "allergen") {
      return c.value === "none" ? `<span class="chip">no allergies</span>`
        : `<span class="chip allergy" title="${esc(c.quote)}">allergy: ${esc(c.value)}${c.scope === "trace" ? " (even traces)" : ""}</span>`;
    }
    const label = `${c.kind.replace("_", " ")}: ${c.value.replaceAll("_", " ")}${c.scope ? ` (${c.scope})` : ""}`;
    return `<span class="chip ${c.strength === "hard" ? "hard" : ""}" title="${esc(c.quote)}">${esc(label)}</span>`;
  };

  $("members").innerHTML = state.members.length
    ? state.members.map((m) => `<div class="member"><b>${esc(m.name)}</b> <span class="muted">${esc(m.relation ?? "")} · ${m.age_group} · ${m.diet} · spice ${m.spice_level}</span><div>${rulesFor(m.id).map(chip).join("")}</div></div>`).join("")
    : `<span class="muted">Nobody yet.</span>`;
  const houseRules = rulesFor(null);
  $("rules").innerHTML = houseRules.length ? `<div class="member"><b>Whole house</b><div>${houseRules.map(chip).join("")}</div></div>` : "";

  const cook = state.cook;
  $("cook").innerHTML = !cook ? `<span class="muted">Not set yet.</span>`
    : cook.household_cooks ? "No cook, the family cooks."
    : `<b>${esc(cook.name ?? "Cook")}</b>` + cook.visits.map((v) => `<div class="muted">${esc(v.label)} ${v.start.slice(0, 5)} · ${v.minutes} min · ${v.meals.join(", ")}</div>`).join("")
      + (cook.days_off.length ? `<div class="muted">Off: ${cook.days_off.join(", ")}</div>` : "")
      + (cook.known_dishes.length ? `<div>${cook.known_dishes.map((d) => `<span class="chip">${esc(d)}</span>`).join("")}</div>` : "");

  $("meals").innerHTML = state.household.meals_set ? state.household.meals.join(", ") : `<span class="muted">Not set yet.</span>`;

  $("instamart").innerHTML = !im.logged_in
    ? `<a href="/api/instamart/login"><button class="primary">Connect Instamart</button></a>`
    : im.address_id ? `<span class="pill live">Connected · address chosen</span>` : `<span class="pill live">Connected</span> <span class="muted">· address not chosen yet</span>`;
}

// ---------- start ----------

$("reset").addEventListener("click", async () => {
  if (busy) return;
  await fetch("/api/household/reset", { method: "POST" });
  $("log").innerHTML = "";
  $("toolLog").innerHTML = "";
  await loadHistory();
  refreshState();
});

async function loadHistory() {
  const history = await fetch("/api/household/messages").then((r) => r.json());
  for (const m of history) bubble(m.role === "user" ? "user" : "anyaa", m.content);
}

loadHistory();
refreshState();
