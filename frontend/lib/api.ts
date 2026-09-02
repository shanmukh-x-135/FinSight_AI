/**
 * Typed API client for the FinSight backend.
 *
 * Responsibilities:
 *  - prepend the API base URL and JSON headers
 *  - send backend-owned HttpOnly session cookies through the same-origin proxy
 *  - unwrap the standard response envelope ({ success, data, message, error })
 *  - transparently refresh the access token once on a 401, then retry
 *
 * Browser JavaScript never receives bearer credentials. A session-bound CSRF
 * token is held in memory and is rehydrated from the backend after reload.
 */

import { publishAuthEvent } from "@/lib/auth-events";
import { BROWSER_API_BASE } from "@/lib/api-origin";

const API_URL = BROWSER_API_BASE;

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
  is_admin?: boolean;
  created_at: string;
  preferences: Preferences;
}

export interface SessionData {
  user: User;
  csrf_token: string;
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

let csrfToken: string | null = null;
let refreshPromise: Promise<boolean> | null = null;

function acceptSession(session: SessionData): SessionData {
  csrfToken = session.csrf_token;
  return session;
}

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
  auth?: boolean;
  headers?: Record<string, string>;
  _retried?: boolean; // internal: prevents infinite refresh loops
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, auth = false, headers: extraHeaders, _retried = false } = opts;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  if (auth && method !== "GET" && method !== "HEAD" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }

  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
    credentials: "include",
  });

  // On an expired/invalid access token, try one refresh + retry.
  if (res.status === 401 && auth && !_retried) {
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
  const method = (init.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD" && csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "include",
  });
  if (response.status === 401 && !retried) {
    const refreshed = await tryRefresh();
    if (refreshed) return authenticatedFetch(path, init, true);
  }
  return response;
}

