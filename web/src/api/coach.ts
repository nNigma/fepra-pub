import { rest } from './rest';

export interface CoachQA {
  ts: string;
  lang: string;
  question: string;
  answer: string;
  engine: string | null;
}
export interface CoachAnswer {
  id: number;
  answer: string;
  engine: string | null;
  ts: string;
}

export const coachApi = {
  ask: (q: string) => rest.post<{ job_id: string }>('/api/coach/ask', { q }),
  recent: (limit = 20) => rest.get<CoachQA[]>(`/api/coach/recent?limit=${limit}`),
};
