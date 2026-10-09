import { waitForRun, type FreeRun } from "./freeai";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(method: string, path: string, body?: unknown, freeRun = ""): Promise<T> {
  const isForm = body instanceof FormData;
  const res = await fetch(path, {
    method,
    credentials: "include",
    headers: {
      "X-Live-Minutes": "1",
      ...(freeRun ? { "X-Free-AI-Run": freeRun } : {}),
      ...(body !== undefined && !isForm ? { "Content-Type": "application/json" } : {})
    },
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body)
  });
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const message = typeof detail === "string" ? detail : Array.isArray(detail) ? "please check the form" : res.statusText;
    throw new ApiError(res.status, message || "request failed");
  }
  const pending = res.status === 202 ? (data as { pending?: FreeRun } | null)?.pending : undefined;
  if (pending && !isForm) {
    const done = await waitForRun(pending);
    if (done.status === "error") throw new ApiError(502, done.error || "the free AI could not finish");
    return request<T>(method, path, body, done.id);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path)
};

export type Role = "owner" | "secretary" | "member" | "viewer";
export const ROLES: Role[] = ["owner", "secretary", "member", "viewer"];
export const ROLE_LABEL: Record<string, string> = { owner: "Full access", secretary: "Runs meetings", member: "Member", viewer: "Read only" };

export interface OrgSummary {
  id: string;
  name: string;
  school: string;
  district: string;
  district_id: string;
  personal?: boolean;
  role: Role;
}

export interface AdminScope {
  scope: "district" | "school";
  id: string;
  name: string;
  district: string;
  role_id: string;
}

export interface Me {
  user: {
    id: string;
    email: string;
    name: string;
    account_type: string;
    is_platform_admin: boolean;
    verified: boolean;
    has_password: boolean;
    can_create_district: boolean;
    admin_scopes: AdminScope[];
    idle_hours?: number;
    terms_current?: boolean;
    two_factor?: boolean;
    recovery_codes_left?: number;
    personal_open?: boolean;
  };
  orgs: OrgSummary[];
}

export interface Org extends OrgSummary {
  style_rules: string;
  aliases: { from: string; to: string }[];
  shared_accounts: { name: string; people: string[] }[];
  allowed_domains: string[];
  public_archive?: boolean;
  default_template_id: string;
  example_template_id: string;
  can_delete?: boolean;
}

export interface Provider {
  id: string;
  label: string;
  default_base_url: string;
  needs_key: boolean;
  needs_base_url: boolean;
  local: boolean;
}

export interface AIConn {
  id: string;
  label: string;
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  has_key: boolean;
  owner_scope: string;
  owner_id: string;
  owner: string;
  can_manage: boolean;
  free?: boolean;
  shares?: { id: string; target_scope: string; target_id: string; target: string }[];
}

export interface Template {
  id: string;
  name: string;
  filename: string;
  mode: "template" | "generated" | "example";
  purpose: "template" | "example";
  created_at: number;
  editable: boolean;
}

export interface Outline {
  slots: string[];
  roll_call: string[];
  report_lines: string[];
  blanks: string[];
  already_written: string[];
}

export interface ReportValue {
  sep?: string;
  text: string;
}

export interface Draft {
  order_time?: string;
  adjourn_time?: string;
  roll_call?: Record<string, string>;
  fills?: { under: string; text: string }[];
  motions?: { under: string; text: string }[];
  replace?: { match: string; text: string }[];
  reports?: Record<string, string | ReportValue>;
  summary?: string[];
  corrections?: { find: string; replace: string; whole_paragraph?: boolean }[];
}

export interface MeetingSummary {
  id: string;
  title: string;
  meeting_date: string;
  status: "scheduled" | "open" | "ended" | "approved";
  run_mode: "live" | "after";
  created_at: number;
  approved_at: number | null;
  scheduled_at: number | null;
  zoom_url: string;
  series_id: string | null;
  has_recording?: boolean;
  sample?: boolean;
}

export interface Meeting extends MeetingSummary {
  org_id: string;
  notes: string;
  role: Role;
  template: { id: string; name: string; mode: string } | null;
  ai_connection: { id: string; label: string; model: string; free?: boolean } | null;
  free_ai?: import("./freeai").FreeRun | null;
  draft: Draft;
  draft_rev: number;
  problems: string[];
  draft_status: "idle" | "queued" | "drafting" | "error";
  draft_error: string;
  drafted_upto: number;
  line_count: number;
  updated_at: number;
  has_export: boolean;
  review: Review;
  duration_min: number;
  timezone: string;
  location: string;
  recording: { type: string; size: number; name: string } | null;
  recording_link: string;
}

export interface Series {
  id: string;
  title: string;
  rule: string;
  frequency: "weekly" | "monthly";
  interval: number;
  weekdays: number[];
  month_week: number;
  month_weekday: number;
  start_date: string;
  until_date: string;
  start_time: string;
  timezone: string;
  duration_min: number;
  zoom_url: string;
  location: string;
  active: boolean;
  next_at: number | null;
}

export interface Review {
  status: "" | "requested" | "changes" | "reviewed";
  note: string;
  requested_at: number | null;
  reviewed_at: number | null;
  reviewer: string;
  required: boolean;
  has_reviewers: boolean;
  can_review: boolean;
}

export interface Line {
  seq: number;
  t: number | null;
  speaker: string;
  text: string;
  source: string;
}

export interface Motion {
  t: number | null;
  mover: string;
  seconder: string;
  text: string;
  status: string;
  result: string;
  roll_call: boolean;
  tally: Record<string, number>;
}

export const rank: Record<Role, number> = { viewer: 0, member: 1, secretary: 2, owner: 3 };
export const can = (role: Role | undefined, need: Role) => !!role && rank[role] >= rank[need];

export async function uploadRecording(meetingId: string, file: File, onProgress: (done: number) => void): Promise<Meeting> {
  const base = "/api/meetings/" + meetingId + "/recording/uploads";
  const start = await api.post<{ upload_id: string; chunk_size: number }>(base, { name: file.name, size: file.size });
  const size = start.chunk_size;
  for (let i = 0, n = 0; i < file.size; i += size, n++) {
    let tries = 0;
    for (;;) {
      const r = await fetch(base + "/" + start.upload_id + "/" + n, {
        method: "PUT", credentials: "include", body: file.slice(i, i + size),
        headers: { "X-Live-Minutes": "1", "Content-Type": "application/octet-stream" }
      });
      if (r.ok) break;
      if (++tries >= 3) {
        const msg = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(msg.detail || "upload failed");
      }
    }
    onProgress(Math.min(file.size, i + size) / file.size);
  }
  return api.post<Meeting>(base + "/" + start.upload_id + "/finish");
}
