import { rest } from './rest';
import type { Lang } from './types';

export interface WatchState {
  garmin: { status: string } | null;
  samsung: boolean;
  whoop: boolean;
  apple: boolean;
}

export interface Profile {
  id: number;
  nick: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  sex: 'm' | 'f' | null;
  age: number | null;
  gym: string | null;
  extra_gyms?: string[];
  level?: string | null;
  lang: Lang;
  goal: string;
  city: string;
  astro: boolean;
  watch: WatchState;
  available_watch_actions: string[];
}

export type ProfilePatch = Partial<{
  nick: string; height_cm: number; weight_kg: number; sex: 'm' | 'f'; age: number;
  gym: string; extra_gyms: string[]; lang: Lang; goal: string; city: string; astro: boolean;
}>;

export interface OnboardingStatus {
  complete: boolean;
  missing: string[];
  optional_missing: string[];
  ranges: { height_cm: [number, number]; age: [number, number]; weight_kg: [number, number] };
}

export interface GymList {
  gyms: { name: string; is_default: boolean; members: number }[];
  special: string[];
}

export const profileApi = {
  profile: () => rest.get<Profile>('/api/profile'),
  patch: (body: ProfilePatch) => rest.patch<Profile>('/api/profile', body),
  onboarding: () => rest.get<OnboardingStatus>('/api/onboarding'),
  gyms: () => rest.get<GymList>('/api/gyms'),
};
