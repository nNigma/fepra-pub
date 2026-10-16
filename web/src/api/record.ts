// Запись тренировки, цели, ПМ, вес тела, самочувствие: типы и вызовы (фаза 3, docs/pwa/api-workouts-examples.md).
import { api, request } from './client';

export type Sport = 'crossfit' | 'weightlifting' | 'hyrox' | 'run' | 'bike';
export const BOARD_SPORTS: Sport[] = ['crossfit', 'weightlifting', 'hyrox'];
export const SPORTS: Sport[] = ['crossfit', 'weightlifting', 'hyrox', 'run', 'bike'];
export type Scaling = 'rx' | 'scaled' | null;
export type Engine = 'fast' | 'slow';

export type FieldType =
  | 'weight_reps' | 'weight' | 'time' | 'int' | 'rounds_reps' | 'text'
  | 'cardio' | 'weight_distance' | 'reps_load';

/** Единица кардио: ккал, метры или время в секундах / минутах — выбирает атлет. */
export type CardioUnit = 'kcal' | 'm' | 'sec' | 'min';
export type TimeUnit = 'sec' | 'min';
export interface FormField {
  key: string;
  label: string;
  type: FieldType;
  unit?: string | null;
  section?: string | null;
  group?: string | null;
  movement?: string | null;
  /** повторы по схеме (подходы 5×5, лесенка 21-15-9): подставляются, если атлет их не менял */
  reps_default?: number | null;
  /** вес в for-time/AMRAP: повторы можно не вводить */
  reps_optional?: boolean;
  /** кардио: единица по умолчанию (ккал для гребли/лыж/байка, м для бега) */
  default_unit?: CardioUnit | null;
}
/** Значение поля формы для сервера: число, строка или объект для составных типов. */
export type FormValue = string | number | Record<string, string | number | null>;

export interface FormBlock {
  index: number;
  title: string;
  format?: string;
  kind?: string;
  has_cap?: boolean;
  fields: FormField[];
}
export interface ResultForm {
  version?: number;
  blocks: FormBlock[];
}

export type ParseReason = null | 'quota' | 'no_vision' | 'not_recognized';
export interface ParseResult {
  recognized: boolean;
  reason: ParseReason;
  board_text: string | null;
  format?: string | null;
  engine_used?: string | null;
  sport?: string;
  blocks: unknown[];
  blocks_verified?: boolean;
  form: ResultForm;
  template_text?: string | null;
  annotated?: string;
}

export interface GymProgram {
  found: boolean;
  day: string;
  gym?: string;
  board_text?: string;
  blocks?: unknown[];
  blocks_verified?: boolean;
  form?: ResultForm;
  template_text?: string;
}

export interface Credited {
  discipline: string;
  name?: string;
  weight: number;
  reps: number;
  est_1rm?: number;
  tier?: TierInfo | string | null;
}
export interface TierInfo {
  level?: string;
  idx?: number;
  distance?: number | null;
}
export interface VariantOpt {
  id: string;
  label: string;
}
export interface Ambiguous {
  movement: string;
  family?: string;
  weight: number;
  reps: number;
  variants: VariantOpt[];
}
export interface ProposedMax {
  movement: string;
  weight_kg: number;
  reps: number;
}
export interface ProposedMaxes {
  maxes: ProposedMax[];
  credited?: Credited[];
  ambiguous?: Ambiguous[];
}

export interface SaveResponse {
  activity_id: string;
  created?: boolean;
  day: string;
  sport: string;
  score?: string | null;
  rpe?: number | null;
  scaling?: string | null;
  board_source?: string | null;
  metcon_lines?: string[];
  credited?: Credited[];
  ambiguous?: Ambiguous[];
  proposed_maxes?: ProposedMaxes | null;
  lifts_skipped_quota?: boolean;
  bodyweight?: number | null;
  like_for_like?: unknown;
}

