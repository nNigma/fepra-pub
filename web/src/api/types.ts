// Типы ответов API. Поля отчётов опциональны там, где бэкенд отдаёт их не всегда.

export type Lang = 'ru' | 'en';
export type Level = 'green' | 'amber' | 'red';

export interface Me {
  id: number;
  nick: string | null;
  lang: Lang;
  roles: { admin: boolean; pro: boolean; coach: boolean };
  gym: string | null;
  has_passkey: boolean;
  garmin: { connected: boolean; status: string } | null;
  public_url: string | null;
}

export interface Verdict {
  level: Level;
  title: string;
  reason: string;
  source?: string;
}
export interface Advice {
  level: Level;
  title: string;
  text: string;
  source?: string;
  date?: string;
  stale?: boolean;
}
export interface Bench {
  latest: number;
  delta: number | null;
}
export type SeriesPoint = [string, number];
export interface MetricSeries {
  series: SeriesPoint[];
  base: number | null;
  dir: 'high_bad' | 'low_bad';
}
export interface ReadinessItem {
  name: string;
  weight: number;
}
export interface Signal {
  label: string;
  value: number | string | null;
  base?: string;
  cls?: Level;
}
export interface NarrativeBlock {
  title: string;
  body: string;
  kind?: string;
}
export interface WatchItem {
  id: string;
  state: 'ok' | 'off' | 'unsupported';
}
export interface MusclesInfo {
  primary?: string[];
  secondary?: string[];
  idle?: string[];
  intensity?: Record<string, number>;
}
export interface NutrMetricWeek {
  sum: number;
  avg: number;
  target_week?: number;
  dir?: string;
  flag?: boolean;
  base?: number;
  series?: SeriesPoint[];
}
export interface NutritionWeek {
  range: [string, string];
  days_recorded: number;
  kcal: { sum?: number; avg?: number; target_week?: number; delta?: number; cls?: Level };
  metrics: Record<string, NutrMetricWeek>;
  protein_per_kg_avg?: number;
  protein_ok?: boolean;
  conclusions?: string[];
  advice?: string[];
}

export interface Summary {
  today: string;
  range: [string, string];
  last_data_day?: string;
  hr_max: number;
  lang?: Lang;
  pro?: boolean;
  is_admin?: boolean;
  viewing?: number;
  m: {
    sleep?: Bench;
    hrv?: Bench;
    rhr?: Bench;
    vo2max?: Bench;
    acwr?: number | null;
    acute7?: number | null;
    chronic28?: number | null;
    monotony?: number | null;
    strain?: number | null;
  };
  verdict: Verdict;
  advice?: Advice | null;
  series: [string, number, number, number, number][];
  sports: [string, number][];
  metrics?: Record<string, MetricSeries>;
  hrv_status?: string | null;
  sleep_deep_h?: number | null;
  sleep_rem_h?: number | null;
  state?: {
    risk?: { level?: Level; title?: string; drivers?: string[] };
    signals?: Record<string, Signal>;
    form?: { vo2max?: number | null; status?: string | null; weight?: number | null };
    readiness?: { value?: number | null; delta?: number | null; base?: number | null; items?: ReadinessItem[] };
  };
  microcycle?: {
    days?: { load?: number; label?: string; readiness?: number | null }[];
    max_streak?: number;
  };
  narrative30?: NarrativeBlock[];
  watch_tuning?: {
    watch?: string;
    others?: string[];
    items?: WatchItem[];
  } | null;
  muscles_week?: MusclesInfo | null;
  nutrition_week?: NutritionWeek | null;
}

export interface WorkoutRow {
  day: string;
  sport: string;
  wod_name?: string | null;
  scaling?: string | null;
  load_kg?: number | null;
  score?: string | null;
  rpe?: number | null;
  readiness?: number | null;
  pr?: boolean;
}

export interface Session {
  sport: string;
  wod_name?: string | null;
  scaling?: string | null;
  load_kg?: number | null;
  score?: string | null;
  rpe?: number | null;
  duration_min?: number | null;
  avg_hr?: number | null;
  max_hr?: number | null;
  calories?: number | null;
  distance_km?: number | null;
  avg_pace_s_per_km?: number | null;
  avg_power_w?: number | null;
  elevation_gain_m?: number | null;
  hr_series?: [number, number][];
  zones?: number[];
  extra?: Record<string, any>;
  narrative?: NarrativeBlock[];
}
export interface WorkoutDetail {
  day: string;
  trimp: number;
  hr_max?: number;
  pro?: boolean;
  condition?: {
    verdict: Verdict;
    readiness?: number | null;
    hrv_delta?: number | null;
    sleep_delta?: number | null;
  } | null;
  sessions: Session[];
  history: Record<string, { day: string; load_kg?: number | null; score?: string | null }[]>;
  muscles?: MusclesInfo | null;
}

