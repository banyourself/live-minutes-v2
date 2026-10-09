import { Link } from "react-router-dom";
import { api } from "../api";
import { useLoad } from "../ui";

interface FileRow { name: string; size: number; sha256: string }

const mb = (n: number) => (n / 1048576).toFixed(n > 10485760 ? 0 : 1) + " MB";

function FileLink({ file }: { file?: FileRow }) {
  if (!file) return <p className="sub">Not available yet.</p>;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row">
        <a className="btn primary" href={"/api/downloads/" + encodeURIComponent(file.name)} download>Download {file.name}</a>
        <span className="sub">{mb(file.size)}</span>
      </div>
      <span className="sub">SHA-256: <span className="mono" style={{ wordBreak: "break-all" }}>{file.sha256}</span></span>
    </div>
  );
}

export default function Download() {
  const list = useLoad(() => api.get<{ files: FileRow[] }>("/api/downloads"), []);
  const files = list.data?.files || [];
  const desktop = files.filter((f) => f.name.endsWith(".exe")).pop();
  const extension = files.filter((f) => f.name.endsWith(".zip")).pop();
  return (
    <article className="legal">
      <div className="page-head">
        <div>
          <div className="kicker">Help</div>
          <h1>Downloads</h1>
          <p className="sub">Read live captions from Zoom so minutes draft during the meeting. You only need one of these.</p>
        </div>
      </div>
      <div className="card stack legal-body">
        <h2>Live Minutes for Windows</h2>
        <p>Your meetings and minutes in their own window, plus Live capture: join Zoom inside the app with captions on, and it sends
          the captions to the Live Minutes meeting you choose. A small floating bar stays on top of Zoom with the time, the lines
          sent, and a button to open the draft. It connects to minutes.kevinle.tech on its own, and a short tour walks you through it.</p>
        <FileLink file={desktop} />
        <p className="sub">The installer is not code-signed yet, so Windows may say "Windows protected your PC". Check that the
          SHA-256 above matches, then choose More info, Run anyway.</p>

        <h2>Caption Reader for Chrome and Edge</h2>
        <p>A browser extension for joining Zoom in the browser with "Join from your browser". It reads the captions you can already
          see and sends them to your Live Minutes meeting. It works with minutes.kevinle.tech.</p>
        <p className="sub">It is on its way to the Microsoft Edge Add-ons store. Until then, install it by hand:</p>
        <FileLink file={extension} />
        <ol>
          <li>Unzip the file into a folder you will keep.</li>
          <li>Open <span className="mono">edge://extensions</span> or <span className="mono">chrome://extensions</span> and turn on Developer mode.</li>
          <li>Choose Load unpacked and pick the unzipped folder.</li>
          <li>In Live Minutes, make a capture token under Settings, Capture devices, and paste it into the extension's options.</li>
        </ol>

        <h2>Before a meeting</h2>
        <ul>
          <li>Start the meeting in Live Minutes first, then pick it in the app or extension.</li>
          <li>Turn on captions in Zoom. Tell everyone that captions are captured for minutes.</li>
        </ul>
        {list.error && <p className="sub">Could not load the file list: {list.error}</p>}
        <p className="sub">Questions: <Link to="/support">Support</Link>.</p>
      </div>
    </article>
  );
}