export interface RecentWorkout {
  id: string;
  day: string;
  sport: string;
  source?: string;
  wod_format?: string | null;
  score?: string | null;
  scaling?: string | null;
  rpe?: number | null;
  duration_min?: number | null;
  distance_km?: number | null;
  start_time?: string | null;
  board_source?: string | null;
  updated_at?: string | null;
}
export interface WorkoutFull extends RecentWorkout {
  board_text?: string | null;
  blocks?: unknown[];
  form?: ResultForm | null;
  form_values?: Record<string, unknown> | null;
  result_text?: string | null;
  metcon?: unknown;
  maxes?: { discipline: string; value: number; reps?: number; est_1rm?: number; source?: string }[];
  bodyweight?: number | null;
  editable?: boolean;
  board_editable?: boolean;
}
export interface PatchResponse {
  workout?: WorkoutFull;
  metcon_lines?: string[];
  credited?: Credited[];
  ambiguous?: Ambiguous[];
}

export interface PutBody {
  day: string;
  sport: Sport;
  start_time?: string;
  duration_min?: number;
  distance_km?: number;
  rpe?: number;
  scaling?: 'rx' | 'scaled';
  bodyweight?: number;
  board?: { text?: string; gym?: string; source: 'own' | 'gym'; format?: string | null; blocks?: unknown[]; blocks_verified?: boolean };
  form_result?: Record<string, FormValue> | string;
}

export interface GoalRow {
  id: number;
  kind: 'numeric' | 'level' | string;
  title: string;
  exercise?: string | null;
  benchmark?: string | null;
  target_value?: string | number | null;
  metric?: string;
  status: string;
  created_at?: string;
}
export interface PmResult {
  discipline: string;
  name: string;
  value: number;
  reps?: number | null;
  est_1rm?: number;
  day?: string;
  tier?: TierInfo | string | null;
}

const q = encodeURIComponent;

export const recordApi = {
  upload: (file: File, kind: 'board' | 'meal' | 'other' = 'board') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('kind', kind);
    return request<{ id: string; url: string; mime: string; size: number; kind: string }>('/api/uploads', {
      method: 'POST',
      body: fd,
    });
  },
  parse: (b: { upload_id?: string; text?: string; sport: Sport; engine: Engine; verbatim?: boolean }) =>
    api.post<{ job_id: string }>('/api/board/parse', b),
  gymProgram: (day: string, gym?: string) => api.getPlain<GymProgram>(`/api/gym-program?day=${q(day)}${gym ? `&gym=${q(gym)}` : ''}`),
  put: (id: string, body: PutBody) => request<SaveResponse>(`/api/workouts/${q(id)}`, { method: 'PUT', body }),
  recent: (limit = 10) => api.getPlain<RecentWorkout[]>(`/api/workouts/recent?limit=${limit}`),
  get: (id: string) => api.getPlain<WorkoutFull>(`/api/workouts/${q(id)}`),
  patch: (id: string, body: Record<string, unknown>) =>
    request<PatchResponse>(`/api/workouts/${q(id)}`, { method: 'PATCH', body }),
  remove: (id: string) => request<{ id: string; deleted_at: string }>(`/api/workouts/${q(id)}`, { method: 'DELETE' }),
  restore: (id: string) => api.post<WorkoutFull>(`/api/workouts/${q(id)}/restore`),
  resolveLift: (id: string, b: { movement: string; variant: string; weight: number; reps: number }) =>
    api.post<Credited>(`/api/workouts/${q(id)}/lifts/resolve`, b),
  confirmMaxes: (id: string, maxes: ProposedMax[]) =>
    api.post<{ credited: Credited[]; ambiguous: Ambiguous[]; skipped_quota?: boolean }>(
      `/api/workouts/${q(id)}/maxes`,
      { maxes },
    ),

  goalItems: () => api.getPlain<GoalRow[]>('/api/goals/items'),
  addGoal: (b: { kind: 'numeric' | 'level'; discipline: string; target: string | number }) =>
    api.post<GoalRow>('/api/goals/items', b),
  archiveGoal: (id: number) => api.post<GoalRow>(`/api/goals/items/${id}/archive`),
  completeGoal: (id: number) => api.post<GoalRow>(`/api/goals/items/${id}/complete`),
  enterPm: (b: { discipline: string; value: string | number; reps?: number }) => api.post<PmResult>('/api/pm', b),
  bodyweight: (kg: number, day?: string) => api.post<{ day: string; kg: number }>('/api/bodyweight', { kg, day }),
  feel: (score: number) => api.post<{ day: string; score: number }>('/api/feel', { score }),
};
