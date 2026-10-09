import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { TERMS_DATE } from "./legal-links";

const CONTACT = "kevin@kevinle.tech";

function Doc({ kicker, title, children }: { kicker: string; title: string; children: ReactNode }) {
  return (
    <article className="legal">
      <div className="page-head">
        <div>
          <div className="kicker">{kicker}</div>
          <h1>{title}</h1>
          <p className="sub">Effective {TERMS_DATE}</p>
        </div>
      </div>
      <div className="card stack legal-body">{children}</div>
      <nav className="row" aria-label="Policies" style={{ marginTop: 12 }}>
        <Link to="/privacy">Privacy policy</Link><Link to="/terms">Terms of use</Link><Link to="/accessibility">Accessibility</Link>
        <Link to="/support">Support</Link><Link to="/help/zoom">Zoom app</Link><Link to="/download">Downloads</Link>
      </nav>
    </article>
  );
}

export function Privacy() {
  return (
    <Doc kicker="Policies" title="Privacy policy">
      <p>Live Minutes helps student governments, clubs, and committees at colleges, and anyone with a personal workspace, turn meeting
        captions, transcripts, and chat into minutes. This policy explains what information Live Minutes collects, how it is used, and the
        choices you have. Live Minutes is operated by Kevin Le. If your college district runs its own copy of Live Minutes, the district's
        agreement and privacy notices also apply and control where they differ.</p>

      <h2>Information we collect</h2>
      <ul>
        <li><strong>Account details:</strong> your name, email address, password (stored only as a one-way hash), and whether you are a student, faculty, staff, IT, or personal use account.</li>
        <li><strong>Sign-in security:</strong> if you turn on two-step sign-in, your authenticator key (stored encrypted) and recovery codes (stored only as
          one-way hashes), and for each signed-in device, its browser and device description and when it was last used, so you can see and sign out devices.</li>
        <li><strong>AI connections:</strong> the AI provider and model you choose and the API key you add, stored encrypted and never shown in full again,
          and, if you connect an AI app such as Claude or ChatGPT to Live Minutes, the app's name and a sign-in token stored only as a one-way hash.</li>
        <li><strong>School details:</strong> the school or work email you confirm, your college, the organizations you belong to, and any officer position you hold.</li>
        <li><strong>Meeting records:</strong> recordings uploaded or imported from Zoom, captions, transcripts (including ones you add from other note-taking apps), chat, notes, drafts and approved minutes, motions and votes, funding requests, translations, and summaries that you or your organization add or create.</li>
        <li><strong>Zoom details, if you connect Zoom:</strong> the Zoom account's email address, user ID, and account ID, its recording settings, and the list of its cloud recordings. See the Zoom section below.</li>
        <li><strong>Activity and security records:</strong> sign-ins, failed sign-ins, the IP address used, and changes to settings and records. These protect accounts and show who changed what.</li>
      </ul>
      <p>We do not collect grades, financial aid, health information, student ID numbers, or Social Security numbers, and you should not enter them.</p>

      <h2>How we use it</h2>
      <p>To run the service: sign you in, show your organizations' meetings, draft and export minutes, send the emails you ask for and security alerts (for example when your password or two-step sign-in changes), keep
        accounts secure, and fix problems.
        We do not sell personal information, use it for advertising, or build profiles about you. We do not use your records to train AI models.</p>

      <h2>AI providers</h2>
      <p>When an organization asks for a draft, a translation, a summary, or an answer, or someone uses the assistant, the relevant meeting text is sent to the AI provider chosen inside Live Minutes
        by your district, college, organization, or you. That provider processes the text under its own terms. Districts and colleges can limit organizations to AI
        providers they approve. Every AI is told to treat meeting text as data only, and a person reviews all AI output before minutes are approved.
        Links to a provider's key or download page open that provider's own site, which has its own privacy policy.</p>
      <p>The free AI built into Live Minutes is different: it is an open model that runs on the Live Minutes server itself, so meeting text sent to it
        never leaves the server and is not sent to any AI company. It drafts minutes, summaries, and translations and answers the assistant and record questions. It is not used to train anything.
        While a request waits in line, its text is kept on the Live Minutes server; it is deleted as soon as the request finishes, and the
        answer is deleted after a day. Quick translation works the same way: it runs LibreTranslate, an open-source translator, on the Live Minutes
        server, so the minutes it translates never leave the server.</p>
      <p>You can also connect an AI app, such as Claude, ChatGPT, Gemini, Grok, Le Chat, or Perplexity, to Live Minutes under My account, AI. You sign in and approve it on a Live Minutes page.
        The app can then read the meetings you can see, and save drafts only if you allow it; it can never approve minutes. What the app reads is handled by
        that app's provider under its own terms. You can disconnect it at any time in the same place.</p>

      <h2>Zoom</h2>
      <p>If you connect a Zoom account, Live Minutes asks Zoom only for what it needs: the account's profile (to show which account is connected and
        to recognize it if you remove the app), its recording settings (to show the setup checklist), and its list of cloud recordings. When you choose
        a recording, Live Minutes copies its closed captions or transcript and its chat into that meeting, and its video or audio only if you ask for it. Live Minutes cannot
        join meetings, record, change Zoom settings, or read anyone else's account, and it does not sell Zoom data or use it for advertising or to train
        AI models. Text imported from Zoom is treated like any other meeting text: only the meeting's organization can see it, and it is sent to your
        chosen AI provider when you ask for a draft. Zoom's sign-in tokens are stored encrypted.</p>
      <p>You can stop this at any time by choosing Disconnect Zoom in Settings, or by removing Live Minutes in Zoom (App Marketplace, Manage, Added Apps).
        Either way the saved Zoom sign-in is deleted right away and nothing more is read from Zoom. Transcripts, chat, and recordings you already
        imported stay with the meeting until you delete the meeting or the workspace, or ask us to delete them. Your recordings in Zoom are never
        changed. Full steps are on the <Link to="/help/zoom">Zoom app page</Link>.</p>

      <h2>Who else handles information</h2>
      <p>Live Minutes uses a small number of service providers: Cloudflare (secure connection, bot checks, and the platform's nightly offsite
        backups, which are encrypted with a key Cloudflare never has), Resend (email), the AI provider or AI app you or your
        organization chooses, Zoom if you or your organization connects it, Microsoft or Google if you use school sign-in, and storage your district or college connects for backups.
        We may disclose information if required by law, after notifying the district when allowed. People in your organization, your college and district IT staff,
        and the platform operator can see records for the areas they manage.</p>

      <h2>Who can see meetings</h2>
      <p>Every meeting is private. Its recording, transcript, chat, drafts, and minutes are visible only to members of its organization and the college and
        district staff who manage it. A personal workspace belongs to no college or district, so only its members and the platform operator can see it.
        Nothing is public unless an organization's owner turns on its public archive. That page shows only the organization's name, its approved
        minutes with their plain-language summaries, and a Word file of each. Drafts, recordings, transcripts, chat, votes, and members are never
        public. Turning the archive off takes the page down right away.</p>

      <h2>Student records and public records</h2>
      <p>For colleges, Live Minutes acts as a school official under the Family Educational Rights and Privacy Act (FERPA) and uses education records only to provide this
        service. Minutes of student government and committee meetings are often public records under state open-meeting and public records laws, so approved minutes
        may be shared publicly by your organization.</p>

      <h2>How long we keep it</h2>
      <p>Records are kept until your organization deletes them or your district's retention rules remove them, except when a legal hold requires keeping them.
        A personal workspace's records are kept until you delete them or ask us to delete the workspace.
        When an account is deleted, its sign-in details are removed; minutes and records that belong to an organization stay with that organization.
        Sign-in sessions end after a period of inactivity, and old notifications are deleted after 180 days.</p>

      <h2>Cookies and local storage</h2>
      <p>Live Minutes uses only what it needs to work. It does not use advertising or analytics cookies, so there is nothing to opt out of.</p>
      <table>
        <thead><tr><th scope="col">Name</th><th scope="col">Purpose</th><th scope="col">Lasts</th></tr></thead>
        <tbody>
          <tr><td className="mono">__Host-lm_session</td><td>Keeps you signed in.</td><td>Until you sign out, 12 idle hours, or 14 days</td></tr>
          <tr><td className="mono">__Secure-lm_sso</td><td>Protects a school sign-in while it is in progress.</td><td>10 minutes</td></tr>
          <tr><td className="mono">__Secure-lm_2fa</td><td>Holds a sign-in between your password and your two-step code.</td><td>5 minutes</td></tr>
          <tr><td className="mono">__Secure-lm_zoom</td><td>Protects connecting a Zoom account while it is in progress.</td><td>10 minutes</td></tr>
          <tr><td className="mono">__Secure-lm_openrouter</td><td>Protects signing in with OpenRouter to add an AI while it is in progress.</td><td>10 minutes</td></tr>
          <tr><td className="mono">__Secure-lm_zoom_pending</td><td>Holds a Zoom connection you started from Zoom's App Marketplace until you choose a workspace.</td><td>15 minutes</td></tr>
          <tr><td>Cloudflare security cookies</td><td>Set by Cloudflare only if a bot check or security challenge is needed.</td><td>Short term</td></tr>
          <tr><td className="mono">lm.prefs, lm.org</td><td>Stored in your browser, not sent to us: your display choices and the organization you last opened.</td><td>Until you clear them</td></tr>
        </tbody>
      </table>
      <p>Your browser's "Do Not Track" signal does not change anything here because Live Minutes does not track you across other sites.</p>
      <p>Live Minutes does not sell or share personal information, including for targeted advertising, and it has no session replay: nothing
        records your clicks, mouse movements, or keystrokes. If your browser sends a Global Privacy Control signal, we treat it as a request not
        to sell or share your information, which we already never do. Fonts, images, and scripts come from Live Minutes itself, not from Google
        or any font, analytics, or ad network. The only outside code a page loads is Cloudflare's bot check on the sign-in and sign-up forms.</p>

      <h2>Security</h2>
      <p>Connections are encrypted, stored keys and tokens are encrypted or hashed, access is limited by role, and changes are logged. You can turn on two-step
        sign-in with an authenticator app, see where your account is signed in, and sign out any device under My account, Security. No system is perfectly secure;
        if we learn of a breach affecting your information, we will notify your district and you as required by law.</p>

      <h2>Your choices and rights</h2>
      <ul>
        <li>See and update your name, password, account type, notification emails, and calendar link under My account.</li>
        <li>Turn two-step sign-in on or off, make new recovery codes, and sign out any device under My account, Security, and disconnect AI apps under My account, AI.</li>
        <li>Ask your organization's owner to correct or remove meeting records, or ask your college or district, which controls official records.</li>
        <li>Ask us at <a href={"mailto:" + CONTACT}>{CONTACT}</a> for a copy of your personal information, to correct it, or to delete your account. Students may also use their FERPA rights through their college.</li>
      </ul>

      <h2>Children</h2>
      <p>Live Minutes is for college students, faculty, and staff, and for people who use a personal workspace. It is not meant for children under 13, and we do not knowingly collect their information.
        If you believe a child under 13 has an account, contact us and we will delete it.</p>

      <h2>Changes</h2>
      <p>We will post changes here with a new effective date, and ask you to review important changes the next time you sign in.</p>

      <h2>Contact</h2>
      <p>Questions or requests: <a href={"mailto:" + CONTACT}>{CONTACT}</a>.</p>
    </Doc>
  );
}

