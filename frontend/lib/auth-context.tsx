"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { publishAuthEvent, subscribeToAuthEvents } from "@/lib/auth-events";
import { api, ApiError, type User } from "@/lib/api";

export type AuthStatus =
  | "checking"
  | "authenticated"
  | "unauthenticated"
  | "refreshing"
  | "expired"
  | "unavailable";

interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  loading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function isUnavailable(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status >= 500;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("checking");
  const [error, setError] = useState<string | null>(null);
  const requestGeneration = useRef(0);

  const hydrate = useCallback(async (nextStatus: AuthStatus = "checking") => {
    const generation = ++requestGeneration.current;
    setStatus(nextStatus);
    setError(null);
    try {
      const session = await api.session();
      if (generation !== requestGeneration.current) return;
      setUser(session.user);
      setStatus("authenticated");
    } catch (caught) {
      if (generation !== requestGeneration.current) return;
      if (isUnavailable(caught)) {
        setStatus("unavailable");
        setError("FinSight could not verify your session. Your session has not been cleared.");
        return;
      }
      setUser((current) => {
        setStatus(current ? "expired" : "unauthenticated");
        return null;
      });
    }
  }, []);

  useEffect(() => {
    // Remove Phase 1 browser-readable credentials during the one-time migration.
    localStorage.removeItem("finsight_access");
    localStorage.removeItem("finsight_refresh");
    const hydrationTimer = window.setTimeout(() => void hydrate(), 0);

    const unsubscribe = subscribeToAuthEvents((event) => {
      if (event === "logout") {
        requestGeneration.current += 1;
        setUser(null);
        setError(null);
        setStatus("unauthenticated");
        return;
      }
      void hydrate(event === "session" ? "refreshing" : "checking");
    });
    return () => {
      window.clearTimeout(hydrationTimer);
      unsubscribe();
    };
  }, [hydrate]);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.login(email.trim().toLowerCase(), password);
    requestGeneration.current += 1;
    setUser(session.user);
    setError(null);
    setStatus("authenticated");
    publishAuthEvent("login");
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    const normalizedEmail = email.trim().toLowerCase();
    await api.register(normalizedEmail, password);
    const session = await api.login(normalizedEmail, password);
    requestGeneration.current += 1;
    setUser(session.user);
    setError(null);
    setStatus("authenticated");
    publishAuthEvent("login");
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    requestGeneration.current += 1;
    setUser(null);
    setError(null);
    setStatus("unauthenticated");
    publishAuthEvent("logout");
  }, []);

  const refreshUser = useCallback(async () => {
    await hydrate("refreshing");
  }, [hydrate]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      loading: status === "checking" || status === "refreshing",
      error,
      isAuthenticated: status === "authenticated" && user !== null,
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, status, error, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an <AuthProvider>");
  }
  return context;
}
