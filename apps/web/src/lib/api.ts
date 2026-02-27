import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';
const ACCESS_KEY = 'pacepilot.access';
const REFRESH_KEY = 'pacepilot.refresh';

let accessToken = localStorage.getItem(ACCESS_KEY) || '';
let refreshToken = localStorage.getItem(REFRESH_KEY) || '';
let refreshing: Promise<string | null> | null = null;

function emitToast(title: string, message: string) {
  window.dispatchEvent(new CustomEvent('app:toast', { detail: { title, message } }));
}

export function getAccessToken() {
  return accessToken;
}

export function getRefreshToken() {
  return refreshToken;
}

export function setTokens(tokens: { access: string; refresh?: string }) {
  accessToken = tokens.access;
  localStorage.setItem(ACCESS_KEY, tokens.access);
  if (tokens.refresh) {
    refreshToken = tokens.refresh;
    localStorage.setItem(REFRESH_KEY, tokens.refresh);
  }
}

export function clearTokens() {
  accessToken = '';
  refreshToken = '';
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

const rawClient = axios.create({ baseURL: API_BASE_URL });

export const api = axios.create({
  baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

async function refreshAccessToken() {
  if (!refreshToken) return null;
  if (!refreshing) {
    refreshing = rawClient
      .post('/auth/refresh', { refresh: refreshToken })
      .then((res) => {
        const next = res.data?.access as string;
        if (next) {
          setTokens({ access: next });
          return next;
        }
        return null;
      })
      .catch(() => {
        clearTokens();
        return null;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    const status = error.response?.status;

    if (status === 401 && !original?._retry && getRefreshToken()) {
      original._retry = true;
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        original.headers.Authorization = `Bearer ${refreshed}`;
        return api(original);
      }
    }

    const suppressToast = Boolean(original?.suppressToast);
    if (!suppressToast) {
      const message = error.response?.data?.detail || 'Request failed.';
      emitToast('Request failed', typeof message === 'string' ? message : 'Please try again.');
    }
    return Promise.reject(error);
  }
);
