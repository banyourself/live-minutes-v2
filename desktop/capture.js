const $ = (id) => document.getElementById(id);
let state = {};
let opened = "";
let meetings = [];

function updateButton(b, u) {
  const labels = { checking: "Checking…", downloading: "Downloading " + (u.percent || 0) + "%", ready: "Restart to update to " + u.version,
    current: "Up to date", error: "Try the update check again" };
  b.textContent = labels[u.status] || "Check for updates";
  b.classList.toggle("ready", u.status === "ready");
  b.disabled = ["checking", "downloading"].includes(u.status);
  b.title = u.error || "";
}

function phaseLabel(s) {
  return { live: "Live", zoom: "Waiting for captions", paused: "Paused" }[s.phase] || "Ready";
}

function clock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return (h ? h + ":" : "") + m + ":" + s;
}

function stepState() {
  const one = !!(state.hasToken && state.organization);
  const two = one && !!state.meetingId;
  const three = two && ["zoom", "live", "paused"].includes(state.phase);
  const auto = !one ? "step1" : !two ? "step2" : three ? "" : "step3";
  const active = opened || auto;
  [["step1", one], ["step2", two], ["step3", three]].forEach(([id, done]) => {
    $(id).classList.toggle("done", done);
    $(id).classList.toggle("active", id === active);
  });
}

function render() {
  const connected = !!(state.hasToken && state.organization);
  $("connDot").className = "dot" + (connected ? " on" : "");
  $("connText").textContent = connected ? state.organization : state.hasToken ? "Checking token…" : "Not connected";
  $("tokenDone").hidden = !connected;
  $("tokenForm").hidden = connected;
  $("orgName").textContent = state.organization || "";
  const capturing = ["zoom", "live", "paused"].includes(state.phase);
  $("live").hidden = !capturing;
  $("liveDot").className = "dot " + (state.phase === "live" ? "live" : "wait");
  $("liveState").textContent = phaseLabel(state);
  $("liveTitle").textContent = state.meetingTitle || "";
  $("lines").textContent = String(state.lines || 0);
  $("drafting").textContent = state.drafting ? "Updating" : state.lines ? "Up to date" : "-";
  $("lastLine").textContent = state.lastLine || "Waiting for the first caption…";
  $("liveErr").textContent = state.error || "";
  $("floatOn").checked = state.floatOn !== false;
  $("version").textContent = state.version ? "Version " + state.version : "";
  updateButton($("updateBtn"), state.update || {});
  document.querySelectorAll(".card-pick").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.id === state.meetingId)));
  stepState();
}

setInterval(() => {
  $("timer").textContent = state.startedAt ? clock(Date.now() - state.startedAt) : "00:00";
}, 500);

function meetingCard(m) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "card-pick";
  b.setAttribute("role", "radio");
  b.dataset.id = m.id;
  const t = document.createElement("span");
  t.className = "t";
  t.textContent = m.title;
  const d = document.createElement("span");
  d.className = "muted";
  d.textContent = m.meeting_date || "Open now";
  b.append(t, d);
  b.addEventListener("click", async () => {
    opened = "";
    await window.lm.chooseMeeting(m.id, m.title);
  });
  return b;
}

async function loadMeetings() {
  $("tokenErr").textContent = "";
  const r = await window.lm.listMeetings();
  if (!r.ok) {
    $("tokenErr").textContent = r.error;
    return;
  }
  meetings = r.meetings || [];
  $("meetings").replaceChildren(...meetings.map(meetingCard));
  $("empty").hidden = meetings.length > 0;
  render();
}

$("saveToken").addEventListener("click", async () => {
  $("tokenErr").textContent = "";
  const r = await window.lm.saveToken($("token").value);
  $("token").value = "";
  if (!r.ok) { $("tokenErr").textContent = r.error; return; }
  opened = "";
  await loadMeetings();
});
$("token").addEventListener("keydown", (e) => { if (e.key === "Enter") $("saveToken").click(); });
$("replaceToken").addEventListener("click", () => {
  $("tokenDone").hidden = true;
  $("tokenForm").hidden = false;
  $("token").focus();
});
$("getToken").addEventListener("click", () => void window.lm.openMain("/settings?tab=capture"));
$("newMeeting").addEventListener("click", () => void window.lm.openMain("/meetings/new"));
$("refresh").addEventListener("click", (e) => { e.stopPropagation(); void loadMeetings(); });
$("help").addEventListener("click", () => void window.lm.openMain("/help/zoom"));
$("openDraft").addEventListener("click", () => void window.lm.openMain("/meetings/" + encodeURIComponent(state.meetingId)));
$("stop").addEventListener("click", () => void window.lm.stopCapture());
$("floatOn").addEventListener("change", (e) => void window.lm.setFloat(e.target.checked));

document.querySelectorAll(".step-head").forEach((h) => {
  h.addEventListener("click", () => {
    opened = h.parentElement.id;
    stepState();
  });
});

$("open").addEventListener("click", async () => {
  $("zoomErr").textContent = "";
  if (!state.meetingId) { $("zoomErr").textContent = "Choose a meeting first."; return; }
  const r = await window.lm.openZoom($("zoom").value);
  if (!r.ok) $("zoomErr").textContent = r.error;
});
$("zoom").addEventListener("keydown", (e) => { if (e.key === "Enter") $("open").click(); });

$("updateBtn").addEventListener("click", () => {
  if ((state.update || {}).status === "ready") void window.lm.installUpdate();
  else void window.lm.checkUpdates();
});

window.lm.onState((s) => { state = s; render(); });
window.lm.getConfig().then((cfg) => {
  state = cfg.state;
  render();
  if (cfg.state.hasToken) void loadMeetings();
});
