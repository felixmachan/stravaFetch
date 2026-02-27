import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/app-shell';
import { useAuth } from './context/auth-context';
import { ActivitiesPage } from './pages/activities-page';
import { ActivityDetailPage } from './pages/activity-detail-page';
import { DashboardPage } from './pages/dashboard-page';
import { LoginPage } from './pages/login-page';
import { PlanPage } from './pages/plan-page';
import { PlanWorkoutPage } from './pages/plan-workout-page';
import { ProfilePage } from './pages/profile-page';
import { AiPage } from './pages/ai-page';
import { SettingsPage } from './pages/settings-page';

function PrivateRoutes() {
  const { isAuthenticated, loading } = useAuth();
  if (loading) return null;
  if (!isAuthenticated) return <Navigate to='/login' replace />;

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path='/' element={<DashboardPage />} />
        <Route path='/activities' element={<ActivitiesPage />} />
        <Route path='/activities/:id' element={<ActivityDetailPage />} />
        <Route path='/integrations' element={<Navigate to='/settings' replace />} />
        <Route path='/plan' element={<PlanPage />} />
        <Route path='/plan/workouts/:date/:idx' element={<PlanWorkoutPage />} />
        <Route path='/ai' element={<AiPage />} />
        <Route path='/profile' element={<ProfilePage />} />
        <Route path='/settings' element={<SettingsPage />} />
      </Route>
      <Route path='*' element={<Navigate to='/' replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path='/login' element={<LoginPage />} />
      <Route path='/*' element={<PrivateRoutes />} />
    </Routes>
  );
}
