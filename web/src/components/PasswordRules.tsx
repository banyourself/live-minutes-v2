const SEQUENCES = ["abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm", "01234567890"];

function hasSequence(lowered: string) {
  for (const seq of SEQUENCES) {
    for (let i = 0; i + 5 <= seq.length; i++) {
      const chunk = seq.slice(i, i + 5);
      if (lowered.includes(chunk) || lowered.includes([...chunk].reverse().join(""))) return true;
    }
  }
  return false;
}

export function passwordChecks(pw: string, email = "", name = "") {
  const kinds = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length;
  const lowered = pw.toLowerCase();
  const parts = (email.split("@")[0] + " " + name).toLowerCase().split(/[^a-z0-9]+/).filter((p) => p.length >= 3);
  return [
    { ok: pw.length >= 12, label: "At least 12 characters" },
    { ok: kinds >= 3 || (pw.length >= 20 && kinds >= 2), label: "Three kinds of characters (a, A, 1, #), or a 20+ character passphrase" },
    { ok: pw.length > 0 && !/(.)\1\1\1/.test(pw) && !hasSequence(lowered), label: "No repeats like aaaa or runs like 12345" },
    { ok: pw.length > 0 && !parts.some((p) => lowered.includes(p)), label: "Does not contain your name or email" }
  ];
}

export function passwordOk(pw: string, email = "", name = "") {
  return passwordChecks(pw, email, name).every((c) => c.ok);
}

export default function PasswordRules({ password, email = "", name = "" }: { password: string; email?: string; name?: string }) {
  return (
    <ul className="pw-rules" aria-live="polite">
      {passwordChecks(password, email, name).map((c) => (
        <li key={c.label} className={c.ok ? "ok" : ""}>{c.ok ? "✓" : "·"} {c.label}</li>
      ))}
      <li className="note">We also block common passwords and ones found in known data breaches.</li>
    </ul>
  );
}
