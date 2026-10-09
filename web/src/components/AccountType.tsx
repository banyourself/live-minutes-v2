export type AccountType = "student" | "faculty" | "staff" | "it" | "personal";

export const TYPES: { id: AccountType; label: string; hint: string }[] = [
  { id: "student", label: "Student", hint: "Members and officers of student organizations" },
  { id: "faculty", label: "Faculty", hint: "Instructors and club advisors" },
  { id: "staff", label: "Staff", hint: "College or district employees, such as student life staff" },
  { id: "it", label: "IT", hint: "College or district technology staff who manage access" },
  { id: "personal", label: "Personal use", hint: "Your own meetings in a private workspace, with no school or organization needed" }
];

export const typeLabel = (t: string) => TYPES.find((x) => x.id === t)?.label || "Not set";

export function emailWord(t: string) {
  return t === "student" ? "student" : "work";
}

export function expectedDomains(domains: string[], staff: string[], t: string) {
  if (t && t !== "student") return staff;
  const studentOnly = domains.filter((d) => !staff.includes(d));
  return studentOnly.length ? studentOnly : domains;
}

export default function AccountTypePicker({ value, onChange, personal = false }: { value: string; onChange: (t: AccountType) => void; personal?: boolean }) {
  return (
    <div className="type-grid" role="radiogroup" aria-label="Account type">
      {TYPES.filter((t) => personal || t.id !== "personal").map((t) => (
        <button key={t.id} type="button" role="radio" aria-checked={value === t.id}
          className={"type-card" + (value === t.id ? " on" : "")} onClick={() => onChange(t.id)}>
          <strong>{t.label}</strong>
          <span>{t.hint}</span>
        </button>
      ))}
    </div>
  );
}
