"use client";

/**
 * Client-side auth state.
 *
 * Wraps the app in an <AuthProvider>. On mount it hydrates the current user
 * from the stored access token (refreshing once if needed). Exposes login,
 * register, and logout, plus the current user and loading state used for route
 * protection.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { api, tokenStore, type User } from "@/lib/api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

async function readStoredUser(): Promise<User | null> {
  if (!tokenStore.getAccess()) return null;
  try {
    return await api.me();
  } catch {
    tokenStore.clear();
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadUser = useCallback(async () => {
    setUser(await readStoredUser());
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function hydrateUser() {
      const storedUser = await readStoredUser();
      if (cancelled) return;
      setUser(storedUser);
      setLoading(false);
    }

    void hydrateUser();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    tokenStore.set(tokens);
    setUser(await api.me());
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      // Register then immediately log in for a smooth first-run experience.
      await api.register(email, password);
      const tokens = await api.login(email, password);
      tokenStore.set(tokens);
      setUser(await api.me());
    },
    [],
  );

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      isAuthenticated: user !== null,
      login,
      register,
      logout,
      refreshUser: loadUser,
    }),
    [user, loading, login, register, logout, loadUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === undefined) {
    throw new Error("useAuth must be used within an <AuthProvider>");
  }
  return ctx;
}
