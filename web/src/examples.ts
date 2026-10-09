import { useSession } from "./session";

const SCHOOL = {
  meetingTitle: "ASG Weekly Meeting",
  uploadTitle: "ASG Regular Meeting",
  place: "Student Center 101",
  notes: "Room account voices: Kevin and the Vice President. Kevin is the new Secretary.",
  recordingLink: "https://college.zoom.us/rec/share/...",
  agendaItem: "New Business: Trunk or Treat funding",
  topic: "Add a topic, like Treasurer Report",
  search: "parking, Trunk or Treat, budget",
  question: "When did we approve the Trunk or Treat budget?",
  shared: "ASG Office: Kevin, the President\nRoom 101: Kevin, the Vice President",
  assistantAsk: "\"Make Kevin Vice President for 6 months\" or \"Schedule a general meeting next Tuesday at 2 p.m.\"",
  appAsk: "In Live Minutes, make Kevin Vice President for 6 months.",
  draftAsk: "Draft the minutes for my latest ASG meeting in Live Minutes."
};

const PERSONAL: typeof SCHOOL = {
  meetingTitle: "Weekly team check-in",
  uploadTitle: "Project kickoff",
  place: "Conference room B",
  notes: "The kitchen laptop is Kevin and a roommate. Kevin is taking notes.",
  recordingLink: "https://zoom.us/rec/share/...",
  agendaItem: "Decisions: Pick the launch date",
  topic: "Add a topic, like Budget check-in",
  search: "launch date, budget, vacation",
  question: "When did we decide on the launch date?",
  shared: "Kitchen laptop: Kevin, a roommate\nTeam room: Kevin, the project lead",
  assistantAsk: "\"Schedule a team check-in next Tuesday at 2 p.m.\" or \"How do I connect Zoom?\"",
  appAsk: "In Live Minutes, schedule a team check-in next Tuesday at 2 p.m.",
  draftAsk: "Draft the minutes for my latest meeting in Live Minutes."
};

export function useExamples() {
  const { me, org } = useSession();
  const personal = org ? !!org.personal : me?.user.account_type === "personal";
  return personal ? PERSONAL : SCHOOL;
}