export function Terms() {
  return (
    <Doc kicker="Policies" title="Terms of use">
      <p>These terms cover your use of Live Minutes. By creating an account or using Live Minutes, you agree to them and to the <Link to="/privacy">Privacy policy</Link>.
        If your college district has its own agreement for Live Minutes, that agreement controls where it differs.</p>

      <h2>Who may use Live Minutes</h2>
      <p>Live Minutes has two kinds of accounts. School accounts are for students, faculty, staff, and IT staff of participating colleges and
        districts, and people they invite. Personal accounts are for anyone who wants a private workspace for their own meetings, with no
        school or organization involved. You must be at least 13, and if you are under 18, please read these terms with a parent or
        guardian. A personal workspace can keep a limited amount of recordings (2 GB unless
        we post a different limit), and we may suspend personal accounts that are used for spam, abuse, or anything that breaks these terms.
        Use your own account, give accurate information, keep your password, authenticator app, and recovery codes private, and tell us right away if you think someone else used your account.</p>

      <h2>Follow your school's rules</h2>
      <p>Your college's student code of conduct, employee policies, and computer and network acceptable use policies apply to everything you do in Live Minutes,
        as do your organization's bylaws. Live Minutes does not replace them.</p>

      <h2>Recording and captions</h2>
      <ul>
        <li>Tell everyone in a meeting that captions, transcripts, or chat are being captured for minutes, at the start of the meeting and in the agenda when you can.</li>
        <li>Do not capture closed sessions, confidential discussions, private conversations, or anyone who has not been told, and follow California and other laws that require consent to record.</li>
        <li>Capture only meetings you host or are allowed to take minutes for.</li>
        <li>When you create a meeting or upload a recording, you confirm that everyone in it has been or will be told. Live Minutes keeps a
          record of that confirmation.</li>
      </ul>

      <h2>Acceptable use</h2>
      <p>Do not use Live Minutes to harass or threaten anyone, post discriminatory or unlawful content, share other people's private information, enter information
        Live Minutes is not designed for (such as student ID numbers, grades, or health information), try to get into accounts or areas you are not allowed to see,
        test or disrupt the service's security without written permission, or use it for commercial purposes unrelated to your organization.
        Report security problems to <a href={"mailto:" + CONTACT}>{CONTACT}</a>.</p>

      <h2>AI drafts and official minutes</h2>
      <p>AI drafts can be wrong or incomplete. A person must review every draft, and minutes become official only when your organization approves them under its bylaws.
        You are responsible for what your organization approves and publishes. Approved minutes may be public records.</p>
      <p>The free AI is offered as is, at no cost. It is slower than paid AI services, drafts wait in line with everyone else's, and it may be paused
        or limited to keep the service running. Meetings longer than about two hours need another AI.</p>

      <h2>Your content</h2>
      <p>If your organization turns on its public archive, you confirm it is allowed to publish those approved minutes, as open-meeting laws
        often require of student governments.</p>
      <p>Your organization, college, or district owns the records it creates in Live Minutes, and you own the records in your personal workspace. You give
        Live Minutes permission to store, process, and display those records only to provide the service, including sending text to the AI provider
        you or your organization chooses.</p>

      <h2>Copyright</h2>
      <p>Upload only recordings, transcripts, templates, and files that you made or have permission to use. Live Minutes has no profile
        pictures, image galleries, or public comments. The only public pages are approved minutes that an organization chooses to publish.</p>
      <p>If you believe something on Live Minutes infringes your copyright, email <a href={"mailto:" + CONTACT}>{CONTACT}</a> with: your name
        and contact details; the work you believe is infringed; where it appears on Live Minutes, such as a link; a statement that you believe
        in good faith the use is not authorized by the owner, its agent, or the law; a statement that the notice is accurate and, under penalty
        of perjury, that you are the owner or allowed to act for the owner; and your physical or electronic signature. We will remove or disable
        the material and tell the person who added it, who may send a counter-notice to the same address. We end the access of people who
        repeatedly infringe.</p>

      <h2>Third-party services</h2>
      <p>Connected services such as Zoom, school sign-in, AI providers, and backup storage have their own terms. You are responsible for following them when you connect them.
        Connect only a Zoom account you control or are allowed to connect. If the account belongs to a school or employer, follow its rules; its Zoom admin
        may need to approve Live Minutes first. AI providers bill the owner of each API key for its use. Live Minutes shows estimated usage, but you are
        responsible for your provider's charges and limits.</p>

      <h2>Suspension and ending</h2>
      <p>Organization owners, college IT, district IT, or the operator may remove access that breaks these terms or school policy. You may stop using Live Minutes at any time
        and ask us to delete your account.</p>

      <h2>The service</h2>
      <p>Live Minutes is provided as is, and during the pilot it may change, pause, or have errors. Keep your own copy of anything you must keep, such as approved minutes.
        To the extent the law allows, the operator is not liable for indirect or consequential losses, and total liability is limited to the amount you paid to use
        Live Minutes, if any. Nothing here limits rights you have under law that cannot be waived.</p>

      <h2>Changes and law</h2>
      <p>We may update these terms and will post the new version here with a new effective date. We will ask you to accept important changes. California law governs these terms.</p>

      <h2>Contact</h2>
      <p><a href={"mailto:" + CONTACT}>{CONTACT}</a></p>
    </Doc>
  );
}

