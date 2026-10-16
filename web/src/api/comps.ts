import { rest } from './rest';

export interface CompDivisionRef {
  id: number;
  name: string;
  field_size: number | null;
  participant_id: number | null;
}
export interface CompEventRow {
  id: number;
  name: string;
  city: string | null;
  date_start: string;
  date_end?: string | null;
  division_id?: number;
  divisions: CompDivisionRef[];
}
export interface CompList {
  mine: CompEventRow[];
  others: CompEventRow[];
}

export interface CompResult {
  id?: number;
  athlete?: string;
  value: string | null;
  place: number | null;
  field_size?: number | null;
  [k: string]: unknown;
}
export interface CompStage {
  id: number;
  idx: number;
  name: string;
  prescription?: string | null;
  movements?: string[];
  format?: string;
  results?: CompResult[];
}
export interface CompDivision extends CompDivisionRef {
  stages: CompStage[];
  total_points?: number | null;
  final_place?: number | null;
}
export interface CompEvent {
  id: number;
  name: string;
  city: string | null;
  date_start: string;
  date_end?: string | null;
  divisions: CompDivision[];
}

export type Category = 'newbie' | 'pro' | 'int' | 'rx';
export interface CreateEventBody {
  name: string;
  date: string;
  city: string;
  category?: Category;
  division?: string;
  force_new?: boolean;
}
export interface CreateEventOk {
  created: true;
  duplicate: false;
  event_id: number;
  division_id: number;
  participant_id: number;
}
export interface CreateEventDup {
  created: false;
  duplicate: true;
  candidates: CompEventRow[];
}
export type CreateEventResponse = CreateEventOk | CreateEventDup;

export interface ParsedStage {
  idx: number;
  name: string;
  prescription: string;
  format?: string;
  movements?: string[];
  source_ref?: string;
}
export interface StagesParseResult {
  recognized: boolean;
  reason: 'quota' | 'no_vision' | 'not_recognized' | null;
  division_id?: number;
  stages: ParsedStage[];
  preview?: string[];
}
export interface ParsedRow {
  stage: number | null;
  value: string | null;
  place: number | null;
  stage_id: number | null;
  stage_idx?: number | null;
  stage_name?: string | null;
}
export interface ResultsParseResult {
  recognized: boolean;
  reason: 'quota' | 'no_vision' | 'not_recognized' | null;
  athlete?: string;
  division_id?: number;
  rows: ParsedRow[];
}
export interface TotalSuggestion {
  total_points: number | null;
  final_place: number | null;
  field_size: number | null;
  place_str?: string | null;
  division_id: number;
  participant_id: number;
}

const E = (id: number) => `/api/comp/events/${id}`;

export const compsApi = {
  list: () => rest.get<CompList>('/api/comp/list'),
  event: (id: number | string) => rest.get<CompEvent>(`/api/comp/events/${id}`),
  create: (b: CreateEventBody) => rest.post<CreateEventResponse>('/api/comp/events', b),
  join: (id: number, division_id?: number | null) =>
    rest.post<{ event_id: number; division_id: number; participant_id: number; created: boolean }>(`${E(id)}/join`, division_id ? { division_id } : {}),
  addStageText: (id: number, text: string, division_id?: number | null) =>
    rest.post<{ stage_id: number; idx: number; division_id: number }>(`${E(id)}/stages`, division_id ? { text, division_id } : { text }),
  parseStages: (id: number, upload_id: string, division_id?: number | null, note?: string) =>
    rest.post<{ job_id: string }>(`${E(id)}/stages/parse`, { upload_id, division_id: division_id ?? null, ...(note ? { note } : {}) }),
  confirmStages: (b: { event_id: number; stages: ParsedStage[]; division_id?: number | null }) =>
    rest.post<{ saved: number; skipped: number; division_id: number }>('/api/comp/stages/confirm', b),
  addResultText: (id: number, b: Record<string, unknown>) =>
    rest.post<{ result_id: number; stage_id: number; stage_idx: number; value: string; place: number | null; field_size: number | null }>(`${E(id)}/results`, b),
  parseResults: (id: number, b: { upload_id: string; athlete?: string; division_id?: number | null; note?: string }) =>
    rest.post<{ job_id: string }>(`${E(id)}/results/parse`, b),
  confirmResults: (b: Record<string, unknown>) =>
    rest.post<{ saved: number; skipped: number; division_id: number }>('/api/comp/results/confirm', b),
  total: (id: number) => rest.get<TotalSuggestion>(`${E(id)}/total`),
  putTotal: (id: number, b: { total_points?: number; final_place?: number }) =>
    rest.put<{ participant_id: number; total_points: number; final_place: number; source: string }>(`${E(id)}/total`, b),
  fieldSize: (divisionId: number, field_size: number) =>
    rest.put<{ division_id: number; field_size: number }>(`/api/comp/divisions/${divisionId}/field_size`, { field_size }),
};
