const { ipcRenderer } = require("electron");

window.addEventListener("DOMContentLoaded", () => {
  if (window.top !== window) return;
  let target = null;
  let timer = null;
  let lastSent = "";
  let picking = false;
  let hovered = null;

  const font = "600 12.5px 'Segoe UI Variable Text','Segoe UI',sans-serif";
  const bar = document.createElement("div");
  bar.style.cssText = "position:fixed;z-index:2147483647;right:16px;bottom:16px;display:flex;gap:10px;align-items:center;" +
    "padding:7px 8px 7px 14px;border-radius:999px;background:rgba(10,17,31,0.92);color:#e8eef8;font:" + font + ";" +
    "border:1px solid rgba(132,184,255,0.35);box-shadow:0 10px 28px rgba(0,0,0,0.45)";
  const dot = document.createElement("span");
  dot.style.cssText = "width:9px;height:9px;border-radius:50%;background:#7486a3;flex:none";
  const title = document.createElement("b");
  title.textContent = "Live Minutes";
  const st = document.createElement("span");
  st.style.cssText = "color:#a9b8d0;font-weight:500";
  const button = (label, primary) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.style.cssText = "height:30px;padding:0 14px;border-radius:999px;cursor:pointer;font:" + font + ";" +
      (primary ? "background:#84b8ff;color:#06101f;border:0" : "background:transparent;color:#e8eef8;border:1px solid rgba(132,184,255,0.4)");
    return b;
  };
  const pick = button("Pick captions area", true);
  const stopBtn = button("Stop", false);
  stopBtn.style.display = "none";
  bar.append(dot, title, st, pick, stopBtn);
  document.documentElement.appendChild(bar);

  const status = (text, color) => {
    st.textContent = text;
    dot.style.background = color || "#7486a3";
  };
  status("Turn on captions, then pick them");
  const outline = (el) => {
    if (hovered) hovered.style.outline = hovered.dataset.lmOutline || "";
    hovered = el;
    if (el) { el.dataset.lmOutline = el.style.outline; el.style.outline = "2px solid #84b8ff"; }
  };
  const onMove = (e) => { if (picking && !bar.contains(e.target)) outline(e.target); };
  const onClick = (e) => {
    if (!picking || bar.contains(e.target)) return;
    e.preventDefault();
    e.stopPropagation();
    picking = false;
    outline(null);
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("click", onClick, true);
    let el = e.target;
    while (el.parentElement && (el.innerText || "").length < 80 && el.parentElement !== document.body) el = el.parentElement;
    start(el);
  };

  pick.onclick = () => {
    picking = true;
    status("Click the captions or transcript panel", "#f2b33d");
    void ipcRenderer.invoke("lm:reader", "picking");
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("click", onClick, true);
  };
  stopBtn.onclick = () => stop("Stopped");

  function start(el) {
    target = el;
    lastSent = "";
    pick.style.display = "none";
    stopBtn.style.display = "";
    status("Reading captions", "#5fd49a");
    void ipcRenderer.invoke("lm:reader", "reading");
    const obs = new MutationObserver(() => schedule());
    obs.observe(el, { childList: true, subtree: true, characterData: true });
    target.lmObs = obs;
    schedule();
  }

  function stop(msg) {
    if (target && target.lmObs) target.lmObs.disconnect();
    target = null;
    clearTimeout(timer);
    pick.style.display = "";
    stopBtn.style.display = "none";
    status(msg || "Stopped", "#7486a3");
    void ipcRenderer.invoke("lm:reader", "stopped");
  }

  ipcRenderer.on("lm:command", (_e, command) => { if (command === "stop" && target) stop("Stopped"); });

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(send, 1500);
  }

  async function send() {
    if (!target) return;
    if (!document.contains(target)) return stop("Panel closed, pick it again");
    const text = target.innerText || "";
    if (!text.trim() || text === lastSent) return;
    lastSent = text;
    const r = await ipcRenderer.invoke("lm:snapshot", text);
    if (r && r.ok) status("Reading captions · +" + r.added + " lines", "#5fd49a");
    else status((r && r.error) || "Not sent", "#ff6b6b");
  }
});
