const DEFAULTS = { token: "", port: 8765, server: "", meetingId: "" };

async function post(cfg, text) {
  const hosted = !!cfg.server;
  const url = hosted
    ? cfg.server.replace(/\/+$/, "") + "/api/capture/meetings/" + encodeURIComponent(cfg.meetingId)
    : "http://127.0.0.1:" + cfg.port + "/api/captions";
  if (hosted && !cfg.meetingId) return { ok: false, error: "Choose a meeting in the extension options." };
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Capture-Token": cfg.token },
    body: JSON.stringify({ snapshot: text })
  });
  const j = await r.json().catch(() => ({}));
  return r.ok ? { ok: true, added: j.added || 0 } : { ok: false, error: j.detail || j.error || "HTTP " + r.status };
}

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type !== "snapshot") return;
  chrome.storage.local.get(DEFAULTS, async (cfg) => {
    if (!cfg.token) { reply({ ok: false, error: "Set the capture token in the extension options." }); return; }
    try {
      reply(await post(cfg, msg.text));
    } catch (e) {
      reply({ ok: false, error: cfg.server ? "Could not reach " + cfg.server : "Live Minutes app is not running on this computer." });
    }
  });
  return true;
});

chrome.action.onClicked.addListener(() => chrome.runtime.openOptionsPage());
