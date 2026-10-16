import { rest, q } from './rest';

export interface Food {
  name: string;
  grams: number | null;
  kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  [k: string]: string | number | null | undefined;
}

export interface MealDraft {
  foods: Food[];
  totals?: { kcal: number; protein_g: number; fat_g: number; carb_g: number };
  question?: string | null;
  confidence?: string | null;
  quality?: number | null;
  quality_note?: string | null;
}

export type MealSource =
  | { kind: 'photo'; upload_id: string; url?: string; text?: null; meal_id?: number }
  | { kind: 'text'; text: string; upload_id?: null; meal_id?: number };

export interface MealParseResult {
  recognized: boolean;
  reason: 'quota' | 'no_vision' | 'not_recognized' | null;
  draft: MealDraft | null;
  notes: string[];
  source: { kind: 'photo' | 'text'; upload_id?: string | null; url?: string | null; text?: string | null; meal_id?: number };
}

export interface Meal {
  id: number;
  uuid: string | null;
  day: string;
  ts: string;
  foods: Food[];
  kcal: number | null;
  protein_g: number | null;
  fat_g: number | null;
  carb_g: number | null;
  note: string | null;
  photo_url: string | null;
  quality: number | null;
  quality_note: string | null;
  engine: string | null;
}

export interface MealsDay {
  day: string;
  meals: Meal[];
  totals: Record<string, number>;
  water_l: number;
  water_ml: number;
  targets?: { kcal: number; protein_g: number; fat_g: number; carb_g: number } | null;
  burned?: number;
  water_target_l?: number | null;
  micro_targets?: Record<string, number>;
  micro_limit?: string[];
  protein_per_kg?: number | null;
}

export interface ParseRequest {
  upload_id?: string;
  text?: string;
  correction?: string;
  notes?: string[];
}

export interface SaveRequest {
  draft: MealDraft;
  day?: string;
  ts?: string | null;
  uuid?: string;
  upload_id?: string | null;
  text?: string | null;
}

export const mealsApi = {
  parse: (b: ParseRequest) => rest.post<{ job_id: string }>('/api/meals/parse', b),
  save: (b: SaveRequest) => rest.post<{ created: boolean; meal: Meal }>('/api/meals', b),
  day: (day: string) => rest.get<MealsDay>(`/api/meals?day=${q(day)}`),
  update: (id: number, b: { draft: MealDraft; day?: string; ts?: string | null }) => rest.put<Meal>(`/api/meals/${id}`, b),
  reparse: (id: number, b: { correction: string; notes?: string[] }) => rest.post<{ job_id: string }>(`/api/meals/${id}/reparse`, b),
  remove: (id: number) => rest.del<{ ok: boolean }>(`/api/meals/${id}`),
  water: (delta_ml: number, day?: string) => rest.post<{ day: string; water_l: number; water_ml: number }>('/api/water', { delta_ml, day }),
};
