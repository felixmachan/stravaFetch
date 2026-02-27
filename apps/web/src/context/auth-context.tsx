import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, clearTokens, getAccessToken, setTokens } from '../lib/api';

type User = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
};

type AuthContextValue = {
  user: User | null;
  stravaConnected: boolean;
  loading: boolean;
  isAuthenticated: boolean;
  login: (payload: { usernameOrEmail: string; password: string }) => Promise<void>;
  register: (payload: Record<string, unknown>) => Promise<void>;
  loginAsAdmin: () => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [stravaConnected, setStravaConnected] = useState(false);
  const [loading, setLoading] = useState(true);
  const qc = useQueryClient();

  const refreshMe = async () => {
    if (!getAccessToken()) {
      setUser(null);
      setStravaConnected(false);
      return;
    }
    const res = await api.get('/auth/me');
    setUser(res.data.user);
    setStravaConnected(Boolean(res.data.strava_connected));
  };

  useEffect(() => {
    refreshMe().catch(() => {
      clearTokens();
      setUser(null);
      setStravaConnected(false);
    }).finally(() => setLoading(false));
  }, []);

  const loginAsAdmin = async () => {
    const res = await api.post('/auth/dev-login');
    setTokens(res.data.tokens);
    await refreshMe();
    qc.invalidateQueries();
  };

  const login = async (payload: { usernameOrEmail: string; password: string }) => {
    const raw = payload.usernameOrEmail.trim();
    const body = raw.includes('@')
      ? { email: raw, password: payload.password }
      : { username: raw, password: payload.password };
    const res = await api.post('/auth/login', body);
    setTokens(res.data.tokens);
    await refreshMe();
    qc.invalidateQueries();
  };

  const register = async (payload: Record<string, unknown>) => {
    const res = await api.post('/auth/register', payload);
    setTokens(res.data.tokens);
    await refreshMe();
    qc.invalidateQueries();
  };

  const logout = async () => {
    clearTokens();
    setUser(null);
    setStravaConnected(false);
    qc.clear();
  };

  const value = useMemo(
    () => ({
      user,
      stravaConnected,
      loading,
      isAuthenticated: Boolean(user),
      login,
      register,
      loginAsAdmin,
      logout,
      refreshMe,
    }),
    [user, stravaConnected, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
