// Удалённые за эту сессию тренировки: дают кнопку «Отменить» (POST …/restore) после ухода с экрана.
export interface TrashItem {
  id: string;
  day: string;
  sport: string;
}
const KEY = 'fepra.record.trash';

function read(): TrashItem[] {
  try {
    const v = JSON.parse(sessionStorage.getItem(KEY) ?? '[]');
    return Array.isArray(v) ? (v as TrashItem[]) : [];
  } catch {
    return [];
  }
}
function write(list: TrashItem[]) {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(list.slice(0, 20)));
  } catch {
    /* ignore */
  }
}
export const trashList = (): TrashItem[] => read();
export function trashAdd(it: TrashItem): void {
  write([it, ...read().filter((x) => x.id !== it.id)]);
}
export function trashRemove(id: string): void {
  write(read().filter((x) => x.id !== id));
}
