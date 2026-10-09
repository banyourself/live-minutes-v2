const $ = (id) => document.getElementById(id);
let state = {};

function clock(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return (h ? h + ":" : "") + m + ":" + s;
}

function render() {
  const live = state.phase === "live";
  $("dot").className = "dot " + (live ? "live" : "wait");
  $("label").textContent = live ? "Live" : state.phase === "paused" ? "Paused" : "Pick captions";
  $("title").textContent = state.meetingTitle || "";
  $("lines").textContent = String(state.lines || 0);
}

setInterval(() => {
  $("timer").textContent = state.startedAt ? clock(Date.now() - state.startedAt) : "00:00";
}, 500);

$("draft").addEventListener("click", () => void window.lm.openMain("/meetings/" + encodeURIComponent(state.meetingId || "")));
$("panel").addEventListener("click", () => void window.lm.openCapture());
$("hide").addEventListener("click", () => void window.lm.setFloat(false));

window.lm.onState((s) => { state = s; render(); });
window.lm.getConfig().then((cfg) => { state = cfg.state; render(); });
