// Программы (фаза 4): типы ответов и вызовы. Примеры JSON — docs/pwa/api-programs-examples.md.
import { ApiError, api, request } from './client';

const q = encodeURIComponent;

export interface Loc { ru: string; en: string }

export type NodeStatus = 'active' | 'planned' | 'hidden';
export interface TreeNode {
  slug: string;
  parent: string | null;
  kind: 'sport' | 'system' | 'program';
  title_ru: string;
  title_en: string;
  status: NodeStatus;
  soon: boolean;
  sort: number;
  template_slug: string | null;
  children: TreeNode[];
}

export type RefSource = 'best' | 'derived' | 'starter' | 'needs_input' | 'user' | 'test';
export type StartLevel = 'careful' | 'normal' | 'experienced';
export interface Reference {
  lift: string;
  kg: number | null;
  source: RefSource;
  stale?: boolean;
  day?: string;
  from?: string[];
  level?: StartLevel;
  note?: string;
  note_en?: string;
  options?: Partial<Record<StartLevel, number>>;
  question?: Loc;
}

export interface RequirementLift {
  lift: string;
  name: Loc;
  required: boolean;
  reference: Reference;
}
export interface WeekBrief {
  week: number;
  type: 'volume' | 'medium' | 'high' | 'deload' | 'test' | string;
  title: Loc;
  note?: Loc | null;
  sessions: number;
  days?: DayBrief[];
}
export interface DayBrief {
  idx: number;
  dow: number;
  title: Loc;
  minutes: number;
  kind: string;
  purpose?: Loc | null;
  focus?: { ru: string[]; en: string[] } | null;
  intensity?: string | null;
}
export interface AboutBlock {
  id: string;
  title: Loc;
  text: Loc;
}
export interface ProgramCardData {
  slug: string;
  kind: string;
  title_ru: string;
  title_en: string;
  status: NodeStatus;
  soon: boolean;
  template?: {
    version: number;
    title: Loc;
    summary: Loc;
    params: { weeks: number; session_minutes?: number[]; days_per_week?: number[] };
    required_lifts: string[];
    optional_lifts: string[];
    rules?: Record<string, unknown>;
    weeks: WeekBrief[];
    about?: AboutBlock[];
    week_types?: Record<string, { title: Loc; text: Loc }>;
  } | null;
  requirements?: { lifts: RequirementLift[]; needs_input: string[]; needs_test: string[] } | null;
  enrollment_id: string | null;
  children?: TreeNode[];
}

export interface EnrollBody {
  start_day: string;
  base_maxes?: Record<string, number>;
  level?: StartLevel;
  weekdays?: number[];
  id?: string;
}

export interface Enrollment {
  id: string;
  program_slug: string;
  title_ru: string | null;
  title_en: string | null;
  template_version: number;
  start_day: string;
  status: 'active' | 'paused' | 'cancelled' | 'done' | string;
  level: StartLevel | null;
  base_maxes: Record<string, Reference>;
  sessions: { total: number; planned?: number; in_progress?: number; done?: number; skipped?: number };
  next_session: { id: string; planned_day: string; week: number; idx: number; kind: string } | null;
  test_lifts?: string[];
  existing?: boolean;
  refreshed?: string[];
}

export interface SetRow {
  id: string;
  n: number;
  kind: 'ladder' | 'work' | 'day_max' | 'attempt' | string;
  pct?: number | null;
  planned_kg: number | null;
  rest_sec: number;
  reps: number | null;
  done_kg: number | null;
  ok: boolean | null;
  note?: string | null;
  ts?: string | null;
  exercise?: string;
}
export interface ExerciseBlock {
  id: string;
  lift: string;
  name: Loc;
  sets: SetRow[];
}
export interface SessionBlock { title: Loc; exercises: ExerciseBlock[] }
export interface AdjustInfo {
  level: 'none' | 'minus5' | 'illness' | 'cap' | string;
  delta_pct: number;
  cap_pct: number | null;
  signals: string[];
  postpone_advised: boolean;
}
export interface Checkin {
  energy?: number;
  tired?: boolean;
  sleepy?: boolean;
  joint?: boolean;
  ill?: boolean;
}
export interface SessionView {
  id: string;
  enrollment_id: string;
  planned_day: string;
  week: number;
  idx: number;
  kind: 'normal' | 'test' | 'deload' | string;
  status: 'planned' | 'in_progress' | 'done' | 'skipped' | string;
  week_type: string;
  week_title: Loc;
  week_note?: string | Loc | null;
  title: Loc;
  minutes: number;
  purpose?: Loc | null;
  focus?: { ru: string[]; en: string[] } | null;
  intensity?: string | null;
  week_type_info?: { title: Loc; text: Loc } | null;
  checkin: Checkin | null;
  adjust: AdjustInfo;
  why: string | null;
  why_en: string | null;
  activity_id: string | null;
  blocks: SessionBlock[];
  extra_sets: SetRow[];
  misses: unknown[];
}
export type TodayState = 'today' | 'in_progress' | 'upcoming' | 'overdue' | 'none' | 'paused' | 'cancelled' | 'done';
export interface TodayView {
  state: TodayState;
  enrollment_id: string;
  date: string;
  session: SessionView | null;
}

