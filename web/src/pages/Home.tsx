import { Link } from "react-router-dom";
import Customize from "../components/Customize";
import { useSession } from "../session";
import { LegalLinks } from "./legal-links";

const AUDIENCES = [
  ["Student governments and clubs", "Secretaries get a draft with every motion, mover, seconder, and vote count, in the template the organization already uses."],
  ["Colleges and districts", "IT staff approve organizations, set how long records are kept, and see what each club has on file."],
  ["Your own meetings", "Anyone can open a private personal workspace for a team, a side project, or a group outside school."]
];

const STEPS = [
  ["Connect Zoom", "Add the Live Minutes app from Settings. It can only read your cloud recordings. It cannot join, record, or change anything in Zoom."],
  ["Record to the cloud", "Turn on audio transcripts and saved chat. Live Minutes imports the closed captions or transcript and the chat, when you choose a recording or automatically when one finishes."],
  ["Get a draft", "The AI writes the minutes in your template, one condensed bullet per topic, and marks anything it is unsure of with [verify]."],
  ["Review and approve", "Fix what needs fixing, confirm the motions, approve, then download the Word file or post it to your public archive."]
];

const FEATURES = [
  ["Live drafting", "The Caption Reader extension sends Zoom's captions during the meeting, so the draft fills in as people talk."],
  ["Motion and vote tracker", "Motions are detected from the transcript and chat votes, then confirmed by a person before approval."],
  ["Your format", "Start from a built-in template or match your own, down to the headings and the Word file."],
  ["Unfinished business", "Tabled motions from earlier meetings are offered on the next agenda, so nothing is forgotten."],
  ["Plain-language summaries", "Give members who missed the meeting a short summary, with translations into other languages."],
  ["Search every record", "Find any motion, vote, or decision across past meetings in seconds."]
];

export default function Home() {
  const { me } = useSession();
  return (
    <div className="home">
      <header className="home-top">
        <Link className="brand" to="/"><img src="/favicon.svg" alt="" width={30} height={30} />Live Minutes</Link>
        <nav className="row" aria-label="Account">
          <Customize />
          {me ? <Link className="btn primary" to="/dashboard">Open dashboard</Link> : (
            <>
              <Link className="btn" to="/login">Sign in</Link>
              <Link className="btn primary" to="/login?mode=signup">Create an account</Link>
            </>
          )}
        </nav>
      </header>

      <main id="main" tabIndex={-1}>
        <section className="home-hero">
          <div>
            <div className="kicker">Records office</div>
            <h1>Meeting minutes, drafted from the meeting itself</h1>
            <p className="home-lead">Live Minutes turns Zoom captions, transcripts, and chat into minutes in your organization's own format. It tracks
              motions and votes, and a person reviews and approves every draft.</p>
            <div className="row">
              {me ? <Link className="btn primary" to="/dashboard">Open your dashboard</Link>
                : <Link className="btn primary" to="/login?mode=signup">Create a free account</Link>}
              <Link className="btn" to="/help/zoom">How the Zoom app works</Link>
            </div>
            <p className="sub">Free to use, with a built-in AI that needs no key or account. It is slower, so bring your own AI if you want drafts in minutes.</p>
          </div>
          <figure className="home-shot">
            <img src="/home/welcome-tour.webp" width={1200} height={780} alt="The Live Minutes welcome tour: live captions from a sample meeting turning into draft minutes, with a carried motion and the floating capture bar, and no real names" />
          </figure>
        </section>

        <section aria-labelledby="who">
          <h2 id="who">Who it is for</h2>
          <div className="home-grid">
            {AUDIENCES.map(([title, text]) => (
              <div key={title} className="card"><h3>{title}</h3><p>{text}</p></div>
            ))}
          </div>
        </section>

        <section aria-labelledby="zoom">
          <h2 id="zoom">How Zoom import works</h2>
          <div className="home-split">
            <ol className="home-steps">
              {STEPS.map(([title, text]) => (
                <li key={title}><strong>{title}</strong><span>{text}</span></li>
              ))}
            </ol>
            <figure className="home-shot">
              <img src="/home/zoom-import.webp" width={1200} height={780} loading="lazy" decoding="async"
                alt="Importing a Zoom cloud recording in Live Minutes, with the recording's captions, transcript, and chat files listed" />
            </figure>
          </div>
          <p className="sub">No Zoom cloud recording? Upload a transcript or chat file, or use the Caption Reader during a live meeting.</p>
        </section>

        <section aria-labelledby="features">
          <h2 id="features">What else it does</h2>
          <div className="home-grid">
            {FEATURES.map(([title, text]) => (
              <div key={title} className="card"><h3>{title}</h3><p>{text}</p></div>
            ))}
          </div>
          <figure className="home-shot home-wide">
            <img src="/home/motions.webp" width={1200} height={780} loading="lazy" decoding="async"
              alt="The votes tab in Live Minutes, listing detected motions with who moved and seconded them, from a sample meeting with no real names" />
          </figure>
        </section>

        <section aria-labelledby="ai">
          <h2 id="ai">Your AI, your choice</h2>
          <p>Every account can use the free AI built into Live Minutes. It runs on our own server, so your meeting never goes to an AI company, and
            it drafts an hour-long meeting in about 15 to 40 minutes after the meeting ends. For faster drafts and live updates during the meeting,
            use Anthropic (Claude), OpenAI, Google Gemini, or Azure OpenAI with your own key, or a free model through OpenRouter or Hugging Face.
            Each organization picks its own, and keys are stored encrypted.</p>
          <p>Already pay for Claude, ChatGPT, Gemini, Grok, or Perplexity, or use Le Chat for free? Connect it to Live Minutes and it drafts
            your minutes inside the plan you already have, at no extra cost.</p>
        </section>

        <section aria-labelledby="private">
          <h2 id="private">Private by default</h2>
          <ul className="home-list">
            <li>Meetings, recordings, transcripts, and drafts are visible only to your organization's members, and for school organizations, the college
              staff who manage it. A personal workspace is visible only to you.</li>
            <li>Nothing is public unless an owner turns on the public archive, which shows approved minutes only.</li>
            <li>No ads, no trackers, and no selling data. Two-step sign-in is available for every account.</li>
          </ul>
          <p><Link to="/privacy">Read the privacy policy</Link></p>
        </section>

        <section className="home-cta card">
          <h2>Ready for your next meeting?</h2>
          <p>Create an account in a minute. Pick Personal for your own meetings, or School to join your organization.</p>
          <div className="row">
            {me ? <Link className="btn primary" to="/dashboard">Open your dashboard</Link> : (
              <>
                <Link className="btn primary" to="/login?mode=signup">Create a free account</Link>
                <Link className="btn" to="/login">Sign in</Link>
              </>
            )}
          </div>
        </section>
      </main>

      <footer className="home-foot sub">
        <LegalLinks />
        <span>Built by <a href="https://kevinle.tech/" target="_blank" rel="noreferrer">Kevin Le</a></span>
      </footer>
    </div>
  );
}
