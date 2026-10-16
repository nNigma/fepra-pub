import type { AdminUser, RolesPatch } from '../../api/admin';

/** Что предупредить перед изменением ролей (сервер ещё и вернёт 409 — здесь только подсказка заранее). */
export type RoleWarning = 'last_admin' | 'self_admin' | 'drop_allowlist_admin' | 'remove_admin' | null;

/** блокирующие предупреждения: сервер ответил бы 409, запрос не шлём */
export const isBlocking = (w: RoleWarning): boolean => w === 'last_admin' || w === 'drop_allowlist_admin' || w === 'remove_admin';

export function roleWarning(users: AdminUser[], target: AdminUser, patch: RolesPatch, selfId?: number): RoleWarning {
  const admins = users.filter((u) => u.roles.admin);
  if (patch.admin === false && target.roles.admin) {
    if (admins.length <= 1) return 'last_admin';
    if (target.id === selfId) return 'self_admin';
  }
  if (patch.allowlist === false && target.roles.admin) return 'drop_allowlist_admin';
  return null;
}

export function removeWarning(users: AdminUser[], target: AdminUser): RoleWarning {
  if (!target.roles.admin) return null;
  return users.filter((u) => u.roles.admin).length <= 1 ? 'last_admin' : 'remove_admin';
}

/** Ответ PUT roles -> обновлённый список */
export function applyRoles(users: AdminUser[], id: number, roles: AdminUser['roles']): AdminUser[] {
  return users.map((u) => (u.id === id ? { ...u, roles } : u));
}
