import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { ApiError, cancelSearchRequest, searchProfessors } from "../api/client";
import type { SearchProfessorResult, SearchRequest, SearchResponse } from "../types/api";

export const CANCELLED_SEARCH_MESSAGE = "Search cancelled. You can start a new search.";
export const DEFAULT_PAGE_SIZE = 20;

function generateClientRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

export type SearchExecutor = (
  req: SearchRequest,
  opts?: { signal?: AbortSignal; timeoutMs?: number },
) => Promise<SearchResponse>;

export type SearchCanceller = (requestId: string) => void;

export interface SearchSnapshot {
  query: string;
  universityId: number | null;
  response: SearchResponse | null;
  results: SearchProfessorResult[];
  totalQualifying: number;
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: ApiError | null;
  cancelledMessage: string | null;
  requestId: number;
}

export interface SearchController {
  getSnapshot: () => SearchSnapshot;
  subscribe: (listener: () => void) => () => void;
  runSearch: (query: string, universityId?: number | null) => Promise<void>;
  loadMore: () => Promise<void>;
  stopSearch: () => void;
}

export function createSearchController(
  executor: SearchExecutor = searchProfessors,
  canceller: SearchCanceller = cancelSearchRequest,
): SearchController {
  let snapshot: SearchSnapshot = {
    query: "",
    universityId: null,
    response: null,
    results: [],
    totalQualifying: 0,
    hasMore: false,
    loading: false,
    loadingMore: false,
    error: null,
    cancelledMessage: null,
    requestId: 0,
  };
  let activeController: AbortController | null = null;
  let activeBackendRequestId: string | null = null;
  const listeners = new Set<() => void>();

  const emit = (patch: Partial<SearchSnapshot>) => {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach((l) => l());
  };

  const stopSearch = () => {
    const nextId = snapshot.requestId + 1;
    const ctrl = activeController;
    const backendReqId = activeBackendRequestId;
    activeController = null;
    activeBackendRequestId = null;
    emit({
      requestId: nextId,
      loading: false,
      loadingMore: false,
      response: null,
      results: [],
      totalQualifying: 0,
      hasMore: false,
      error: null,
      cancelledMessage: CANCELLED_SEARCH_MESSAGE,
    });
    ctrl?.abort();
    if (backendReqId) canceller(backendReqId);
  };

  const runSearch = async (rawQuery: string, universityId?: number | null): Promise<void> => {
    const trimmed = rawQuery.trim();
    if (!trimmed) {
      emit({
        error: new ApiError("validation", "Please enter a research topic to search."),
        cancelledMessage: null,
      });
      return;
    }

    const effectiveUnivId = universityId !== undefined ? universityId : snapshot.universityId;

    // Abort and invalidate any previous in-flight request immediately.
    const prevCtrl = activeController;
    const prevBackendReqId = activeBackendRequestId;
    const reqId = snapshot.requestId + 1;
    const backendReqId = generateClientRequestId();
    const controller = new AbortController();
    activeController = controller;
    activeBackendRequestId = backendReqId;

    emit({
      requestId: reqId,
      query: trimmed,
      universityId: effectiveUnivId ?? null,
      loading: true,
      loadingMore: false,
      error: null,
      cancelledMessage: null,
      response: null,
      results: [],
      totalQualifying: 0,
      hasMore: false,
    });
    prevCtrl?.abort();
    if (prevBackendReqId) canceller(prevBackendReqId);

    try {
      const res = await executor(
        {
          query: trimmed,
          limit: DEFAULT_PAGE_SIZE,
          offset: 0,
          university_id: effectiveUnivId ?? undefined,
          request_id: backendReqId,
        },
        { signal: controller.signal },
      );
      if (snapshot.requestId !== reqId) return; // stale request — ignore
      activeController = null;
      activeBackendRequestId = null;
      const totalQ = res.total_qualifying_results ?? res.total_results ?? res.results.length;
      const hasMore = res.has_more ?? res.results.length < totalQ;
      emit({
        response: res,
        results: res.results,
        totalQualifying: totalQ,
        hasMore,
        loading: false,
        loadingMore: false,
        error: null,
        cancelledMessage: null,
      });
    } catch (e) {
      if (snapshot.requestId !== reqId) return; // stale/cancelled request — ignore
      activeController = null;
      activeBackendRequestId = null;
      if (e instanceof ApiError && e.kind === "aborted") {
        emit({
          loading: false,
          loadingMore: false,
          error: null,
          cancelledMessage: CANCELLED_SEARCH_MESSAGE,
        });
        return;
      }
      emit({
        loading: false,
        loadingMore: false,
        error: e instanceof ApiError ? e : new ApiError("unknown", "Unexpected error."),
        cancelledMessage: null,
      });
    }
  };

  const loadMore = async (): Promise<void> => {
    if (snapshot.loading || snapshot.loadingMore || !snapshot.hasMore || !snapshot.query) return;

    const reqId = snapshot.requestId + 1;
    const backendReqId = generateClientRequestId();
    const controller = new AbortController();
    activeController = controller;
    activeBackendRequestId = backendReqId;

    const currentOffset = snapshot.results.length;
    emit({
      requestId: reqId,
      loadingMore: true,
      error: null,
    });

    try {
      const res = await executor(
        {
          query: snapshot.query,
          limit: DEFAULT_PAGE_SIZE,
          offset: currentOffset,
          university_id: snapshot.universityId ?? undefined,
          request_id: backendReqId,
        },
        { signal: controller.signal },
      );
      if (snapshot.requestId !== reqId) return;
      activeController = null;
      activeBackendRequestId = null;

      // Deduplicate by professor_id defensively across pages
      const seen = new Set(snapshot.results.map((r) => r.professor_id));
      const appended = res.results.filter((r) => !seen.has(r.professor_id));
      const merged = [...snapshot.results, ...appended];
      const totalQ = res.total_qualifying_results ?? Math.max(snapshot.totalQualifying, merged.length);
      const hasMore = res.has_more ?? merged.length < totalQ;

      emit({
        response: { ...res, results: merged, total_results: merged.length, total_qualifying_results: totalQ, has_more: hasMore },
        results: merged,
        totalQualifying: totalQ,
        hasMore,
        loadingMore: false,
      });
    } catch (e) {
      if (snapshot.requestId !== reqId) return;
      activeController = null;
      activeBackendRequestId = null;
      if (e instanceof ApiError && e.kind === "aborted") {
        emit({ loadingMore: false });
        return;
      }
      emit({
        loadingMore: false,
        error: e instanceof ApiError ? e : new ApiError("unknown", "Failed to load additional professors."),
      });
    }
  };

  return {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    runSearch,
    loadMore,
    stopSearch,
  };
}

export interface SearchState extends SearchSnapshot {
  runSearch: (query: string, universityId?: number | null) => Promise<void>;
  loadMore: () => Promise<void>;
  stopSearch: () => void;
}

const SearchContext = createContext<SearchController | null>(null);

export function SearchProvider({
  children,
  controller: externalController,
}: {
  children: ReactNode;
  controller?: SearchController;
}) {
  const controller = useMemo(() => externalController ?? createSearchController(), [externalController]);
  return <SearchContext.Provider value={controller}>{children}</SearchContext.Provider>;
}

export function useSearch(): SearchState {
  const controller = useContext(SearchContext);
  if (!controller) throw new Error("useSearch must be used within SearchProvider");
  const snap = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  return {
    ...snap,
    runSearch: controller.runSearch,
    loadMore: controller.loadMore,
    stopSearch: controller.stopSearch,
  };
}
