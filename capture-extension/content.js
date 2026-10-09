(() => {
  if (window.top !== window && !document.querySelector("[class*=transcript],[class*=caption]")) return;
  if (window.__liveMinutes) return;
  window.__liveMinutes = true;

  let target = null, timer = null, lastSent = "", picking = false;

  const bar = document.createElement("div");
  bar.style.cssText = "position:fixed;z-index:2147483647;right:12px;bottom:12px;background:#1b2029;color:#e6e9ef;" +
    "font:12px system-ui,sans-serif;padding:8px 10px;border-radius:8px;box-shadow:0 2px 10px #0006;display:flex;gap:8px;align-items:center";
  bar.innerHTML = '<b>Live Minutes</b><span id="lm-st">off</span>' +
    '<button id="lm-pick" style="font:inherit">Pick captions area</button>' +
    '<button id="lm-stop" style="font:inherit;display:none">Stop</button>';
  document.documentElement.appendChild(bar);
  const st = bar.querySelector("#lm-st"), pickBtn = bar.querySelector("#lm-pick"), stopBtn = bar.querySelector("#lm-stop");
  const setStatus = (t, color) => { st.textContent = t; st.style.color = color || "#9aa3b2"; };

  let hovered = null;
  const outline = el => { if (hovered) hovered.style.outline = hovered.__lmOutline || ""; hovered = el;
    if (el) { el.__lmOutline = el.style.outline; el.style.outline = "2px solid #5b9bef"; } };
  const onMove = e => { if (picking && !bar.contains(e.target)) outline(e.target); };
  const onClick = e => {
    if (!picking || bar.contains(e.target)) return;
    e.preventDefault(); e.stopPropagation();
    picking = false; outline(null);
    document.removeEventListener("mousemove", onMove, true);
    document.removeEventListener("click", onClick, true);
    let el = e.target;
    while (el.parentElement && (el.innerText || "").length < 80 && el.parentElement !== document.body) el = el.parentElement;
    start(el);
  };

  pickBtn.onclick = () => {
    picking = true; setStatus("click the captions or transcript panel…", "#f0b35a");
    document.addEventListener("mousemove", onMove, true);
    document.addEventListener("click", onClick, true);
  };
  stopBtn.onclick = () => stop("stopped");

  function start(el) {
    target = el; lastSent = "";
    pickBtn.style.display = "none"; stopBtn.style.display = "";
    setStatus("reading…", "#5fcf93");
    const obs = new MutationObserver(() => schedule());
    obs.observe(el, { childList: true, subtree: true, characterData: true });
    target.__lmObs = obs;
    schedule();
  }

  function stop(msg) {
    if (target?.__lmObs) target.__lmObs.disconnect();
    target = null; clearTimeout(timer);
    pickBtn.style.display = ""; stopBtn.style.display = "none";
    setStatus(msg || "off");
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(send, 1500);
  }

  function send() {
    if (!target) return;
    if (!document.contains(target)) return stop("panel closed; pick it again");
    const text = target.innerText || "";
    if (!text.trim() || text === lastSent) return;
    lastSent = text;
    chrome.runtime.sendMessage({ type: "snapshot", text: text.slice(-60000) }, r => {
      if (chrome.runtime.lastError) return setStatus("extension reloaded; refresh the page", "#ff8a80");
      if (r?.ok) setStatus("reading · +" + r.added + " lines", "#5fcf93");
      else setStatus(r?.error || "not sent", "#ff8a80");
    });
  }
})();