async function tryRefresh(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = performRefresh().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

async function performRefresh(): Promise<boolean> {
  try {
    if (!csrfToken) {
      const csrfResponse = await fetch(`${API_URL}/api/v1/auth/csrf`, {
        cache: "no-store",
        credentials: "include",
      });
      if (!csrfResponse.ok) return false;
      csrfToken = (await parse<{ csrf_token: string }>(csrfResponse)).csrf_token;
    }
    const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
      cache: "no-store",
      credentials: "include",
    });
    if (response.ok) {
      acceptSession(await parse<SessionData>(response));
      publishAuthEvent("session");
      return true;
    }

    // Another tab may have won refresh-token rotation. Its new access cookie is
    // shared, so converge on that authoritative session before declaring expiry.
    if (response.status === 401) {
      const sessionResponse = await fetch(`${API_URL}/api/v1/auth/session`, {
        cache: "no-store",
        credentials: "include",
      });
      if (sessionResponse.ok) {
        acceptSession(await parse<SessionData>(sessionResponse));
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

// ----- Endpoints ------------------------------------------------------------
export const api = {
  googleStartUrl: (returnTo = "/dashboard") =>
    `${API_URL}/api/v1/auth/google/start?${new URLSearchParams({ return_to: returnTo })}`,

  register: (email: string, password: string) =>
    request<User>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),

  forgotPassword: (email: string) =>
    request<null>("/api/v1/auth/password/forgot", {
      method: "POST",
      body: { email },
    }),

  resetPassword: (token: string, password: string) =>
    request<null>("/api/v1/auth/password/reset", {
      method: "POST",
      body: { token, password },
    }),

  login: async (email: string, password: string) =>
    acceptSession(await request<SessionData>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    })),

  session: async () =>
    acceptSession(await request<SessionData>("/api/v1/auth/session", { auth: true })),

  logout: async () => {
    await request<null>("/api/v1/auth/logout", { method: "POST", auth: true });
    csrfToken = null;
  },

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

export interface CorrelationCell { symbol_x: string; symbol_y: string; correlation: number | null; observations: number }
export interface HoldingRiskContribution { symbol: string; weight_percent: number; return_contribution_percent: number | null; risk_contribution_percent: number | null; momentum_20d_percent: number | null }
export interface SectorDeviation { sector: string; portfolio_weight_percent: number; benchmark_weight_percent: number; deviation_percent: number }
export interface RegimeSensitivity { regime: string; sessions: number; average_daily_return_percent: number; positive_session_percent: number }
export interface StressScenario { code: string; label: string; shock: string; estimated_impact_percent: number | null; estimated_value_change: number | null; methodology: string; is_prediction: false }
export interface PortfolioRisk { portfolio_id: number; as_of: string | null; methodology: string; benchmark_symbol: string; observations: number; minimum_observations: number; data_complete: boolean; missing_symbols: string[]; annualized_volatility_percent: number | null; beta: number | null; sharpe_ratio: number | null; max_drawdown_percent: number | null; concentration_hhi: number | null; momentum_exposure_percent: number | null; correlation: CorrelationCell[]; holding_contributions: HoldingRiskContribution[]; sector_deviation: SectorDeviation[]; sector_benchmark_methodology: string; regime_sensitivity: RegimeSensitivity[]; stress_scenarios: StressScenario[] }
export interface PortfolioCounterfactual { label: string; changes: { symbol: string; quantity_delta: number }[]; before: PortfolioRisk; after: PortfolioRisk; deltas: Record<string, number | null> }

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
  rsi_14?: number | null;
  trend?: string | null;
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
  risk: (id: number) =>
    request<PortfolioRisk>(`/api/v1/portfolios/${id}/risk`, { auth: true }),
  counterfactual: (id: number, changes: { symbol: string; quantity_delta: number }[]) =>
    request<PortfolioCounterfactual>(`/api/v1/portfolios/${id}/counterfactual`, { method: "POST", body: { changes }, auth: true }),
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

export interface MarketStockSnapshot extends Quote {
  rsi_14: number | null;
  ema_20: number | null;
  ema_50: number | null;
  macd_histogram: number | null;
  trend: string | null;
}

export type UniverseCode = "NIFTY50" | "NIFTYNEXT50" | "NIFTY100";

export interface UniverseOption {
  code: UniverseCode;
  label: string;
  expected_constituents: number;
  active_constituents: number;
  initialized: boolean;
  preferred: boolean;
  source_url: string;
}

export interface HeatmapStock {
  symbol: string;
  name: string | null;
  sector: string;
  as_of: string | null;
  change_percent: number | null;
  market_cap: number | null;
  sentiment: number | null;
  sentiment_availability: "available" | "no_relevant_news";
  rsi_14: number | null;
  signal: string | null;
}

export interface SectorRotation {
  sector: string;
  stock_count: number;
  return_1d: number | null;
  return_5d: number | null;
  return_20d: number | null;
  momentum_regime: "leader" | "improving" | "weakening" | "laggard" | "mixed" | "unavailable";
}

export interface Fundamentals {
  market_cap: number | null;
  pe_ratio: number | null;
  eps: number | null;
  dividend_yield: number | null;
  week52_high: number | null;
  week52_low: number | null;
}

export interface StockDetail extends Quote {
  industry: string | null;
  exchange: string | null;
  fundamentals: Fundamentals | null;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface IndicatorPoint {
  date: string;
  rsi_14: number | null;
  ema_20: number | null;
  ema_50: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bb_upper: number | null;
  bb_middle: number | null;
  bb_lower: number | null;
  atr_14: number | null;
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

export interface MarketWorkspace {
  universe: UniverseCode;
  stocks: MarketStockSnapshot[];
  breadth: Breadth;
  sectors: SectorOverview[];
  technical: TechnicalSummary;
  heatmap: HeatmapStock[];
  sector_rotation: SectorRotation[];
  economic_events: EconomicCalendar;
  sentiment: LatestSentiment[];
}

export const marketApi = {
  universes: () => request<UniverseOption[]>("/api/v1/market/universes"),
  workspace: (universe: UniverseCode, days = 14) =>
    request<MarketWorkspace>(`/api/v1/market/workspace?universe=${universe}&days=${days}`),
  stocks: (universe?: UniverseCode) => request<MarketStockSnapshot[]>(`/api/v1/market/stocks${universe ? `?universe=${universe}` : ""}`),
  heatmap: (universe: UniverseCode) => request<HeatmapStock[]>(`/api/v1/market/heatmap?universe=${universe}`),
  sectorRotation: (universe: UniverseCode) => request<SectorRotation[]>(`/api/v1/market/sector-rotation?universe=${universe}`),
  detail: (symbol: string) =>
    request<StockDetail>(`/api/v1/market/stocks/${encodeURIComponent(symbol)}`),
  attribution: (symbol: string) =>
    request<MovementAttribution>(
      `/api/v1/market/stocks/${encodeURIComponent(symbol)}/attribution`,
    ),
  prices: (symbol: string, limit = 180) =>
    request<PricePoint[]>(`/api/v1/market/stocks/${encodeURIComponent(symbol)}/prices?limit=${limit}`),
  indicators: (symbol: string, limit = 180) =>
    request<IndicatorPoint[]>(`/api/v1/market/stocks/${encodeURIComponent(symbol)}/indicators?limit=${limit}`),
  gainers: (limit = 5, universe?: UniverseCode) => request<Quote[]>(`/api/v1/market/gainers?limit=${limit}${universe ? `&universe=${universe}` : ""}`),
  losers: (limit = 5, universe?: UniverseCode) => request<Quote[]>(`/api/v1/market/losers?limit=${limit}${universe ? `&universe=${universe}` : ""}`),
  breadth: (universe?: UniverseCode) => request<Breadth>(`/api/v1/market/breadth${universe ? `?universe=${universe}` : ""}`),
  sectors: (universe?: UniverseCode) => request<SectorOverview[]>(`/api/v1/market/sectors${universe ? `?universe=${universe}` : ""}`),
  technicalSummary: (universe?: UniverseCode) =>
    request<TechnicalSummary>(`/api/v1/market/technical-summary${universe ? `?universe=${universe}` : ""}`),
  economicEvents: (days = 14) =>
    request<EconomicCalendar>(`/api/v1/market/economic-events?days=${days}`),
};

// ----- News & sentiment ----------------------------------------------------
export interface SentimentDaily {
  date: string;
  avg_sentiment: number;
  article_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
}

export interface StockSentiment {
  symbol: string;
  name: string | null;
  latest_sentiment: number | null;
  availability: "available" | "no_relevant_news";
  confidence: number | null;
  article_count: number;
  positive_count: number;
  negative_count: number;
  neutral_count: number;
  evidence: StockNewsEvidence[];
  series: SentimentDaily[];
}

export interface LatestSentiment {
  symbol: string;
  latest_sentiment: number | null;
  availability: "available" | "no_relevant_news";
  confidence: number | null;
  article_count: number;
}

export interface StockNewsEvidence {
  id: number;
  headline: string;
  publisher: string;
  published_at: string | null;
  source_url: string;
  sentiment_class: "positive" | "neutral" | "negative";
  sentiment_score: number;
  sentiment_confidence: number;
  event_category: string;
  event_confidence: number;
  driver: string;
  evidence_excerpt: string;
  matched_alias: string | null;
  entity_match_confidence: number;
}

export interface NewsArticle {
  id: number;
  source: string;
  url: string;
  title: string;
  summary: string;
  published_at: string | null;
  sentiment_label: string;
  sentiment_score: number;
  sentiment_confidence: number;
  event_category: string;
  event_confidence: number;
  driver: string;
  evidence_excerpt: string;
  tags: string[];
  associations: {
    symbol: string;
    matched_alias: string | null;
    entity_match_confidence: number;
  }[];
}

export const newsApi = {
  recent: (limit = 50) => request<NewsArticle[]>(`/api/v1/news?limit=${limit}`),
  latestSentiment: () => request<LatestSentiment[]>("/api/v1/news/sentiment"),
  stockSentiment: (symbol: string) =>
    request<StockSentiment>(`/api/v1/news/sentiment/${encodeURIComponent(symbol)}`),
};

export interface AttributionDriver {
  rank: number;
  category: string;
  label: string;
  observation: string;
  direction: "bullish" | "bearish" | "neutral" | "unavailable";
  relevance: "high" | "medium" | "low" | "unavailable";
  confidence: number;
  value_percent: number | null;
  evidence_article_ids: number[];
}

export interface ConflictSignal {
  source: string;
  direction: "bullish" | "bearish" | "neutral" | "unavailable";
  confidence: number;
  observation: string;
}

export interface MovementAttribution {
  symbol: string;
  as_of: string | null;
  change_percent: number | null;
  certainty: "likely_contributors_not_proven_causes";
  summary: string;
  drivers: AttributionDriver[];
  evidence_conflict: {
    consensus: "bullish" | "bearish" | "neutral" | "mixed" | "unavailable";
    confidence: number;
    conflict_detected: boolean;
    signals: ConflictSignal[];
  };
}

// ----- Historical similarity types (Phase 4 reads) --------------------------
export interface SessionSummary {
  date: string;
  avg_return: number;
  pct_advancers: number;
  advance_decline_ratio: number;
  avg_rsi: number;
  feature_version?: string;
  median_rsi?: number;
  median_atr_percent?: number;
  median_relative_volume?: number;
  coverage_ratio?: number;
  usable_constituents?: number;
  expected_constituents?: number;
  membership_mode?: "effective_membership" | "available_data_proxy" | string;
  quality_flags?: string[];
  breadth_regime?: string;
  momentum_regime?: string;
  volatility_regime?: string;
}

export interface FactorComparison {
  factor: string;
  similarity_score: number;
  explanation: string;
}

export interface SimilarSession extends SessionSummary {
  similarity_score: number;
  distance: number;
  next_day_return: number | null;
  outcome: string | null;
  next_session_breadth?: number | null;
  forward_5_session_return?: number | null;
  forward_5_session_drawdown?: number | null;
  forward_5_session_upside?: number | null;
  matching_factors?: FactorComparison[];
  divergence_factors?: FactorComparison[];
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
  feature_version?: string;
  vector_dimension?: number;
  normalization_method?: string;
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
  sectors: SectorOverview[];
  technical: TechnicalSummary;
  sentiment: LatestSentiment[];
  opportunities: Recommendation[];
  risk_alerts: Recommendation[];
  history: SimilarityResult | null;
  generation: GenerationSummary;
  freshness: DataFreshness[];
}

export interface DataFreshness {
  dataset: "market" | "news" | "universe" | "historical_corpus";
  state: "Fresh" | "Delayed" | "Unavailable";
  observed_date: string | null;
  observed_at: string | null;
  expected_trading_date: string | null;
  explanation: string;
}

export const dashboardApi = {
  summary: () => request<DashboardSummary>("/api/v1/dashboard/summary", { auth: true }),
};

export interface PipelineStepStatus { step_name: string; sequence: number; status: "pending" | "running" | "completed" | "failed" | "skipped"; attempt_count: number; counters: Record<string, number>; last_error_summary: string | null; started_at: string | null; heartbeat_at: string | null; completed_at: string | null }
export interface PipelineRunStatus { id: number; pipeline_name: string; target_trading_date: string; correlation_id: string; status: "pending" | "running" | "partial" | "completed" | "failed"; attempt_count: number; counters: Record<string, number>; last_error_summary: string | null; started_at: string | null; heartbeat_at: string | null; completed_at: string | null; created_at: string; updated_at: string; steps: PipelineStepStatus[] }
export interface EODStatus { pipeline_name: string; requested_trading_date: string | null; run: PipelineRunStatus | null; rerun_recommended: boolean; health: "healthy" | "running" | "attention" | "unavailable"; operator_explanation: string; freshness: DataFreshness[] }
export const operationsApi = { eodStatus: (target?: string) => request<EODStatus>(`/api/v1/admin/jobs/eod/status${target ? `?target_trading_date=${encodeURIComponent(target)}` : ""}`, { auth: true }) };

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

// ----- Strategies & deterministic backtesting (Phase 11C) -----------------
export type RuleField =
  | "price_vs_ema20" | "price_vs_ema50" | "rsi" | "macd_histogram"
  | "volume_ratio" | "sector_momentum_20d" | "market_breadth"
  | "market_regime" | "news_sentiment";
export type RuleOperator = "gt" | "gte" | "lt" | "lte" | "between" | "positive" | "negative" | "above" | "below" | "is" | "is_not";
export type RuleNode = RuleCondition | RuleGroup;
export interface RuleCondition { kind: "condition"; field: RuleField; operator: RuleOperator; value?: number | string | null; upper_value?: number | null }
export interface RuleGroup { kind: "group"; operator: "AND" | "OR" | "NOT"; rules: RuleNode[] }
export interface ExecutionConfig { initial_capital: number; max_positions: number; transaction_cost_bps: number; slippage_bps: number; stop_loss_percent: number | null; take_profit_percent: number | null; max_holding_sessions: number | null; benchmark_symbol: string }
export interface StrategyDefinition { entry: RuleGroup; exit: RuleGroup; execution: ExecutionConfig }
export interface StrategyVersion { id: number; version: number; definition: StrategyDefinition; created_at: string }
export interface Strategy { id: number; name: string; description: string | null; is_active: boolean; created_at: string; updated_at: string; latest_version: StrategyVersion }
export interface BacktestMetrics { total_return_percent: number; benchmark_return_percent: number | null; excess_return_percent: number | null; cagr_percent: number | null; sharpe_ratio: number | null; sortino_ratio: number | null; max_drawdown_percent: number; win_rate_percent: number | null; profit_factor: number | null; average_winner_percent: number | null; average_loser_percent: number | null; expectancy_percent: number | null; total_trades: number; average_holding_sessions: number | null; turnover_percent: number; estimated_transaction_costs: number }
export interface EquityPoint { date: string; equity: number; benchmark_equity: number | null; drawdown_percent: number }
export interface BacktestTrade { symbol: string; entry_signal_date: string; entry_date: string; entry_price: number; exit_signal_date: string | null; exit_date: string; exit_price: number; quantity: number; gross_pnl: number; net_pnl: number; return_percent: number; holding_sessions: number; exit_reason: string; transaction_cost: number }
export interface ValidationMetricSlice { total_return_percent: number; benchmark_return_percent: number | null; excess_return_percent: number | null; max_drawdown_percent: number; sharpe_ratio: number | null; total_trades: number }
export interface PerformanceBreakdown { label: string; trades: number; average_return_percent: number; win_rate_percent: number; net_pnl: number }
export interface SignalOutcome { symbol: string; signal_date: string; execution_date: string; confidence: number; confidence_bucket: string; positive_outcome: boolean; return_percent: number; net_pnl: number; breadth_regime: string; momentum_regime: string; volatility_regime: string; macro_stress: string; sector: string }
export interface RobustnessAnalysis { analysis_version: "strategy_robustness_v1"; baseline_result_hash: string; chronological_split: { train_percent: number; test_percent: number; split_date: string | null; training: ValidationMetricSlice | null; test: ValidationMetricSlice | null; note: string }; signal_outcomes: SignalOutcome[]; breakdowns: Record<"breadth_regime" | "momentum_regime" | "volatility_regime" | "macro_stress" | "sector" | "confidence_bucket", PerformanceBreakdown[]>; parameter_sensitivity: (ValidationMetricSlice & { label: string })[]; cost_sensitivity: (ValidationMetricSlice & { label: string; transaction_cost_bps: number; slippage_bps: number })[]; robustness: { score: number; components: Record<string, number>; explanation: string[] } }
export interface Backtest { id: number; strategy_id: number; strategy_version_id: number; strategy_version: number; status: "completed" | "failed"; start_date: string; end_date: string; universe_code: "NIFTY50" | "NIFTYNEXT50" | "NIFTY100"; membership_mode: "current_universe" | "historical_membership"; membership_disclaimer: string; benchmark_symbol: string; result_hash: string | null; created_at: string; completed_at: string | null; metrics: BacktestMetrics | null; equity_curve: EquityPoint[]; trades: BacktestTrade[]; robustness_analysis: RobustnessAnalysis | null }
export interface BacktestSummary { id: number; strategy_version: number; status: "completed" | "failed"; start_date: string; end_date: string; universe_code: "NIFTY50" | "NIFTYNEXT50" | "NIFTY100"; membership_mode: "current_universe" | "historical_membership"; result_hash: string | null; created_at: string; metrics: BacktestMetrics | null }

export const strategiesApi = {
  list: () => request<Strategy[]>("/api/v1/strategies", { auth: true }),
  create: (payload: { name: string; description?: string; definition: StrategyDefinition }) => request<Strategy>("/api/v1/strategies", { method: "POST", body: payload, auth: true }),
  update: (id: number, payload: { name?: string; description?: string; definition: StrategyDefinition }) => request<Strategy>(`/api/v1/strategies/${id}`, { method: "PUT", body: payload, auth: true }),
  archive: (id: number) => request<null>(`/api/v1/strategies/${id}`, { method: "DELETE", auth: true }),
  run: (id: number, payload: { start_date: string; end_date: string; universe_code: string; membership_mode: string }) => request<Backtest>(`/api/v1/strategies/${id}/backtests`, { method: "POST", body: payload, auth: true }),
  runs: (id: number) => request<BacktestSummary[]>(`/api/v1/strategies/${id}/backtests`, { auth: true }),
  backtest: (id: number) => request<Backtest>(`/api/v1/backtests/${id}`, { auth: true }),
  analyze: (id: number) => request<RobustnessAnalysis>(`/api/v1/backtests/${id}/robustness`, { method: "POST", auth: true }),
};

// ----- Deterministic discovery (Phase 11F) -------------------------------
export type ScreenerField = "sector" | "price_change_percent" | "rsi_14" | "price_vs_ema20" | "price_vs_ema50" | "macd_histogram" | "volume_ratio" | "pe_ratio" | "eps" | "news_sentiment" | "signal_state" | "regime_fit";
export interface ScreenerCondition { field: ScreenerField; operator: string; value: number | string | null; upper_value: number | null }
export interface ScreenerAST { version: "screener_ast_v1"; universe: "NIFTY50" | "NIFTYNEXT50" | "NIFTY100"; conditions: ScreenerCondition[] }
export interface ScreenerRow { symbol: string; name: string | null; sector: string | null; as_of: string | null; close: number | null; price_change_percent: number | null; rsi_14: number | null; ema_20: number | null; ema_50: number | null; macd_histogram: number | null; volume_ratio: number | null; pe_ratio: number | null; eps: number | null; news_sentiment: number | null; signal_state: string; regime_fit: string }
export interface ScreenerResult { query: string; ast: ScreenerAST; explanation: string[]; rows: ScreenerRow[]; result_hash: string }
export interface SavedScreen { id: number; name: string; query_text: string; filter_ast: ScreenerAST; created_at: string; updated_at: string }

export const discoveryApi = {
  screen: (query: string) => request<ScreenerResult>("/api/v1/discovery/screen", { method: "POST", body: { query }, auth: true }),
  list: () => request<SavedScreen[]>("/api/v1/discovery/screens", { auth: true }),
  save: (payload: { name: string; query_text: string; filter_ast: ScreenerAST }) => request<SavedScreen>("/api/v1/discovery/screens", { method: "POST", body: payload, auth: true }),
  run: (id: number) => request<ScreenerResult>(`/api/v1/discovery/screens/${id}/run`, { method: "POST", auth: true }),
  remove: (id: number) => request<null>(`/api/v1/discovery/screens/${id}`, { method: "DELETE", auth: true }),
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
 * the blob with the session cookie, then triggers a browser download.
 */
export async function downloadReport(id: number, fmt: "markdown" | "pdf"): Promise<void> {
  const res = await fetch(`${API_URL}/api/v1/reports/${id}/export?format=${fmt}`, {
    cache: "no-store",
    credentials: "include",
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
