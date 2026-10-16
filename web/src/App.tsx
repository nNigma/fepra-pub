import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { I18nProvider } from './i18n';
import { SessionProvider, useSession } from './lib/session';
import { Layout, Offline } from './components/Shell';
import { Loading } from './components/ui';
import { InviteScreen, LoginScreen } from './screens/Auth';
import { SummaryScreen } from './screens/Summary';
import { WorkoutDetailScreen, WorkoutsScreen } from './screens/Workouts';
import { NutritionDayScreen, NutritionScreen } from './screens/Nutrition';
import { CompetitionDetailScreen, CompetitionsScreen } from './screens/Competitions';
import { GoalsScreen } from './screens/Goals';
import { LeaderboardScreen } from './screens/Leaderboard';
import { MoreScreen, ProfileScreen } from './screens/Profile';
import { GarminScreen } from './screens/Garmin';
import { InvitesScreen } from './screens/Invites';
import { ProgramsRoutes } from './screens/programs';
import { RecordScreen } from './screens/record/RecordScreen';
import { WorkoutManageScreen } from './screens/record/WorkoutManage';
import { OnboardingGate } from './screens/onboarding/Onboarding';
import { ProfileSettingsScreen } from './screens/settings/ProfileSettings';
import { MealsScreen } from './screens/meals/Meals';
import { MealAddScreen } from './screens/meals/MealAdd';
import { MealEditScreen } from './screens/meals/MealEdit';
import { CompsScreen } from './screens/comps/Comps';
import { CompCreateScreen } from './screens/comps/CompCreate';
import { CompEventScreen } from './screens/comps/CompEvent';
import { CoachScreen } from './screens/coach/Coach';
import { ClubScreen } from './screens/club/Club';
import { ClubEditScreen } from './screens/club/ClubEdit';
import { ClubPendingScreen } from './screens/club/ClubPending';
import { ClubStatsScreen } from './screens/club/ClubStats';
import { AdminScreen } from './screens/admin/Admin';
import { AdminUsersScreen } from './screens/admin/AdminUsers';
import { AdminGymsScreen } from './screens/admin/AdminGyms';
import { AdminStatsScreen } from './screens/admin/AdminStats';

function Routed() {
  const { status, offline } = useSession();
  if (offline) return <Offline />;
  return (
    <Routes>
      <Route path="/invite/:token" element={<InviteScreen />} />
      {status === 'loading' ? (
        <Route path="*" element={<div className="wrap"><Loading /></div>} />
      ) : status === 'anon' ? (
        <Route path="*" element={<LoginScreen />} />
      ) : (
        <Route element={<OnboardingGate><Layout /></OnboardingGate>}>
          <Route index element={<SummaryScreen />} />
          <Route path="workouts" element={<WorkoutsScreen />} />
          <Route path="workouts/:day" element={<WorkoutDetailScreen />} />
          <Route path="record" element={<RecordScreen />} />
          <Route path="w/:id" element={<WorkoutManageScreen />} />
          <Route path="nutrition" element={<NutritionScreen />} />
          <Route path="nutrition/:day" element={<NutritionDayScreen />} />
          <Route path="competitions" element={<CompetitionsScreen />} />
          <Route path="competitions/:id" element={<CompetitionDetailScreen />} />
          <Route path="goals" element={<GoalsScreen />} />
          <Route path="leaderboard" element={<LeaderboardScreen />} />
          <Route path="programs/*" element={<ProgramsRoutes />} />
          <Route path="program" element={<Navigate to="/programs" replace />} />
          <Route path="garmin" element={<Navigate to="/profile/garmin" replace />} />
          <Route path="more" element={<MoreScreen />} />
          <Route path="profile" element={<ProfileScreen />} />
          <Route path="profile/garmin" element={<GarminScreen />} />
          <Route path="profile/invites" element={<InvitesScreen />} />
          <Route path="profile/settings" element={<ProfileSettingsScreen />} />
          <Route path="meals" element={<MealsScreen />} />
          <Route path="meals/new" element={<MealAddScreen />} />
          <Route path="meals/:id" element={<MealEditScreen />} />
          <Route path="comps" element={<CompsScreen />} />
          <Route path="comps/new" element={<CompCreateScreen />} />
          <Route path="comps/:id" element={<CompEventScreen />} />
          <Route path="coach" element={<CoachScreen />} />
          <Route path="club" element={<ClubScreen />} />
          <Route path="club/edit" element={<ClubEditScreen />} />
          <Route path="club/pending" element={<ClubPendingScreen />} />
          <Route path="club/stats" element={<ClubStatsScreen />} />
          <Route path="admin" element={<AdminScreen />} />
          <Route path="admin/users" element={<AdminUsersScreen />} />
          <Route path="admin/gyms" element={<AdminGymsScreen />} />
          <Route path="admin/stats" element={<AdminStatsScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      )}
    </Routes>
  );
}

export function App() {
  return (
    <I18nProvider>
      <SessionProvider>
        <HashRouter>
          <Routed />
        </HashRouter>
      </SessionProvider>
    </I18nProvider>
  );
}