export function Support() {
  return (
    <Doc kicker="Help" title="Support">
      <p>Live Minutes is run by Kevin Le. For help with your account, a meeting, the Zoom app, or anything else, email{" "}
        <a href={"mailto:" + CONTACT}>{CONTACT}</a>.</p>
      <h2>When you will hear back</h2>
      <p>Support is answered Monday to Friday, 9 a.m. to 5 p.m. Pacific time, except holidays. You will get a reply within 2 business days, and
        usually sooner. Urgent problems, such as a meeting that will not save during a live session, are answered first.</p>
      <h2>What to include</h2>
      <ul>
        <li>The email address you sign in with and the name of your workspace or organization.</li>
        <li>What you were doing, what you expected, and what happened instead, including any error message.</li>
        <li>For the Zoom app, the email address of the Zoom account you connected.</li>
      </ul>
      <p>Never send your password, your Zoom password, or an AI key. Live Minutes staff will never ask for them.</p>
      <h2>Common questions</h2>
      <ul>
        <li><strong>Connecting or removing Zoom:</strong> see the <Link to="/help/zoom">Zoom app page</Link>.</li>
        <li><strong>Deleting your data:</strong> delete meetings in the app, or email us to delete your account or workspace.</li>
        <li><strong>Lost the phone with your authenticator app:</strong> sign in with one of your recovery codes, then set up two-step sign-in again under
          My account, Security. Without a recovery code, email us from your account's email address; once we confirm who you are, we can turn it off.</li>
        <li><strong>An AI test fails:</strong> choose Edit on that AI under Settings, AI or My account, AI, check its model name and key, then choose Test.
          The Get a key button opens the provider's key page.</li>
        <li><strong>Accessibility:</strong> see the <Link to="/accessibility">accessibility statement</Link>.</li>
        <li><strong>Security problems:</strong> email {CONTACT}; please do not test the live service without written permission.</li>
      </ul>
    </Doc>
  );
}

