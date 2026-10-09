const $ = (id) => document.getElementById(id);
const DEFAULTS = { token: "", port: 8765, server: "https://minutes.kevinle.tech", meetingId: "" };

function serverOk(server) {
  try {
    const u = new URL(server);
    return u.protocol === "https:" || (u.protocol === "http:" && ["localhost", "127.0.0.1"].includes(u.hostname));
  } catch {
    return false;
  }
}

chrome.storage.local.get(DEFAULTS, (cfg) => {
  $("server").value = cfg.server;
  if (cfg.server && cfg.token && serverOk(cfg.server)) void loadMeetings(cfg);
});

async function loadMeetings(cfg) {
  $("err").textContent = "";
  try {
    const r = await fetch(cfg.server.replace(/\/+$/, "") + "/api/capture/meetings", { headers: { "X-Capture-Token": cfg.token } });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || "HTTP " + r.status);
    const sel = $("meeting");
    sel.textContent = "";
    sel.append(new Option(j.meetings.length ? "Choose a meeting in " + j.organization : "No open meetings in " + j.organization, ""));
    j.meetings.forEach((m) => {
      const o = new Option(m.title + (m.meeting_date ? " · " + m.meeting_date : ""), m.id);
      o.selected = m.id === cfg.meetingId;
      sel.append(o);
    });
    $("pick").style.display = "";
  } catch (e) {
    $("err").textContent = "Could not load meetings: " + e.message;
  }
}

$("save").onclick = async () => {
  const server = $("server").value.trim().replace(/\/+$/, "");
  const token = $("token").value.trim();
  $("err").textContent = "";
  if (server && !serverOk(server)) {
    $("err").textContent = "Enter the full server address starting with https:// (http:// works only for localhost or 127.0.0.1).";
    return;
  }
  if (server) {
    const origin = new URL(server).origin + "/*";
    let granted = false;
    try {
      granted = await chrome.permissions.request({ origins: [origin] });
    } catch {
      $("err").textContent = "This version works with https://minutes.kevinle.tech. For another Live Minutes server, use the copy your district provides.";
      return;
    }
    if (!granted) { $("err").textContent = "Permission to reach " + server + " is needed."; return; }
  }
  const update = { server };
  if (token) update.token = token;
  chrome.storage.local.set(update, () => {
    $("msg").textContent = "Saved.";
    $("token").value = "";
    chrome.storage.local.get(DEFAULTS, (cfg) => { if (cfg.server && cfg.token) void loadMeetings(cfg); });
  });
};

$("meeting").onchange = (e) => {
  chrome.storage.local.set({ meetingId: e.target.value }, () => { $("msg").textContent = "Meeting saved."; });
};