export interface SetPut {
  done_kg?: number | null;
  reps?: number | null;
  ok?: boolean | null;
  note?: string | null;
  exercise?: string;
  ts?: string;
}
export interface SetPutResult {
  set: { id: string; exercise: string; planned_kg: number | null; done_kg: number | null; reps: number | null; ok: boolean | null; ts: string | null };
  changed: string[];
  why: Loc | null;
  session_status: string;
}
export interface RefreshSuggestion {
  lift: string;
  base_kg: number;
  new_kg: number;
  delta_kg: number;
  ru: string;
  en: string;
}
export interface FinishResult {
  session_id: string;
  status: string;
  already: boolean;
  activity_id: string;
  maxes: { lift: string; kg: number; reps: number }[];
  refresh: RefreshSuggestion[];
  base_updated: string[];
  enrollment_done: boolean;
}
export interface TrendData {
  lift: string;
  points: { day: string; kg: number; session_id: string }[];
  delta_kg: number | null;
  trend: 'up' | 'flat' | 'down' | 'none';
  best: number | null;
}

/** Ошибка 422 needs_input: вопросы по лифтам без опорного веса. */
export class NeedsInputError extends Error {
  items: Record<string, Reference>;
  constructor(items: Record<string, Reference>) {
    super('needs_input');
    this.name = 'NeedsInputError';
    this.items = items;
  }
}

export function localToday(d = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function newId(): string {
  const c = globalThis.crypto as Crypto | undefined;
  if (c?.randomUUID) return c.randomUUID();
  const h = (n: number) => Math.floor(Math.random() * 16 ** n).toString(16).padStart(n, '0');
  return `${h(8)}-${h(4)}-4${h(3)}-a${h(3)}-${h(12)}`;
}

/** 422 needs_input несёт вопросы по лифтам в `items`: превращаем в NeedsInputError. */
async function enroll(slug: string, body: EnrollBody): Promise<Enrollment> {
  try {
    return await request<Enrollment>(`/api/programs/${q(slug)}/enroll?today=${localToday()}`, { method: 'POST', body });
  } catch (e) {
    if (e instanceof ApiError && e.status === 422 && e.code === 'needs_input' && e.body?.items) {
      throw new NeedsInputError(e.body.items as Record<string, Reference>);
    }
    throw e;
  }
}

export const programsApi = {
  tree: () => api.getPlain<{ tree: TreeNode[] }>('/api/programs/tree').then((r) => r.tree),
  program: (slug: string) => api.get<ProgramCardData>(`/api/programs/${q(slug)}?today=${localToday()}`),
  enroll,
  enrollments: () => api.get<{ enrollments: Enrollment[] }>('/api/enrollments').then((r) => r.enrollments),
  enrollment: (id: string) => api.get<Enrollment>(`/api/enrollments/${q(id)}`),
  today: (id: string) => api.get<TodayView>(`/api/enrollments/${q(id)}/today?today=${localToday()}`),
  refreshBase: (id: string, lifts?: string[]) =>
    api.post<Enrollment>(`/api/enrollments/${q(id)}/refresh-base`, lifts ? { lifts } : {}),
  setStatus: (id: string, action: 'pause' | 'resume' | 'cancel') =>
    api.post<Enrollment>(`/api/programs/enrollments/${q(id)}/${action}`),
  session: (id: string) => api.get<SessionView>(`/api/sessions/${q(id)}`),
  putSet: (sid: string, setId: string, body: SetPut) =>
    request<SetPutResult>(`/api/sessions/${q(sid)}/sets/${q(setId)}`, { method: 'PUT', body }),
  checkin: (sid: string, body: Checkin) => api.post<SessionView>(`/api/sessions/${q(sid)}/checkin`, body),
  finish: (sid: string, body: { rpe?: number; feel?: number; activity_id?: string } = {}) =>
    api.post<FinishResult>(`/api/sessions/${q(sid)}/finish?today=${localToday()}`, body),
  trend: (lift: string, window = 7) => api.get<TrendData>(`/api/lifts/${q(lift)}/trend?window=${window}`),
};

// --- Push и уведомления ---
export interface Notice {
  id: string;
  kind: string;
  text: string;
  created_at: string;
  read_at: string | null;
}
export interface PushSubJSON {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}
export const pushApi = {
  key: () => api.getPlain<{ public_key: string }>('/api/push/key'),
  subscribe: (sub: PushSubJSON) => api.post<{ id: string }>('/api/push/subscribe', sub),
  unsubscribe: (endpoint: string) => api.post<{ ok: boolean }>('/api/push/unsubscribe', { endpoint }),
  notices: () => api.getPlain<Notice[]>('/api/notices?unread=1'),
  readNotice: (id: string) => api.post<{ ok: boolean }>(`/api/notices/${q(id)}/read`),
};
