import type {
  DraftBoard,
  DraftMode,
  DraftMockBatch,
  MockOrderPreview,
  DraftReplay,
  DraftSession,
  League,
  PlayerIdentity,
  TargetStatus,
  DraftSyncResult,
  DraftSyncState,
  TeamCategoryBaseline,
  YahooRosterBaseline,
} from "./types";
import type { WaiverBoard, WaiverImpact, WaiverMode, WaiverRefreshStatus, TransactionAnalysis } from "./waiverTypes";

export type MockRehearsalAction =
  | "normal" | "fast" | "step_one_pick" | "deliver_next_snapshot" | "pause_source"
  | "resume_source" | "simulate_source_lag" | "release_delayed_picks"
  | "simulate_duplicate_snapshot" | "simulate_multiple_picks_together"
  | "simulate_source_outage" | "recover_source" | "simulate_local_ahead_confirmation"
  | "simulate_pick_conflict" | "resolve_with_yahoo" | "keep_local_and_pause" | "undo_latest_local"
  | "simulate_malformed_source" | "simulate_unknown_player" | "reset_rehearsal";

export type ApiErrorCode =
  | "GATEWAY_TIMEOUT"
  | "TIMEOUT"
  | "NETWORK_ERROR"
  | "ABORTED"
  | "BAD_GATEWAY"
  | "SERVICE_UNAVAILABLE"
  | "SERVER_ERROR"
  | "INVALID_RESPONSE"
  | string;

const RETRYABLE_STATUSES = new Set([0, 408, 425, 429, 500, 502, 503, 504]);
const STATUS_TEXT: Record<number, { code: ApiErrorCode; message: string }> = {
  500: { code: "SERVER_ERROR", message: "The server hit an error while handling the request." },
  502: { code: "BAD_GATEWAY", message: "The server is temporarily unavailable." },
  503: { code: "SERVICE_UNAVAILABLE", message: "The server is temporarily unavailable." },
  504: { code: "GATEWAY_TIMEOUT", message: "The server took too long to respond." },
};
const HTML_PATTERN = /<\s*(!doctype|html|head|body|center|h1|hr)\b/i;
const MAX_MESSAGE_LENGTH = 400;

/** A normalized API failure: a short message only, never a raw HTML or text response body. */
export class ApiError extends Error {
  status: number;
  code: ApiErrorCode;
  retryable: boolean;
  requestId: string | null;
  mismatches: string[];

  constructor(status: number, message: string, mismatches: string[] = [], options: {
    code?: ApiErrorCode; retryable?: boolean; requestId?: string | null;
  } = {}) {
    super(message);
    this.status = status;
    this.code = options.code ?? STATUS_TEXT[status]?.code ?? `HTTP_${status}`;
    this.retryable = options.retryable ?? RETRYABLE_STATUSES.has(status);
    this.requestId = options.requestId ?? null;
    this.mismatches = mismatches;
  }
}

export function isTimeoutError(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "GATEWAY_TIMEOUT" || error.code === "TIMEOUT");
}

function safeText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || HTML_PATTERN.test(text)) return null;
  return text.length > MAX_MESSAGE_LENGTH ? `${text.slice(0, MAX_MESSAGE_LENGTH)}…` : text;
}

function statusMessage(status: number): string {
  return STATUS_TEXT[status]?.message ?? `The request failed (HTTP ${status}).`;
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs?: number): Promise<T> {
  const controller = new AbortController();
  const outer = init.signal;
  let timedOut = false;
  const abortFromCaller = () => controller.abort();
  if (outer) {
    if (outer.aborted) controller.abort();
    else outer.addEventListener("abort", abortFromCaller, { once: true });
  }
  const timer = timeoutMs ? globalThis.setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs) : undefined;
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: {
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...init.headers,
      },
    });
  } catch {
    if (timedOut) throw new ApiError(0, "The request timed out before the server answered.", [], { code: "TIMEOUT", retryable: true });
    if (controller.signal.aborted) throw new ApiError(0, "The request was cancelled.", [], { code: "ABORTED", retryable: false });
    throw new ApiError(0, "Could not reach the server. Check the connection, then retry.", [], { code: "NETWORK_ERROR", retryable: true });
  } finally {
    if (timer !== undefined) globalThis.clearTimeout(timer);
    outer?.removeEventListener("abort", abortFromCaller);
  }
  const requestId = response.headers.get("x-request-id");
  const text = await response.text();
  let payload: unknown = null;
  let parsed = false;
  if (text) {
    try {
      payload = JSON.parse(text);
      parsed = true;
    } catch (cause) {
      if (!(cause instanceof SyntaxError)) throw cause;
      if (response.ok) {
        throw new ApiError(response.status, "The server returned an invalid response.", [], { code: "INVALID_RESPONSE", retryable: true, requestId });
      }
    }
  }
  if (!response.ok) {
    // Non-JSON bodies (for example an nginx 504 page) are never shown; only the status is used.
    const body = parsed && typeof payload === "object" && payload !== null ? payload as { detail?: unknown } : null;
    const detail = body?.detail;
    const structured = typeof detail === "object" && detail !== null && !Array.isArray(detail)
      ? detail as Record<string, unknown> : null;
    const mismatches = Array.isArray(structured?.mismatches)
      ? structured.mismatches.filter((item): item is string => typeof item === "string")
      : [];
    // FastAPI request-validation errors arrive as a list of {loc, msg, type} items.
    const validation = Array.isArray(detail)
      ? detail.map((item) => safeText(typeof item === "object" && item !== null ? (item as { msg?: unknown }).msg : null))
      : [];
    const parts = [safeText(detail), safeText(structured?.message), safeText(structured?.reason_code), safeText(structured?.reason),
      ...mismatches.map(safeText), ...validation].filter((part): part is string => part !== null);
    const message = parts.length ? [...new Set(parts)].join(" · ") : statusMessage(response.status);
    const code = typeof structured?.code === "string" ? structured.code : undefined;
    throw new ApiError(response.status, message, mismatches, {
      code, requestId,
      retryable: code === "RECOMMENDATION_CONTRACT_VIOLATION" ? false : undefined,
    });
  }
  return payload as T;
}

