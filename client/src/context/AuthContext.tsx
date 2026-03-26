import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import axios from 'axios';
import { useTravelStore } from '../store/useTravelStore';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface AuthUser {
  uid: string;
  email: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  googleLogin: (idToken: string) => Promise<void>;
  logout: () => void;
  getToken: () => Promise<string>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'trippy_id_token';
const REFRESH_KEY = 'trippy_refresh_token';
const USER_KEY = 'trippy_user';

function saveSession(idToken: string, refreshToken: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, idToken);
  localStorage.setItem(REFRESH_KEY, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

function loadUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

/** Fetch saved preferences from MongoDB and hydrate the Zustand store. */
async function fetchAndApplyPreferences(token: string) {
  try {
    const res = await axios.get(`${API_BASE}/api/users/preferences`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.data.found && res.data.data) {
      const d = res.data.data;
      const store = useTravelStore.getState();
      if (d.user_profile) {
        store.setUserProfile({
          name: d.user_profile.name ?? '',
          age: d.user_profile.age ?? '',
        });
      }
      if (d.preferences) {
        store.setPreferences({ ...store.preferences, ...d.preferences });
      }
    }
  } catch {
    // First-time user or network hiccup — ignore
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(loadUser);
  const [loading, setLoading] = useState(() => !!localStorage.getItem(TOKEN_KEY));

  // On mount (page refresh): if we have a stored token, fetch preferences
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && user) {
      fetchAndApplyPreferences(token).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** Process a successful auth response from the backend */
  const handleAuthResponse = useCallback(async (data: { id_token: string; refresh_token: string; uid: string; email: string }) => {
    const u: AuthUser = { uid: data.uid, email: data.email };
    saveSession(data.id_token, data.refresh_token, u);
    setUser(u);
    // Eagerly load preferences right after login/signup
    await fetchAndApplyPreferences(data.id_token);
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const { data } = await axios.post(`${API_BASE}/api/auth/signup`, { email, password });
    await handleAuthResponse(data);
  }, [handleAuthResponse]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await axios.post(`${API_BASE}/api/auth/login`, { email, password });
    await handleAuthResponse(data);
  }, [handleAuthResponse]);

  const googleLogin = useCallback(async (idToken: string) => {
    const { data } = await axios.post(`${API_BASE}/api/auth/google`, { id_token: idToken });
    await handleAuthResponse(data);
  }, [handleAuthResponse]);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
  }, []);

  const getToken = useCallback(async (): Promise<string> => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) throw new Error('Not authenticated');
    return token;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, googleLogin, logout, getToken }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
