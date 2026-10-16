import { rest, q } from './rest';

export interface ClubProgram {
  id: number;
  uuid: string;
  day: string;
  gym: string;
  raw_text: string;
  format: string;
  movements: string[];
  blocks: unknown[] | null;
  blocks_verified: boolean;
  source: string | null;
  confirmed: boolean;
  updated_at: string | null;
  created_by: number | null;
}
export interface ClubDay {
  gym: string;
  day: string;
  program: ClubProgram | null;
  last_day: string | null;
  can_manage: boolean;
}
export interface ClubGym {
  name: string;
  is_default: boolean;
  is_mine: boolean;
  can_manage: boolean;
}
export interface ClubGyms {
  current: string;
  can_add?: boolean;
  gyms: ClubGym[];
}
export interface ClubPreview {
  raw_text: string;
  format: string;
  canon: string[];
  unknown: string[];
  annotated: string;
}
export interface ClubSaved {
  program: ClubProgram;
  unknown: string[];
  job_id: string | null;
}
export interface DictEntry {
  canon: string;
  aliases: string[];
}

export const clubApi = {
  /** залы для выбора: админу все, тренеру его залы, атлету свой */
  gyms: () => rest.get<ClubGyms>('/api/club/gyms'),
  program: (day?: string, gym?: string) => {
    const p = [day && `day=${q(day)}`, gym && `gym=${q(gym)}`].filter(Boolean).join('&');
    return rest.get<ClubDay>(`/api/club/program${p ? '?' + p : ''}`);
  },
  save: (b: { day: string; raw_text: string; gym?: string }) => rest.put<ClubSaved>('/api/club/program', b),
  /** фото доски -> задача (job_id); результат {recognized, reason, board_text} */
  parsePhoto: (upload_id: string, engine: 'fast' | 'slow' = 'fast', gym?: string) =>
    rest.post<{ job_id: string }>('/api/club/program/parse', gym ? { upload_id, engine, gym } : { upload_id, engine }),
  preview: (raw_text: string, gym?: string) =>
    rest.post<ClubPreview>('/api/club/program/preview', gym ? { raw_text, gym } : { raw_text }),
  pending: (gym?: string) => rest.get<ClubProgram[]>(`/api/club/pending${gym ? '?gym=' + q(gym) : ''}`),
  confirm: (id: number, raw_text?: string) => rest.post<ClubProgram>(`/api/club/pending/${id}/confirm`, raw_text != null ? { raw_text } : {}),
  reject: (id: number) => rest.del<{ ok: boolean }>(`/api/club/pending/${id}`),
  stats: (gym?: string) =>
    rest.get<{ gym: string; movements: { canon: string; count: number; name: string }[] }>(`/api/club/stats${gym ? '?gym=' + q(gym) : ''}`),
  athletes: (days = 30, gym?: string) =>
    rest.get<{ gym: string; days: number; since: string; athletes: { id: number; nick: string | null; workouts: number }[] }>(`/api/club/athletes?days=${days}${gym ? '&gym=' + q(gym) : ''}`),
  dictionary: () => rest.get<DictEntry[]>('/api/club/dictionary'),
  addAliases: (pairs: { alias: string; canon: string }[]) => rest.post<{ added: number }>('/api/club/aliases', { pairs }),
  resolve: (phrase: string, name?: string) => rest.post<{ phrase: string; canon: string; created: boolean }>('/api/club/movements/resolve', name ? { phrase, name } : { phrase }),
};