export interface LlmStatus {
  available: boolean;
  cached: { text: string; engine: string } | null;
  stale?: boolean;
  remaining?: number;
}
export interface LlmRun {
  text?: string;
  engine?: string;
  cached?: boolean;
  pending?: boolean;
}
export interface ClaudeReview {
  available: boolean;
  text: string | null;
}

export interface NutritionDays {
  days: { day: string; kcal?: number; protein_g?: number; fat_g?: number; carb_g?: number; meals: number; verdict?: number | null }[];
  weight_kg?: number | null;
}
export interface Meal {
  id?: number;
  ts?: string;
  kcal?: number;
  protein_g?: number;
  fat_g?: number;
  carb_g?: number;
  foods?: { name: string; grams?: number | null }[];
  quality?: number | null;
  quality_note?: string | null;
}
export interface NutritionDay {
  day: string;
  meals: Meal[];
  totals: Record<string, number>;
  water_l?: number | null;
  water_target_l?: number | null;
  protein_per_kg?: number | null;
  advice?: string[];
  targets?: { kcal: number; protein_g: number; fat_g: number; carb_g: number } | null;
  burned?: number;
  day_verdict?: number | null;
  pro?: boolean;
}

export interface CompetitionRow {
  id: number;
  name: string;
  date: string;
  final_place: number | null;
  field: number;
}
export interface RadarSet {
  name: string;
  date?: string;
  grades: Record<string, number>;
}
export interface BestWorstItem {
  name: string;
  field: number;
  result?: { place?: number | null };
}
export interface Competitions {
  starts: number;
  best_place?: number | null;
  totals?: CompetitionRow[];
  radars?: RadarSet[];
  best_worst?: { best?: BestWorstItem[]; worst?: BestWorstItem[] };
  narrative?: NarrativeBlock[];
  pro?: boolean;
}
export interface CompetitionDetail {
  name: string;
  city?: string;
  date: string;
  division?: string;
  final_place: number | null;
  field: number;
  total_points?: number | null;
  dynamics?: { idx: number; place: number }[];
  radar?: Record<string, number>;
  table?: { name: string; place: number | null; percentile: number }[];
  narrative?: NarrativeBlock[];
  scenario?: { gain?: number; target_place?: number };
}

export interface GoalItem {
  id?: number;
  title: string;
  progress?: { pct?: number; done?: boolean; text?: string };
}
export interface Discipline {
  id?: string;
  kind?: 'lift' | 'benchmark' | string;
  name: string;
  has_data: boolean;
  unit?: 'kg' | 'time' | string;
  value?: number;
  idx?: number | null;
  level?: string | null;
  distance_text?: string | null;
}
export interface Goals {
  overall?: { level?: string | null; progress?: number; assessed?: number; total?: number };
  goals?: GoalItem[];
  lifts?: Discipline[];
  benchmarks?: Discipline[];
  bot_username?: string;
}

export interface LbRow {
  place: number;
  nick?: string | null;
  tg_id?: number;
  user_id?: number;
  value: string | number;
  tier?: string | null;
  is_me?: boolean;
}
export interface Leaderboard {
  metric: string;
  rows: LbRow[];
  disciplines: { id: string; name: string }[];
  no_gym?: boolean;
}

export interface AppUser {
  tg_id?: number;
  id?: number;
  nick?: string | null;
}

// --- вход и профиль (Волна 1) ---
export interface RedeemResult {
  ok?: boolean;
  user?: Me;
}
export interface Invite {
  token?: string;
  url?: string;
  role?: string;
  gym?: string | null;
  note?: string | null;
  existing_user_id?: number | null;
  expires_at?: string;
  used_at?: string | null;
  created_at?: string;
}
export interface InviteIn {
  role: 'athlete' | 'pro' | 'coach' | 'admin';
  gym: string | null;
  existing_user_id: number | null;
  ttl_hours: number;
  note: string;
}

// --- Garmin ---
export interface GarminStatus {
  connected: boolean;
  status: string;
  email?: string;
  last_sync?: string | null;
}
export interface GarminLoginResult {
  status: 'ok' | 'need_mfa' | 'error';
  message?: string;
}
export interface JobStarted {
  job_id: string;
}
export interface Job {
  status: 'pending' | 'running' | 'done' | 'error';
  result?: unknown;
  error?: string | null;
}
