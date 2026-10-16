// Плитки раздела «Ещё»: видимость по ролям — чистая функция, чтобы тестировать без рендера.
import type { Me } from '../../api/types';
import { canManageClub, isAdmin, isPro } from '../../lib/roles';

export interface Tile {
  to: string;
  icon: string;
  key: string;
  show: (me: Me | null) => boolean;
}

export const TILES: Tile[] = [
  { to: '/competitions', icon: '🏆', key: 'tab.competitions', show: () => true },
  { to: '/comps', icon: '📝', key: 'more.comps', show: () => true },
  { to: '/leaderboard', icon: '🥇', key: 'tab.leaderboard', show: () => true },
  { to: '/meals', icon: '🍽', key: 'more.meals', show: isPro },
  { to: '/coach', icon: '🧠', key: 'more.coach', show: isPro },
  { to: '/club', icon: '🏟', key: 'more.club', show: () => true },
  { to: '/club/pending', icon: '📥', key: 'more.club_pending', show: canManageClub },
  { to: '/admin', icon: '🛠', key: 'more.admin', show: isAdmin },
  { to: '/profile', icon: '👤', key: 'tab.profile', show: () => true },
];

export const visibleTiles = (me: Me | null): Tile[] => TILES.filter((x) => x.show(me));
