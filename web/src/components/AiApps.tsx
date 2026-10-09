import { useState } from "react";
import { useExamples } from "../examples";
import { api } from "../api";
import { ErrorBox, errText, fmtDate, useLoad } from "../ui";

interface Token { id: string; name: string; can_write: boolean; created_at: number; expires_at: number; last_used_at: number | null; connected: boolean }

export default function AiApps() {
  const ex = useExamples();
  const data = useLoad(() => api.get<{ tokens: Token[]; mcp_url: string }>("/api/me/tokens"), []);
  const [name, setName] = useState("My AI app");
  const [write, setWrite] = useState(true);
  const [password, setPassword] = useState("");
  const [made, setMade] = useState("");
  const [error, setError] = useState("");
  const url = data.data?.mcp_url || location.origin + "/mcp";

  async function create() {
    setError(""); setMade("");
    try {
      await api.post("/api/auth/sudo", { password });
      const r = await api.post<{ token: string }>("/api/me/tokens", { name, can_write: write });
      setMade(r.token); setPassword("");
      await data.reload();
    } catch (e) {
      setError(errText(e));
    }
  }

  async function remove(t: Token) {
    if (!confirm((t.connected ? "Disconnect " : "Remove the token for ") + t.name + "? That app stops working with Live Minutes.")) return;
    try { await api.del("/api/me/tokens/" + t.id); await data.reload(); } catch (e) { setError(errText(e)); }
  }

  const desktop = JSON.stringify({ mcpServers: { "live-minutes": { command: "npx", args: ["-y", "mcp-remote", url, "--header", "Authorization:${LM_TOKEN}"],
    env: { LM_TOKEN: "Bearer " + (made || "YOUR_TOKEN") } } } }, null, 2);
  const tokens = data.data?.tokens || [];
  return (
    <div className="stack" id="ai-apps">
      <p className="sub" style={{ margin: 0 }}>Already have an AI plan? Connect Claude, ChatGPT, Gemini, Grok, Le Chat, or Perplexity to Live
        Minutes, then ask it, for example, "{ex.draftAsk}" It works inside the plan you already
        pay for (Le Chat's free plan works too), so Live Minutes costs nothing extra. It saves the draft here for you to review and approve,
        and can only see what you can see. You sign in and approve it on a Live Minutes page; no key or token is needed.</p>
      <div className="lbl">Live Minutes server address</div>
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <div className="token-box mono" style={{ flex: 1 }}>{url}</div>
        <button onClick={() => void navigator.clipboard.writeText(url)}>Copy</button>
      </div>
      {tokens.length > 0 && (
        <table>
          <thead><tr><th scope="col">App</th><th scope="col">Can</th><th scope="col">Last used</th><th scope="col">Expires</th><th /></tr></thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.id}>
                <td>{t.name}<div className="sub">{t.connected ? "Connected by signing in" : "Token"}</div></td>
                <td>{t.can_write ? "Read and save drafts" : "Read only"}</td>
                <td className="sub">{fmtDate(t.last_used_at) || "never"}</td><td className="sub">{fmtDate(t.expires_at)}</td>
                <td><button className="danger" onClick={() => void remove(t)}>{t.connected ? "Disconnect" : "Remove"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <details open>
        <summary>Claude (website, desktop app, and phone)</summary>
        <p className="sub">In Claude, open Settings, Connectors, and choose Add custom connector. Name it Live Minutes, paste the address above,
          and choose Add. Then choose Connect and approve it on the Live Minutes page that opens. On Team and Enterprise plans an owner adds the
          connector first under Organization settings, Connectors.</p>
      </details>
      <details>
        <summary>ChatGPT</summary>
        <p className="sub">In ChatGPT, open Settings, Apps and Connectors, Advanced settings, and turn on Developer mode. Then choose Create, paste
          the address above, pick OAuth for authentication, and approve it on the Live Minutes page that opens. Business and Enterprise
          workspaces may need an admin to allow custom connectors.</p>
      </details>
      <details>
        <summary>Gemini (Google AI Pro or Ultra)</summary>
        <p className="sub">Gemini connects custom apps through Spark, which needs a Google AI Pro or Ultra plan on a personal Google account
          (age 18 or over) with Keep activity turned on. On a computer, open gemini.google.com, then Settings and help, Connected apps. Under
          Custom apps for Spark, choose Add a custom app, paste the address above, choose Next, and approve it on the Live Minutes page that
          opens. Then ask Spark to draft your minutes.</p>
      </details>
      <details>
        <summary>Grok (paid plans)</summary>
        <p className="sub">On grok.com, open Connectors and add a custom connector. Paste the address above and sign in when Grok asks, then
          approve it on the Live Minutes page that opens.</p>
      </details>
      <details>
        <summary>Le Chat by Mistral (free plan works)</summary>
        <p className="sub">In Le Chat, open Intelligence, Connectors, and the Custom MCP Connector tab. Name it Live Minutes, paste the address
          above, and approve it on the Live Minutes page that opens. This works on Le Chat's free plan, which has a daily message limit.</p>
      </details>
      <details>
        <summary>Perplexity (Pro or Max)</summary>
        <p className="sub">On the perplexity.ai website (the phone app may not offer custom connectors), open Settings, Connectors, and choose
          Custom connector, Remote. Paste the address above, choose OAuth, and approve it on the Live Minutes page that opens.</p>
      </details>
      <p className="sub">These apps move their menus often; if a step looks different, look for Connectors or Custom app. Microsoft Copilot's
        free app cannot connect custom apps yet.</p>
      <details>
        <summary>Claude Code</summary>
        <pre className="prewrap">{"claude mcp add --transport http live-minutes " + url}</pre>
        <p className="sub">Then type <span className="mono">/mcp</span> in Claude Code, pick live-minutes, and sign in.</p>
      </details>
      <details>
        <summary>Apps that need a token</summary>
        <div className="stack">
          <p className="sub" style={{ margin: 0 }}>For apps that cannot sign in, make a personal token. Send it as the header
            <span className="mono"> Authorization: Bearer YOUR_TOKEN</span>.</p>
          <div className="grid-2">
            <label>App name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
            <label>Your password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
          </div>
          <label className="setting-row">
            <span>Let this app save minute drafts (it can never approve them)</span>
            <input type="checkbox" checked={write} onChange={(e) => setWrite(e.target.checked)} />
          </label>
          <div className="row"><button className="primary" disabled={!name.trim() || !password} onClick={() => void create()}>Make a token</button></div>
          {made && (
            <div className="stack">
              <p className="sub" style={{ margin: 0 }}>Copy it now. It is shown only once and works for 90 days.</p>
              <div className="token-box mono">{made}</div>
              <div className="row"><button onClick={() => void navigator.clipboard.writeText(made)}>Copy token</button></div>
            </div>
          )}
          <p className="sub" style={{ margin: 0 }}>Example for an older Claude Desktop setup (needs Node.js), in <span className="mono">claude_desktop_config.json</span>:</p>
          <pre className="prewrap">{desktop}</pre>
        </div>
      </details>
      <ErrorBox error={error || data.error} />
    </div>
  );
}
