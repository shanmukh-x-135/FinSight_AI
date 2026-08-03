/**
 * Typed API client for the FinSight backend.
 *
 * Responsibilities:
 *  - prepend the API base URL and JSON headers
 *  - attach the Bearer access token from localStorage
 *  - unwrap the standard response envelope ({ success, data, message, error })
 *  - transparently refresh the access token once on a 401, then retry
 *
 * Token storage decision (Phase 1): access + refresh tokens live in
 * localStorage and are sent as a Bearer header. This is one consistent
 * approach across the app. Trade-off: susceptible to XSS; a future hardening
 * is httpOnly cookies (documented in docs/auth.md).
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const ACCESS_KEY = "finsight_access";
const REFRESH_KEY = "finsight_refresh";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Preferences {
  risk_tolerance: string;
  investment_horizon: string;
  preferred_market: string;
  preferred_sectors: string[];
}

export interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  preferences: Preferences;
}

export class ApiError extends Error {
  status: number;
  type: string;
  constructor(message: string, status: number, type = "error") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.type = type;
  }
}

// ----- Token storage --------------------------------------------------------
export const tokenStore = {
  getAccess: (): string | null =>
    typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY),
  getRefresh: (): string | null =>
    typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY),
  set: (tokens: TokenPair): void => {
    localStorage.setItem(ACCESS_KEY, tokens.access_token);
    localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  },
  clear: (): void => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

interface Envelope<T> {
  success: boolean;
  message: string;
  data: T;
  error?: { type: string; detail?: unknown };
}

async function parse<T>(res: Response): Promise<T> {
  const body = (await res.json().catch(() => ({}))) as Envelope<T>;
  if (!res.ok || body.success === false) {
    throw new ApiError(
      body.message || `Request failed (${res.status})`,
      res.status,
      body.error?.type ?? "error",
    );
  }
  return body.data;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  auth?: boolean; // attach access token
  _retried?: boolean; // internal: prevents infinite refresh loops
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = false, _retried = false } = opts;

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const token = tokenStore.getAccess();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  // On an expired/invalid access token, try one refresh + retry.
  if (res.status === 401 && auth && !_retried && tokenStore.getRefresh()) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      return request<T>(path, { ...opts, _retried: true });
    }
  }

  return parse<T>(res);
}

async function tryRefresh(): Promise<boolean> {
  const refresh_token = tokenStore.getRefresh();
  if (!refresh_token) return false;
  try {
    const tokens = await request<TokenPair>("/api/v1/auth/refresh", {
      method: "POST",
      body: { refresh_token },
    });
    tokenStore.set(tokens);
    return true;
  } catch {
    tokenStore.clear();
    return false;
  }
}

// ----- Endpoints ------------------------------------------------------------
export const api = {
  register: (email: string, password: string) =>
    request<User>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),

  login: (email: string, password: string) =>
    request<TokenPair>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  me: () => request<User>("/api/v1/user/me", { auth: true }),

  getPreferences: () =>
    request<Preferences>("/api/v1/user/preferences", { auth: true }),

  updatePreferences: (changes: Partial<Preferences>) =>
    request<Preferences>("/api/v1/user/preferences", {
      method: "PUT",
      body: changes,
      auth: true,
    }),
};

// ----- Portfolio & Watchlist types -----------------------------------------
export interface PortfolioSummary {
  id: number;
  name: string;
  created_at: string;
  holding_count: number;
}

export interface HoldingRaw {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  quantity: number;
  avg_buy_price: number;
}

export interface PortfolioDetail {
  id: number;
  name: string;
  created_at: string;
  holdings: HoldingRaw[];
}

export interface SectorAllocation {
  sector: string;
  value: number;
  weight_percent: number;
}

export interface HoldingAnalytics {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  quantity: number;
  avg_buy_price: number;
  current_price: number | null;
  previous_close: number | null;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  return_percent: number | null;
  daily_pnl: number;
  weight_percent: number;
}

export interface PortfolioAnalytics {
  portfolio_id: number;
  name: string;
  total_value: number;
  total_cost: number;
  total_unrealized_pnl: number;
  total_return_percent: number | null;
  daily_pnl: number;
  daily_pnl_percent: number | null;
  number_of_holdings: number;
  number_of_sectors: number;
  top_holding_weight_percent: number;
  concentration_hhi: number;
  diversification_score: number;
  volatility_percent: number | null;
  health_score: number;
  risk_level: string;
  sector_allocation: SectorAllocation[];
  holdings: HoldingAnalytics[];
}

export interface WatchlistItem {
  id: number;
  symbol: string;
  name: string | null;
  sector: string | null;
  current_price: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  pinned: boolean;
  sort_order: number;
}

export const portfolioApi = {
  list: () => request<PortfolioSummary[]>("/api/v1/portfolios", { auth: true }),
  create: (name: string) =>
    request<PortfolioSummary>("/api/v1/portfolios", {
      method: "POST",
      body: { name },
      auth: true,
    }),
  detail: (id: number) =>
    request<PortfolioDetail>(`/api/v1/portfolios/${id}`, { auth: true }),
  remove: (id: number) =>
    request<null>(`/api/v1/portfolios/${id}`, { method: "DELETE", auth: true }),
  analytics: (id: number) =>
    request<PortfolioAnalytics>(`/api/v1/portfolios/${id}/analytics`, { auth: true }),
  addHolding: (id: number, body: { symbol: string; quantity: number; avg_buy_price: number }) =>
    request<{ id: number }>(`/api/v1/portfolios/${id}/items`, {
      method: "POST",
      body,
      auth: true,
    }),
  updateHolding: (
    id: number,
    itemId: number,
    body: { quantity?: number; avg_buy_price?: number },
  ) =>
    request<{ id: number }>(`/api/v1/portfolios/${id}/items/${itemId}`, {
      method: "PUT",
      body,
      auth: true,
    }),
  removeHolding: (id: number, itemId: number) =>
    request<null>(`/api/v1/portfolios/${id}/items/${itemId}`, {
      method: "DELETE",
      auth: true,
    }),
};

export const watchlistApi = {
  list: () => request<WatchlistItem[]>("/api/v1/watchlist", { auth: true }),
  add: (symbol: string) =>
    request<{ id: number }>("/api/v1/watchlist", {
      method: "POST",
      body: { symbol },
      auth: true,
    }),
  update: (id: number, body: { pinned?: boolean; sort_order?: number }) =>
    request<{ id: number }>(`/api/v1/watchlist/${id}`, {
      method: "PATCH",
      body,
      auth: true,
    }),
  remove: (id: number) =>
    request<null>(`/api/v1/watchlist/${id}`, { method: "DELETE", auth: true }),
};
