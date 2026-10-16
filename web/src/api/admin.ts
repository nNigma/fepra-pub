import { rest, q } from './rest';

export interface AdminRoles {
  allowlist: boolean;
  pro: boolean;
  admin: boolean;
  coach: boolean;
  coach_gym: string | null;
  /** все залы тренера (основной первым) */
  coach_gyms: string[];
}
export interface AdminUser {
  id: number;
  nick: string | null;
  gym: string | null;
  created_at: string | null;
  roles: AdminRoles;
}
export interface AdminGym {
  name: string;
  is_default: boolean;
  members: number;
  coaches: { id: number; nick: string | null }[];
}
export interface AdminCoach {
  id: number;
  nick: string | null;
  gym: string | null;
  gyms: string[];
}
export interface AdminStats {
  days: number | null;
  since: string | null;
  total: number;
  users: { id: number; nick: string | null; total: number; actions: { key: string; label: string; n: number }[] }[];
}
export type RolesPatch = Partial<{ allowlist: boolean; pro: boolean; admin: boolean; coach: string | string[] | null }>;

export const adminApi = {
  users: (query?: string) => rest.get<AdminUser[]>(`/api/admin/users${query ? '?q=' + q(query) : ''}`),
  setRoles: (id: number, b: RolesPatch) => rest.put<{ id: number; roles: AdminRoles }>(`/api/admin/users/${id}/roles`, b),
  removeUser: (id: number) => rest.del<{ ok: boolean }>(`/api/admin/users/${id}`),
  gyms: () => rest.get<AdminGym[]>('/api/admin/gyms'),
  addGym: (name: string) => rest.post<AdminGym>('/api/admin/gyms', { name }),
  coaches: () => rest.get<AdminCoach[]>('/api/admin/coaches'),
  assignCoach: (user_id: number, gym: string) => rest.post<AdminCoach>('/api/admin/coaches', { user_id, gym }),
  /** gym: снять тренера только из этого зала; без него — совсем */
  revokeCoach: (id: number, gym?: string) => rest.del<{ ok: boolean }>(`/api/admin/coaches/${id}${gym ? '?gym=' + q(gym) : ''}`),
  stats: (days: number) => rest.get<AdminStats>(`/api/admin/stats?days=${days}`),
  review: () => rest.post<{ job_id: string; already_running: boolean }>('/api/admin/review'),
};