export function ZoomHelp() {
  return (
    <Doc kicker="Help" title="Using Live Minutes with Zoom">
      <p>The Live Minutes app for Zoom imports your Zoom cloud recordings' transcripts and chat into Live Minutes, where AI drafts the minutes for a
        person to review. It only reads. It cannot join, record, or change anything in your Zoom account.</p>

      <h2>Before you start</h2>
      <ul>
        <li>You need a Live Minutes account, in an organization approved by your college or district or in your own personal workspace, and
          the Runs meetings role or higher in that workspace.</li>
        <li>Your Zoom account needs cloud recording, which Zoom includes in Pro and higher plans and most school accounts.</li>
        <li>In Zoom's settings, under Recording, turn on Cloud recording, Create audio transcript, and Save chat messages. Turning on Save
          closed captions as a VTT file too lets Live Minutes use the meeting's live captions, which are often the most accurate text.
          After you connect, Settings, Zoom in Live Minutes shows a checklist of these settings.</li>
        <li>If your Zoom account belongs to a school or company, its Zoom admin may need to approve Live Minutes before you can add it.</li>
      </ul>

      <h2>Add the app</h2>
      <p>From Live Minutes: open Settings, then Zoom, and choose Connect Zoom. Sign in to the Zoom account that hosts your meetings, review what
        Live Minutes may read, and choose Allow. You return to Live Minutes, connected.</p>
      <p>From the Zoom App Marketplace: the Live Minutes listing brings you to this page, or straight to Zoom's approval screen. If you choose Allow
        there first, sign in to Live Minutes if asked, then choose the workspace whose meetings this Zoom account hosts.</p>

      <h2>Use it</h2>
      <ul>
        <li>Open a meeting, choose Import, then Zoom recording, and pick a recording from the last 30 days. Its closed captions, or its audio
          transcript when there are no captions covering the meeting, and its chat are added to the meeting; add the video or audio too if you
          want it.</li>
        <li>If several people speak from one Zoom account, such as a club's shared account or a room, list it under Settings, General, Shared
          accounts. The AI tells them apart from context, such as "This is Kevin" before someone speaks, and marks anything it cannot tell.</li>
        <li>Or paste a Zoom recording share link when you upload a meeting, and Live Minutes finds the matching recording in your account.</li>
        <li>Or turn on Import new cloud recordings automatically under Settings, Zoom. When the connected account finishes a cloud recording, Live
          Minutes makes a meeting for it, imports its closed captions or transcript and chat, starts the draft if an AI is set up, and tells the
          people who run meetings.</li>
        <li>Then draft, review, and approve the minutes as usual.</li>
      </ul>

      <h2>What Live Minutes may read</h2>
      <table>
        <thead><tr><th scope="col">Permission</th><th scope="col">Why</th></tr></thead>
        <tbody>
          <tr><td className="mono">user:read:user</td><td>Shows which Zoom account is connected, and recognizes it if you remove the app.</td></tr>
          <tr><td className="mono">user:read:settings</td><td>Checks that cloud recording, transcripts, and saved chat are turned on.</td></tr>
          <tr><td className="mono">cloud_recording:read:list_user_recordings</td><td>Lists your cloud recordings so you can choose one.</td></tr>
          <tr><td className="mono">cloud_recording:read:list_recording_files</td><td>Reads the closed captions, transcript, chat, and media files of a recording you choose.</td></tr>
        </tbody>
      </table>

      <h2>Remove the app</h2>
      <ul>
        <li>In Live Minutes: open Settings, then Zoom, and choose Disconnect Zoom.</li>
        <li>In Zoom: sign in at marketplace.zoom.us, open Manage, then Added Apps, find Live Minutes, and choose Remove.</li>
      </ul>
      <p>Either way, Live Minutes deletes the saved Zoom sign-in right away, and nothing more is read from your Zoom account. You can add the app
        again later by connecting from Settings.</p>

      <h2>What happens to your data</h2>
      <ul>
        <li>Transcripts, chat, and recordings you imported stay in the meeting they were added to, so your minutes keep their source, until you
          delete the meeting or the workspace.</li>
        <li>To have everything deleted, delete those meetings, or email <a href={"mailto:" + CONTACT}>{CONTACT}</a> to delete your workspace or account.</li>
        <li>Your recordings in Zoom are never changed or deleted by Live Minutes.</li>
      </ul>
      <p>More detail is in the <Link to="/privacy">Privacy policy</Link>. Questions: <Link to="/support">Support</Link>.</p>
    </Doc>
  );
}