// Waiver reads normally finish in seconds; the proxy cuts requests at 60 seconds. This client limit
// only covers a proxy that never answers.
const WAIVER_READ_TIMEOUT_MS = 75_000;

export const api = {
  getWaivers: (mode: WaiverMode, signal?: AbortSignal) =>
    request<WaiverBoard>(`/api/v1/waivers?${new URLSearchParams({ mode })}`, { signal }, WAIVER_READ_TIMEOUT_MS),
  getWaiverTransactions: (mode: WaiverMode, signal?: AbortSignal) =>
    request<TransactionAnalysis>(`/api/v1/waivers/transactions?${new URLSearchParams({ mode })}`, { signal }, WAIVER_READ_TIMEOUT_MS),
  getWaiverReplacements: (dropPlayerId: number, mode: WaiverMode, signal?: AbortSignal) =>
    request<WaiverBoard>(`/api/v1/waivers/replacements?${new URLSearchParams({
      drop_player_id: String(dropPlayerId), mode,
    })}`, { signal }, WAIVER_READ_TIMEOUT_MS),
  getWaiverImpact: (playerId: number, mode: WaiverMode, dropPlayerId?: number, signal?: AbortSignal) =>
    request<WaiverImpact>(`/api/v1/waivers/${playerId}/impact?${new URLSearchParams({
      mode,
      ...(dropPlayerId !== undefined ? { drop_player_id: String(dropPlayerId) } : {}),
    })}`, { signal }, WAIVER_READ_TIMEOUT_MS),
  getWaiverRefresh: (signal?: AbortSignal) =>
    request<WaiverRefreshStatus>("/api/v1/waivers/refresh", { signal }, 30_000),
  // The Waiver Center's only mutation: start (or rejoin) the backend-owned Yahoo + NBA refresh.
  startWaiverRefresh: (retryFailed = false) =>
    request<WaiverRefreshStatus>("/api/v1/waivers/refresh", {
      method: "POST",
      body: JSON.stringify({ retry_failed: retryFailed }),
    }, 30_000),
  getLeagues: () => request<League[]>("/api/v1/leagues"),
  getLeague: (leagueKey: string, signal?: AbortSignal) =>
    request<League>(`/api/v1/league?league_key=${encodeURIComponent(leagueKey)}`, { signal }),
  getRosters: (leagueKey: string, signal?: AbortSignal) =>
    request<YahooRosterBaseline[]>(`/api/v1/rosters?league_key=${encodeURIComponent(leagueKey)}`, { signal }),
  getTeamCategoryBaseline: (leagueKey: string, signal?: AbortSignal) =>
    request<TeamCategoryBaseline>(
      `/api/v1/team-category-baseline?league_key=${encodeURIComponent(leagueKey)}`,
      { signal },
    ),
  getSessions: () => request<DraftSession[]>("/api/v2/draft/sessions"),
  getMockSessions: () => request<DraftSession[]>("/api/v2/draft/mock-sessions"),
  deleteMockSession: (sessionId: string) =>
    request<void>(`/api/v2/draft/mock-sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    }),
  getPlayers: (signal?: AbortSignal) => request<PlayerIdentity[]>("/api/v1/players", { signal }),
  getBoard: (sessionId: string, sortBy = "decision", descending = true, signal?: AbortSignal) =>
    request<DraftBoard>(
      `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/board?sort_by=${sortBy}&descending=${descending}`,
      { signal },
    ),
  getDraftSync: (sessionId: string, signal?: AbortSignal) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync`, { signal }),
  syncDraft: (sessionId: string) =>
    request<DraftSyncResult>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync`, {
      method: "POST",
    }),
  pauseDraftSync: (sessionId: string) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync/pause`, {
      method: "POST",
    }),
  resumeDraftSync: (sessionId: string) =>
    request<DraftSyncState>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/sync/resume`, {
      method: "POST",
    }),
  mockRehearsal: (sessionId: string, action: MockRehearsalAction) =>
    request<DraftSyncResult>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock-rehearsal`, {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  importLeagues: () => request<unknown>("/api/v1/leagues/import", { method: "POST" }),
  importPlayers: (leagueKey: string) =>
    request<unknown>(`/api/v1/players/import?league_key=${encodeURIComponent(leagueKey)}`, { method: "POST" }),
  buildMetrics: (leagueKey: string, season: string) =>
    request<unknown>(
      `/api/v1/draft/metrics?league_key=${encodeURIComponent(leagueKey)}&season=${encodeURIComponent(season)}`,
      { method: "POST" },
    ),
  createSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots: Record<string, number>;
    mode: DraftMode;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createLiveSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number | null;
    total_teams: number;
    rounds: number;
    team_slots: Record<string, number>;
    mode: DraftMode;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/live-sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createMockSession: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots?: Record<string, number>;
    mode: DraftMode;
    aggressiveness: number;
    seed?: number;
    opponent_order_seed?: number;
    live_sync_rehearsal?: boolean;
  }) =>
    request<{ state: DraftSession; event: string }>("/api/v2/draft/mock-sessions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createMockBatch: (body: {
    league_key: string;
    season: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    rounds: number;
    team_slots?: Record<string, number>;
    mode: DraftMode;
    aggressiveness: number;
    seed?: number;
    opponent_order_seed?: number;
    count: number;
  }) => request<{ batch: DraftMockBatch; session_ids: string[] }>("/api/v2/draft/mock-batches", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  previewMockOrder: (body: {
    league_key: string;
    manager_team_key: string;
    draft_position: number;
    total_teams: number;
    seed: number;
  }) => request<MockOrderPreview>("/api/v2/draft/mock-order-preview", {
    method: "POST",
    body: JSON.stringify(body),
  }),
  updateLiveOrder: (sessionId: string, body: {
    expected_version: number;
    draft_position?: number;
    team_slots?: Record<string, number>;
    replace_mapping?: boolean;
    clear_manager_position?: boolean;
  }) => request<DraftSession>(`/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/order`, {
    method: "PUT",
    body: JSON.stringify(body),
  }),
  getMockBatches: () => request<DraftMockBatch[]>("/api/v2/draft/mock-batches"),
  runMockBatch: (batchId: string) => request<{ batch: DraftMockBatch }>(
    `/api/v2/draft/mock-batches/${encodeURIComponent(batchId)}/run`,
    { method: "POST" },
  ),
  mockAction: (sessionId: string, action: "next_pick" | "until_my_turn") =>
    request<{ state: DraftSession; event: string; simulated_picks: number }>(
      `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock-action`,
      { method: "POST", body: JSON.stringify({ action }) },
    ),
  pauseMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/pause`, { method: "POST" },
  ),
  resumeMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/resume`, { method: "POST" },
  ),
  resetMock: (sessionId: string) => request<DraftSession>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/mock/reset`, { method: "POST" },
  ),
  getReplay: (sessionId: string, version: number) => request<DraftReplay>(
    `/api/v2/draft/sessions/${encodeURIComponent(sessionId)}/replay?version=${version}`,
  ),
  recordPick: (
    sessionId: string,
    pick: number,
    playerId: number,
    version: number,
    source = "manual",
  ) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}`, {
      method: "POST",
      body: JSON.stringify({
        selected_player_id: playerId,
        expected_version: version,
        source,
      }),
    }),
  correctPick: (sessionId: string, pick: number, playerId: number, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}`, {
      method: "PUT",
      body: JSON.stringify({
        selected_player_id: playerId,
        expected_version: version,
        source: "manual_correction",
      }),
    }),
  undoPick: (sessionId: string, pick: number, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/picks/${pick}/undo`, {
      method: "POST",
      body: JSON.stringify({ expected_version: version }),
    }),
  setTarget: (sessionId: string, playerId: number, status: TargetStatus, version: number) =>
    request<unknown>(`/api/v2/draft/sessions/${sessionId}/targets/${playerId}`, {
      method: "PUT",
      body: JSON.stringify({ status, expected_version: version }),
    }),
  clearTarget: (sessionId: string, playerId: number, version: number) =>
    request<unknown>(
      `/api/v2/draft/sessions/${sessionId}/targets/${playerId}?expected_version=${version}`,
      { method: "DELETE" },
    ),
};