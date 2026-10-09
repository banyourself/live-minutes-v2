function zoomWebUrl(input) {
  const raw = String(input || "").trim();
  const m = raw.match(/(?:\/j\/|\/wc\/join\/|\/wc\/)(\d{9,12})/) || raw.replace(/\s/g, "").match(/^(\d{9,12})$/);
  if (!m) return "";
  let pwd = "";
  try {
    pwd = new URL(raw).searchParams.get("pwd") || "";
  } catch {
    pwd = "";
  }
  return "https://app.zoom.us/wc/join/" + m[1] + (pwd ? "?pwd=" + encodeURIComponent(pwd) : "");
}

module.exports = { zoomWebUrl };
