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

import { resolveApiOrigin } from "@/lib/api-origin";

const API_URL = resolveApiOrigin();

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
  headers?: Record<string, string>;
  _retried?: boolean; // internal: prevents infinite refresh loops
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = false, headers: extraHeaders, _retried = false } = opts;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
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

async function authenticatedFetch(
  path: string,
  init: RequestInit,
  retried = false,
): Promise<Response> {
  const headers = new Headers(init.headers);
  const token = tokenStore.getAccess();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (response.status === 401 && !retried && tokenStore.getRefresh()) {
    const refreshed = await tryRefresh();
    if (refreshed) return authenticatedFetch(path, init, true);
  }
  return response;
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
  market_value: number | null;
  cost_basis: number;
  unrealized_pnl: number | null;
  return_percent: number | null;
  daily_pnl: number | null;
  weight_percent: number | null;
}

export interface PortfolioAnalytics {
  portfolio_id: number;
  name: string;
  total_value: number | null;
  total_cost: number;
  total_unrealized_pnl: number | null;
  total_return_percent: number | null;
  daily_pnl: number | null;
  daily_pnl_percent: number | null;
  number_of_holdings: number;
  number_of_sectors: number;
  top_holding_weight_percent: number | null;
  concentration_hhi: number | null;
  diversification_score: number | null;
  volatility_percent: number | null;
  health_score: number | null;
  risk_level: string;
  valuation_complete: boolean;
  unpriced_symbols: string[];
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

// ----- Market types (Phase 2 reads, surfaced in Phase 7) --------------------
export interface Quote {
  symbol: string;
  name: string | null;
  sector: string | null;
  date: string | null;
  close: number | null;
  previous_close: number | null;
  change: number | null;
  change_percent: number | null;
  volume: number | null;
}

export interface Breadth {
  advancers: number;
  decliners: number;
  unchanged: number;
  total: number;
  advance_decline_ratio: number | null;
}

export interface SectorOverview {
  sector: string;
  stock_count: number;
  average_change_percent: number | null;
}

export interface TechnicalSummary {
  as_of: string | null;
  stocks_with_indicators: number;
  average_rsi: number | null;
  bullish_rsi_count: number;
  overbought_count: number;
  oversold_count: number;
  above_ema20_count: number;
  above_ema50_count: number;
  positive_macd_count: number;
  average_atr_percent: number | null;
}

export interface EconomicEvent {
  event_id: string;
  date: string;
  country: string;
  category: string;
  name: string;
  importance: number;
  reference: string | null;
  source: string | null;
  source_url: string | null;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
}

export interface EconomicCalendar {
  provider: string;
  status: "ok" | "not_configured" | "unavailable";
  events: EconomicEvent[];
}

export const marketApi = {
  gainers: (limit = 5) => request<Quote[]>(`/api/v1/market/gainers?limit=${limit}`),
  losers: (limit = 5) => request<Quote[]>(`/api/v1/market/losers?limit=${limit}`),
  breadth: () => request<Breadth>("/api/v1/market/breadth"),
  sectors: () => request<SectorOverview[]>("/api/v1/market/sectors"),
  technicalSummary: () =>
    request<TechnicalSummary>("/api/v1/market/technical-summary"),
  economicEvents: (days = 14) =>
    request<EconomicCalendar>(`/api/v1/market/economic-events?days=${days}`),
};

// ----- Historical similarity types (Phase 4 reads) --------------------------
export interface SessionSummary {
  date: string;
  avg_return: number;
  pct_advancers: number;
  advance_decline_ratio: number;
  avg_rsi: number;
}

export interface SimilarSession extends SessionSummary {
  similarity_score: number;
  distance: number;
  next_day_return: number | null;
  outcome: string | null;
}

export interface HistoryStatistics {
  k: number;
  sample_size: number;
  bullish_count: number;
  bearish_count: number;
  neutral_count: number;
  bullish_probability: number | null;
  avg_next_day_return: number | null;
  median_next_day_return: number | null;
  std_next_day_return: number | null;
  best_case_return: number | null;
  worst_case_return: number | null;
  ci_low: number | null;
  ci_high: number | null;
}

export interface SimilarityResult {
  query_date: string;
  query_summary: SessionSummary;
  similar_sessions: SimilarSession[];
  statistics: HistoryStatistics;
}

export const historyApi = {
  similar: (k?: number) =>
    request<SimilarityResult>(`/api/v1/history/similar${k ? `?k=${k}` : ""}`),
};

// ----- Intelligence types (Phase 6 output) ----------------------------------
export interface GenerationUsage {
  prompt_tokens: number | null;
  candidate_tokens: number | null;
  total_tokens: number | null;
  cached_tokens: number | null;
  thoughts_tokens: number | null;
}

export interface GenerationMetadata {
  configured_backend: string;
  backend: string;
  requested_model: string | null;
  model_version: string | null;
  response_id: string | null;
  finish_reason: string | null;
  provider_created_at: string | null;
  attempt_count: number;
  provider_response_count: number;
  fallback_used: boolean;
  latency_ms: number;
  usage: GenerationUsage;
}

export interface GenerationSummary {
  schema_version: number;
  configured_backend: string;
  actual_backends: string[];
  requested_models: string[];
  model_versions: string[];
  generation_count: number;
  provider_attempt_count: number;
  provider_response_count: number;
  fallback_count: number;
  usage: GenerationUsage;
  items: (GenerationMetadata & { purpose: string })[];
}

export interface Recommendation {
  symbol: string;
  name: string | null;
  sector: string | null;
  action: string;
  confidence: number;
  score: number;
  evidence: string[];
  risks: string[];
  historical_context: {
    bullish_probability: number | null;
    sample_size: number | null;
  };
  explanation: string;
}

export interface Recommendations {
  watchlist: Recommendation[];
  risk_alerts: Recommendation[];
  generation: GenerationSummary;
}

export const intelligenceApi = {
  recommendations: () =>
    request<Recommendations>("/api/v1/recommendations", { auth: true }),
};

// ----- Dashboard summary (Phase 7 — batched home screen) --------------------
export interface DashboardSummary {
  market: { breadth: Breadth; gainers: Quote[]; losers: Quote[] };
  ai_market_summary: string;
  portfolio: PortfolioAnalytics | null;
  watchlist: WatchlistItem[];
  opportunities: Recommendation[];
  risk_alerts: Recommendation[];
  history: SimilarityResult | null;
  generation: GenerationSummary;
}

export const dashboardApi = {
  summary: () => request<DashboardSummary>("/api/v1/dashboard/summary", { auth: true }),
};

// ----- Reports (Phase 8) ----------------------------------------------------
export interface ReportSummary {
  id: number;
  report_type: string;
  created_at: string;
}

export interface ReportSections {
  executive_summary?: string;
  market_summary?: {
    narrative?: string;
    breadth?: Breadth;
    gainers?: Quote[];
    losers?: Quote[];
  };
  portfolio_summary?: {
    narrative?: string;
    total_value?: number | null;
    total_cost?: number;
    total_return_percent?: number | null;
    health_score?: number | null;
    risk_level?: string;
    diversification_score?: number | null;
    number_of_holdings?: number;
    valuation_complete?: boolean;
    unpriced_symbols?: string[];
  };
  historical_summary?: {
    narrative?: string;
    statistics?: HistoryStatistics;
  };
  recommendations?: Recommendation[];
  risk_alerts?: Recommendation[];
  news?: { notable?: { title: string; sentiment_label?: string; tags?: string[] }[] };
  meta?: {
    prompt_version?: string;
    llm_backend?: string;
    generated_at?: string;
    generation?: GenerationSummary;
  };
}

export interface Report {
  id: number;
  user_id: number | null;
  report_type: string;
  sections: ReportSections;
  created_at: string;
}

export interface ReportFilters {
  report_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}

export const reportsApi = {
  list: (f: ReportFilters = {}) => {
    const p = new URLSearchParams();
    if (f.report_type) p.set("report_type", f.report_type);
    if (f.start_date) p.set("start_date", f.start_date);
    if (f.end_date) p.set("end_date", f.end_date);
    if (f.limit != null) p.set("limit", String(f.limit));
    if (f.offset != null) p.set("offset", String(f.offset));
    const qs = p.toString();
    return request<ReportSummary[]>(`/api/v1/reports${qs ? `?${qs}` : ""}`, { auth: true });
  },
  get: (id: number) => request<Report>(`/api/v1/reports/${id}`, { auth: true }),
  generate: () =>
    request<Report>("/api/v1/reports/generate", {
      method: "POST",
      auth: true,
      headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
};

// ----- AI Chat (Phase 9) ---------------------------------------------------
export interface ChatSource {
  kind: "portfolio" | "watchlist" | "market" | "history" | "news";
  label: string;
  reference: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  evidence: string[];
  confidence: number | null;
  sources: ChatSource[];
  risks: string[];
  generation?: GenerationMetadata | null;
}

export interface ChatStreamHandlers {
  onUser: (message: ChatMessage) => void;
  onChunk: (delta: string) => void;
  onComplete: (message: ChatMessage) => void;
}

interface ChatStreamEvent {
  event: string;
  data: Record<string, unknown>;
}

function parseSseBlock(block: string): ChatStreamEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    if (line.startsWith("data: ")) data.push(line.slice(6));
  }
  if (data.length === 0) return null;
  return { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
}

function userStreamMessage(value: unknown): ChatMessage {
  const message = value as Pick<ChatMessage, "id" | "role" | "content" | "created_at">;
  return { ...message, evidence: [], confidence: null, sources: [], risks: [] };
}

export const chatApi = {
  history: (limit = 100) =>
    request<ChatMessage[]>(`/api/v1/chat/history?limit=${limit}`, { auth: true }),

  clear: () =>
    request<{ deleted: number }>("/api/v1/chat/history", {
      method: "DELETE",
      auth: true,
    }),

  stream: async (
    message: string,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
  ): Promise<void> => {
    const response = await authenticatedFetch("/api/v1/chat?stream=true", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });
    if (!response.ok) {
      await parse<never>(response);
      return;
    }
    if (!response.body) {
      throw new ApiError("Chat stream was unavailable.", response.status);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completed = false;

    function dispatch(parsed: ChatStreamEvent | null) {
      if (parsed?.event === "meta") {
        handlers.onUser(userStreamMessage(parsed.data.user));
      } else if (parsed?.event === "chunk") {
        handlers.onChunk(String(parsed.data.delta ?? ""));
      } else if (parsed?.event === "complete") {
        handlers.onComplete(parsed.data.assistant as ChatMessage);
        completed = true;
      }
    }

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done }).replaceAll("\r\n", "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary >= 0) {
        const parsed = parseSseBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        dispatch(parsed);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }
    if (buffer.trim()) dispatch(parseSseBlock(buffer.trim()));
    if (!completed) throw new ApiError("Chat stream ended before completion.", 502);
  },
};

/**
 * Download a report export (Markdown or PDF). The export endpoint returns a
 * binary file (not the JSON envelope), so this bypasses `request()` and streams
 * the blob with the Bearer token, then triggers a browser download.
 */
export async function downloadReport(id: number, fmt: "markdown" | "pdf"): Promise<void> {
  const token = tokenStore.getAccess();
  const res = await fetch(`${API_URL}/api/v1/reports/${id}/export?format=${fmt}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    cache: "no-store",
  });
  if (!res.ok) {
    throw new ApiError(`Export failed (${res.status})`, res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `finsight-report-${id}.${fmt === "pdf" ? "pdf" : "md"}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