export function Accessibility() {
  return (
    <Doc kicker="Policies" title="Accessibility">
      <p>Live Minutes aims to meet the Web Content Accessibility Guidelines (WCAG) 2.1 at Level AA, the standard public colleges must meet under Title II of the
        Americans with Disabilities Act and Section 508.</p>
      <h2>What Live Minutes does</h2>
      <ul>
        <li>Works with a keyboard and screen readers, with a skip link, headings, labeled fields, and status messages that are announced.</li>
        <li>Meets 4.5 to 1 text contrast in the built-in color schemes, and offers light schemes and a high-contrast setting under Customize.</li>
        <li>Respects your device's reduced motion setting, and lets you turn animations off.</li>
        <li>Warns you before signing you out for inactivity so you can stay signed in.</li>
        <li>Shows the two-step sign-in setup key as text beside its QR code, so it can be entered by hand, and accepts pasted codes.</li>
        <li>Plays recordings beside a transcript that follows along and jumps to any line, with caption and subtitle downloads.</li>
        <li>Gives every Word file a title and language, and checks it for headings, image descriptions, table headers, spacing, text size, contrast, and link text.</li>
        <li>Offers plain-language summaries and translations of minutes.</li>
      </ul>
      <h2>Known limits</h2>
      <p>Live Minutes has not yet had an outside accessibility audit. The accessibility of Word files also depends on each organization's template.</p>
      <h2>Report a barrier or ask for another format</h2>
      <p>Email <a href={"mailto:" + CONTACT}>{CONTACT}</a> with the page and what happened. We will reply within 5 business days and can provide minutes or other
        content in another format. You can also contact your college's disability services office.</p>
    </Doc>
  );
}
