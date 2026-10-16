// Права для показа управления. Сервер всё равно проверяет сам; это только про то, что рисовать.
import type { Me } from '../api/types';

type MaybeMe = Pick<Me, 'roles'> | null | undefined;

export const isAdmin = (me: MaybeMe): boolean => !!me?.roles?.admin;
export const isPro = (me: MaybeMe): boolean => !!(me?.roles?.pro || me?.roles?.admin);
/** управлять программой зала: админ или тренер */
export const canManageClub = (me: MaybeMe): boolean => !!(me?.roles?.admin || me?.roles?.coach);
