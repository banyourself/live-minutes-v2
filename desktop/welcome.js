const $ = (id) => document.getElementById(id);
const slides = [...document.querySelectorAll(".slide")];
const dots = [...document.querySelectorAll(".step-dot")];
let current = 0;

function go(n) {
  current = Math.max(0, Math.min(slides.length - 1, n));
  slides.forEach((s, i) => {
    s.hidden = i !== current;
    s.classList.toggle("rise", i === current);
  });
  dots.forEach((d, i) => {
    d.classList.toggle("on", i === current);
    d.setAttribute("aria-current", i === current ? "step" : "false");
  });
  const heading = slides[current].querySelector("h1");
  if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
}

document.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => go(current + 1)));
document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => go(current - 1)));
dots.forEach((d) => d.addEventListener("click", () => go(Number(d.dataset.go))));
document.addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea")) return;
  if (e.key === "ArrowRight") go(current + 1);
  if (e.key === "ArrowLeft") go(current - 1);
});

document.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => {
  void window.lm.finishWelcome(b.dataset.open);
}));

function showServer(cfg) {
  $("serverName").textContent = cfg.serverUrl.replace(/^https?:\/\//, "");
  $("url").value = cfg.customServer ? cfg.serverUrl : "";
  $("auth").value = (cfg.authOrigins || []).join("\n");
  $("version").textContent = "Version " + cfg.version;
}

$("toggleServer").addEventListener("click", () => {
  const form = $("serverForm");
  form.hidden = !form.hidden;
  $("toggleServer").setAttribute("aria-expanded", String(!form.hidden));
  $("toggleServer").textContent = form.hidden ? "Change" : "Hide";
  if (!form.hidden) $("url").focus();
});

$("saveServer").addEventListener("click", async () => {
  $("serverErr").textContent = "";
  const r = await window.lm.saveServer($("url").value, $("auth").value);
  if (!r.ok) { $("serverErr").textContent = r.error; return; }
  showServer(await window.lm.getConfig());
  $("serverErr").textContent = "";
  $("toggleServer").click();
});

function showUpdate(u) {
  const labels = { checking: "Checking…", downloading: "Downloading " + (u.percent || 0) + "%", ready: "Restart to update",
    current: "Up to date", error: "Try again" };
  $("updateBtn").textContent = labels[u.status] || "Check for updates";
  $("updateBtn").dataset.ready = u.status === "ready" ? "1" : "";
}

$("updateBtn").addEventListener("click", () => {
  if ($("updateBtn").dataset.ready) void window.lm.installUpdate();
  else void window.lm.checkUpdates();
});
window.lm.onState((s) => showUpdate(s.update || {}));

window.lm.getConfig().then((cfg) => {
  showServer(cfg);
  showUpdate(cfg.state.update || {});
  if (location.hash === "#server") {
    go(2);
    $("toggleServer").click();
  }
});

const SCRIPT = [
  ["Kevin", "Let's call the meeting to order at 2:05."],
  ["Jordan", "I move to approve the agenda."],
  ["Taylor", "Second."],
  ["Kevin", "All in favor? Motion carries, eight to zero."],
  ["Avery", "Club Rush is moving to the quad next Tuesday."],
  ["Kevin", "Any other business? Meeting adjourned at 2:55."]
];
const DRAFT = [
  ["Called to order at 2:05 p.m.", false, 0],
  ["Motion to approve the agenda (Jordan, seconded by Taylor)", true, 3],
  ["Club Rush moves to the quad next Tuesday.", false, 4],
  ["Adjourned at 2:55 p.m.", false, 5]
];
const lines = $("demoLines");
const draft = $("demoDraft");
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let step = 0;
let seconds = 0;
let sent = 0;

function line(who, text) {
  const li = document.createElement("li");
  const b = document.createElement("b");
  b.textContent = who;
  li.append(b, document.createTextNode(text));
  return li;
}

function bullet([text, motion]) {
  const li = document.createElement("li");
  if (motion) {
    li.className = "motion";
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = "CARRIED";
    li.append(tag);
  }
  li.append(document.createTextNode(text));
  return li;
}

function tick() {
  if (step >= SCRIPT.length) {
    step = 0;
    lines.replaceChildren();
    draft.replaceChildren();
  }
  lines.append(line(...SCRIPT[step]));
  while (lines.children.length > 4) lines.firstElementChild.remove();
  DRAFT.filter((d) => d[2] === step).forEach((d) => draft.append(bullet(d)));
  step += 1;
  sent += 3 + step;
  $("demoLinesCount").textContent = String(sent);
}

if (reduced) {
  SCRIPT.slice(-4).forEach((s) => lines.append(line(...s)));
  DRAFT.forEach((d) => draft.append(bullet(d)));
} else {
  tick();
  setInterval(tick, 1900);
}
setInterval(() => {
  seconds += 1;
  const text = String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
  $("demoClock").textContent = text;
  $("demoClock2").textContent = text;
}, 1000);
