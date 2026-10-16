// Сериализация запросов соревнований и разбор ответа дедупа старта.
import type {
  Category, CompEventRow, CreateEventBody, CreateEventResponse, ParsedRow, ParsedStage,
} from '../../api/comps';

export const CATEGORIES: Category[] = ['newbie', 'pro', 'int', 'rx'];

/** «значение, место[, размер поля]» */
export interface TextResult {
  value: string;
  place: number;
  field_size: number | null;
}

const POS_INT = /^\d+$/;

/** Клиентская проверка строки результата; null — формат неверен. */
export function parseResultInput(text: string): TextResult | null {
  const parts = text.split(',').map((s) => s.trim());
  if (parts.length < 2 || parts.length > 3) return null;
  const [value, place, field] = parts;
  if (!value || !POS_INT.test(place) || +place < 1) return null;
  if (field !== undefined && (!POS_INT.test(field) || +field < 1)) return null;
  if (field !== undefined && +field < +place) return null;
  return { value, place: +place, field_size: field !== undefined ? +field : null };
}

export interface ResultTextForm {
  text: string;
  athlete?: string;
  stageIdx?: number | null;
  divisionId?: number | null;
}

/** Тело POST /events/{id}/results: пустые необязательные поля не отправляем. */
export function serializeResultText(f: ResultTextForm): Record<string, unknown> {
  const body: Record<string, unknown> = { text: f.text.trim() };
  const a = f.athlete?.trim();
  if (a && a !== 'Я') body.athlete = a;
  if (f.stageIdx != null && Number.isFinite(f.stageIdx)) body.stage_idx = f.stageIdx;
  if (f.divisionId != null) body.division_id = f.divisionId;
  return body;
}

/** Тело POST /results/confirm: строки без сопоставленного этапа отбрасываются, place/stage_id — числа. */
export function serializeConfirmResults(
  eventId: number,
  rows: ParsedRow[],
  opts: { athlete?: string; divisionId?: number | null } = {},
): Record<string, unknown> {
  const clean = rows
    .filter((r) => r.stage_id != null && r.value != null && String(r.value).trim() !== '')
    .map((r) => ({
      stage: r.stage,
      value: String(r.value).trim(),
      place: r.place == null || String(r.place) === '' ? null : Number(r.place),
      stage_id: Number(r.stage_id),
      stage_idx: r.stage_idx ?? null,
      stage_name: r.stage_name ?? null,
    }));
  const body: Record<string, unknown> = { event_id: eventId, rows: clean };
  const a = opts.athlete?.trim();
  if (a && a !== 'Я') body.athlete = a;
  if (opts.divisionId != null) body.division_id = opts.divisionId;
  return body;
}

export function serializeConfirmStages(
  eventId: number,
  stages: ParsedStage[],
  divisionId?: number | null,
): { event_id: number; stages: ParsedStage[]; division_id?: number } {
  const body: { event_id: number; stages: ParsedStage[]; division_id?: number } = {
    event_id: eventId,
    stages: stages.filter((s) => s.name.trim() !== '').map((s) => ({ ...s, name: s.name.trim(), prescription: (s.prescription ?? '').trim() })),
  };
  if (divisionId != null) body.division_id = divisionId;
  return body;
}

/** «12.04.2026», «12.04» или ISO — так же принимает сервер. */
export function validDateInput(s: string): boolean {
  const t = s.trim();
  return /^\d{1,2}\.\d{1,2}(\.\d{4})?$/.test(t) || /^\d{4}-\d{2}-\d{2}$/.test(t);
}

export interface CreateForm {
  name: string;
  date: string;
  city: string;
  category: Category | 'custom';
  division: string;
}

export function serializeCreateEvent(f: CreateForm, forceNew = false): CreateEventBody {
  const body: CreateEventBody = { name: f.name.trim(), date: f.date.trim(), city: f.city.trim() };
  if (f.category === 'custom') body.division = f.division.trim();
  else body.category = f.category;
  if (forceNew) body.force_new = true;
  return body;
}

export type DedupOutcome =
  | { kind: 'created'; eventId: number; divisionId: number }
  | { kind: 'duplicate'; candidates: CompEventRow[] };

/** Разбор ответа POST /api/comp/events: создан или дубль с кандидатами. */
export function parseCreateResponse(r: CreateEventResponse | Record<string, unknown>): DedupOutcome {
  const x = r as Record<string, unknown>;
  if (x.duplicate === true) {
    const cands = Array.isArray(x.candidates) ? (x.candidates as CompEventRow[]) : [];
    return { kind: 'duplicate', candidates: cands.map((c) => ({ ...c, divisions: c.divisions ?? [] })) };
  }
  return { kind: 'created', eventId: Number(x.event_id), divisionId: Number(x.division_id) };
}

/** Какой division_id передать при «присоединиться»: один дивизион — его; несколько — пусть выберет пользователь. */
export function joinDivisionChoice(c: CompEventRow): number | 'choose' | null {
  if (c.divisions.length === 0) return null;
  return c.divisions.length === 1 ? c.divisions[0].id : 'choose';
}
