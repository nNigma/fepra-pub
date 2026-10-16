import { api, request } from './client';
import type * as T from './types';
import {
  assertionToJSON,
  creationOptionsFromJSON,
  registrationToJSON,
  requestOptionsFromJSON,
  type CreationOptionsJSON,
  type RequestOptionsJSON,
} from './webauthn';

const q = encodeURIComponent;

export const endpoints = {
  // --- вход / сессия ---
  me: () => request<T.Me>('/api/me', { quiet401: true }),
  logout: () => api.post<void>('/api/auth/logout'),
  inviteInfo: (token: string) =>
    request<{ valid: boolean; existing: boolean; nick: string | null }>('/api/auth/invite-info', { method: 'POST', body: { token }, quiet401: true }),
  redeem: (token: string, nick: string) =>
    request<T.RedeemResult>('/api/auth/redeem', { method: 'POST', body: { token, nick }, quiet401: true }),
  setLang: (lang: T.Lang) => api.post<{ lang: T.Lang }>('/api/lang', { lang }),

  // --- отчёты (существующие GET) ---
  summary: () => api.get<T.Summary>('/api/summary'),
  workouts: (limit = 60) => api.get<T.WorkoutRow[]>(`/api/workouts?limit=${limit}`),
  workout: (day: string) => api.get<T.WorkoutDetail>(`/api/workout/${q(day)}`),
  claude: (day: string) => api.get<T.ClaudeReview>(`/api/claude/${q(day)}`),
  nutritionDays: () => api.get<T.NutritionDays>('/api/nutrition/days'),
  nutritionDay: (day: string) => api.get<T.NutritionDay>(`/api/nutrition?day=${q(day)}`),
  competitions: () => api.get<T.Competitions>('/api/competitions'),
  competition: (id: number | string) => api.get<T.CompetitionDetail>(`/api/competition/${q(String(id))}`),
  goals: () => api.get<T.Goals>('/api/goals'),
  leaderboard: (metric: string) => api.get<T.Leaderboard>(`/api/leaderboard?metric=${q(metric)}`),
  users: () => api.getPlain<T.AppUser[]>('/api/users'),

  // --- ИИ-разборы ---
  llmStatus: (kind: string, ref: string) => api.get<T.LlmStatus>(`/api/llm/${q(kind)}/${q(ref)}`),
  llmRun: (kind: string, ref: string, refresh: boolean) =>
    api.post<T.LlmRun>(`/api/llm/${q(kind)}/${q(ref)}${refresh ? '?refresh=1' : ''}`),

  // --- админ ---
  createInvite: (body: T.InviteIn) => api.post<T.Invite>('/api/admin/invites', body),
  invites: () => api.getPlain<T.Invite[] | { invites: T.Invite[] }>('/api/admin/invites'),

  // --- Garmin ---
  garminStatus: () => api.getPlain<T.GarminStatus>('/api/garmin/status'),
  garminLogin: (email: string, password: string) =>
    api.post<T.GarminLoginResult>('/api/garmin/login', { email, password }),
  garminMfa: (code: string) => api.post<T.GarminLoginResult>('/api/garmin/mfa', { code }),
  garminSync: () => api.post<T.JobStarted>('/api/garmin/sync'),
  garminHistory: (days: number) => api.post<T.JobStarted>('/api/garmin/history', { days }),
  garminDisconnect: () => api.post<void>('/api/garmin/disconnect'),
  job: (id: string) => api.getPlain<T.Job>(`/api/jobs/${q(id)}`),
};

// --- passkey ---
interface ChallengeEnvelope {
  options?: unknown;
  publicKey?: unknown;
  challenge_id?: string;
  [k: string]: unknown;
}

function unwrap<O>(res: ChallengeEnvelope): { options: O; challengeId?: string } {
  const options = (res.options ?? res.publicKey ?? res) as O;
  return { options, challengeId: res.challenge_id };
}

/** Регистрация Face ID / отпечатка для уже вошедшего пользователя. */
export async function registerPasskey(): Promise<void> {
  const res = await api.post<ChallengeEnvelope>('/api/auth/passkey/register/options');
  const { options, challengeId } = unwrap<CreationOptionsJSON>(res);
  const cred = (await navigator.credentials.create({
    publicKey: creationOptionsFromJSON(options),
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('cancelled');
  await api.post('/api/auth/passkey/register/verify', {
    challenge_id: challengeId,
    credential: registrationToJSON(cred),
  });
}

/** Вход по passkey. Возвращает состояние сессии. */
export async function loginWithPasskey(): Promise<void> {
  const res = await request<ChallengeEnvelope>('/api/auth/passkey/login/options', {
    method: 'POST',
    body: {},
    quiet401: true,
  });
  const { options, challengeId } = unwrap<RequestOptionsJSON>(res);
  const cred = (await navigator.credentials.get({
    publicKey: requestOptionsFromJSON(options),
  })) as PublicKeyCredential | null;
  if (!cred) throw new Error('cancelled');
  await request('/api/auth/passkey/login/verify', {
    method: 'POST',
    body: { challenge_id: challengeId, credential: assertionToJSON(cred) },
    quiet401: true,
  });
}
