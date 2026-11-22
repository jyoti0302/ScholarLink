import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import SearchBar from "../components/SearchBar";
import { CANCELLED_SEARCH_MESSAGE, SearchProvider, createSearchController } from "../context/SearchContext";
import SearchResultsPage from "../pages/SearchResultsPage";
import type { SearchResponse } from "../types/api";
import { ApiError, cancelSearchRequest, describeHttpError, searchProfessors } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function makeSearchResponse(query: string, profName: string): SearchResponse {
  return {
    request_id: `req-${query}`,
    query,
    expanded_queries: [query],
    status: "ok",
    message: null,
    search_latency_ms: 42,
    total_results: 1,
    results: [
      {
        professor_id: 1,
        professor_name: profName,
        department: "CS",
        department_code: "CS",
        department_name: "Computer Science and Engineering",
        designation: "Professor",
        email: null,
        profile_url: null,
        score: 3.1,
        match_category: "strong",
        research_interests: query,
        evidence_counts: {},
        matched_topics: [],
        matched_queries: [query],
        supporting_evidence: [],
        explanation: "Matched.",
      },
    ],
  };
}

describe("searchProfessors API client", () => {
  it("rejects empty and whitespace queries without calling fetch", async () => {
    const fetchImpl = vi.fn();
    await expect(searchProfessors({ query: "   " }, { fetchImpl })).rejects.toMatchObject({ kind: "validation" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("sends the exact backend request schema with defaults", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        request_id: "r",
        query: "NLP",
        expanded_queries: [],
        status: "ok",
        message: null,
        search_latency_ms: 1,
        total_results: 0,
        results: [],
      }),
    );
    await searchProfessors({ query: "  NLP  " }, { fetchImpl });
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toMatch(/\/search$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      query: "NLP",
      limit: 20,
      use_expansion: true,
      include_candidate_publications: true,
    });
  });

  it.each([
    [422, "validation"],
    [503, "unavailable"],
    [500, "server"],
  ])("maps HTTP %i to %s", async (status, kind) => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(status, { detail: "x" }));
    await expect(searchProfessors({ query: "AI" }, { fetchImpl })).rejects.toMatchObject({ kind, status });
  });

  it("distinguishes timeout from manual AbortController cancellation", async () => {
    const hangingFetch = vi.fn(
      (_url: string, init: RequestInit) =>
        new Promise<Response>((_res, rej) => {
          init.signal?.addEventListener("abort", () =>
            rej(Object.assign(new Error("aborted"), { name: "AbortError" })),
          );
        }),
    );

    // 9. Timeout behavior still works
    await expect(
      searchProfessors({ query: "AI" }, { fetchImpl: hangingFetch as unknown as typeof fetch, timeoutMs: 10 }),
    ).rejects.toMatchObject({
      kind: "timeout",
    });

    // Manual abort via external AbortSignal produces kind="aborted", not "network" or "timeout"
    const manualCtrl = new AbortController();
    const p = searchProfessors(
      { query: "AI" },
      { fetchImpl: hangingFetch as unknown as typeof fetch, signal: manualCtrl.signal, timeoutMs: 5000 },
    );
    manualCtrl.abort();
    await expect(p).rejects.toMatchObject({
      kind: "aborted",
      message: CANCELLED_SEARCH_MESSAGE,
    });
  });

  it("reports network failures", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(searchProfessors({ query: "AI" }, { fetchImpl })).rejects.toBeInstanceOf(ApiError);
    await expect(searchProfessors({ query: "AI" }, { fetchImpl })).rejects.toMatchObject({ kind: "network" });
  });

  it("describeHttpError hides 500 internals", () => {
    expect(describeHttpError(500, "secret stack").message).not.toContain("secret");
  });
});

describe("Stop Search UI & race-free search controller", () => {
  it("1 & 4. renders active Stop Search button with stop-square icon when loading, and Search button when idle", () => {
    const loadingHtml = renderToStaticMarkup(
      React.createElement(SearchBar, {
        initialValue: "NLP for Indian languages",
        loading: true,
        onSubmit: () => {},
        onStop: () => {},
      }),
    );
    expect(loadingHtml).toContain("Stop Search");
    expect(loadingHtml).toContain("<rect");
    expect(loadingHtml).toContain('value="NLP for Indian languages"');

    const idleHtml = renderToStaticMarkup(
      React.createElement(SearchBar, {
        initialValue: "NLP for Indian languages",
        loading: false,
        onSubmit: () => {},
        onStop: () => {},
      }),
    );
    expect(idleHtml).toContain(">Search<");
    expect(idleHtml).not.toContain("Stop Search");
  });

  it("2, 3, 5 & 6. clicking Stop Search aborts active request, clears loading immediately, shows cancelled message, and allows immediate new search before old promise settles", async () => {
    const signals: AbortSignal[] = [];
    let resolveFirst!: (res: SearchResponse) => void;
    let resolveSecond!: (res: SearchResponse) => void;

    const executor = vi.fn((req, opts) => {
      if (opts?.signal) signals.push(opts.signal);
      return new Promise<SearchResponse>((resolve) => {
        if (req.query === "NLP for Indian languages") {
          resolveFirst = resolve;
        } else {
          resolveSecond = resolve;
        }
      });
    });

    const ctrl = createSearchController(executor);

    // Start first search
    const p1 = ctrl.runSearch("NLP for Indian languages");
    expect(ctrl.getSnapshot().loading).toBe(true);
    expect(signals).toHaveLength(1);
    expect(signals[0].aborted).toBe(false);

    // Stop search while first request is still pending
    ctrl.stopSearch();
    expect(signals[0].aborted).toBe(true); // 2. AbortController.abort() called
    expect(ctrl.getSnapshot().loading).toBe(false); // 3. Loading clears immediately
    expect(ctrl.getSnapshot().error).toBeNull(); // 6. No network error displayed
    expect(ctrl.getSnapshot().cancelledMessage).toBe(CANCELLED_SEARCH_MESSAGE);

    // 5. Immediately submit a new query WITHOUT waiting for p1 to settle
    const p2 = ctrl.runSearch("Generative AI for healthcare");
    expect(ctrl.getSnapshot().loading).toBe(true);
    expect(ctrl.getSnapshot().query).toBe("Generative AI for healthcare");
    expect(ctrl.getSnapshot().cancelledMessage).toBeNull();
    expect(signals).toHaveLength(2);

    // Settle p1 late — must NOT clear p2's loading state or overwrite p2
    resolveFirst(makeSearchResponse("NLP for Indian languages", "Stale Prof"));
    await p1;
    expect(ctrl.getSnapshot().loading).toBe(true); // 8. Older request cannot clear newer loading state
    expect(ctrl.getSnapshot().response).toBeNull();

    // Now resolve p2
    resolveSecond(makeSearchResponse("Generative AI for healthcare", "Healthcare Prof"));
    await p2;
    expect(ctrl.getSnapshot().loading).toBe(false);
    expect(ctrl.getSnapshot().response?.results[0].professor_name).toBe("Healthcare Prof");
  });

  it("7 & 8. older request resolving after newer request finishes never overwrites newer results", async () => {
    let resolveA!: (res: SearchResponse) => void;
    let resolveB!: (res: SearchResponse) => void;

    const ctrl = createSearchController((req) => {
      return new Promise<SearchResponse>((resolve) => {
        if (req.query === "Query A") resolveA = resolve;
        else resolveB = resolve;
      });
    });

    const pA = ctrl.runSearch("Query A");
    const pB = ctrl.runSearch("Query B"); // automatically invalidates Query A

    resolveB(makeSearchResponse("Query B", "Prof B"));
    await pB;
    expect(ctrl.getSnapshot().response?.results[0].professor_name).toBe("Prof B");
    expect(ctrl.getSnapshot().loading).toBe(false);

    // Now Query A finally resolves late
    resolveA(makeSearchResponse("Query A", "Prof A"));
    await pA;
    expect(ctrl.getSnapshot().response?.results[0].professor_name).toBe("Prof B");
    expect(ctrl.getSnapshot().query).toBe("Query B");
  });

  it("10. supports repeated cancellations and subsequent searches reliably", async () => {
    const signals: AbortSignal[] = [];
    const ctrl = createSearchController((req, opts) => {
      if (opts?.signal) signals.push(opts.signal);
      if (req.query === "Final Query") {
        return Promise.resolve(makeSearchResponse("Final Query", "Final Prof"));
      }
      return new Promise<SearchResponse>(() => {});
    });

    void ctrl.runSearch("Attempt 1");
    ctrl.stopSearch();
    expect(signals[0].aborted).toBe(true);
    expect(ctrl.getSnapshot().loading).toBe(false);
    expect(ctrl.getSnapshot().cancelledMessage).toBe(CANCELLED_SEARCH_MESSAGE);

    void ctrl.runSearch("Attempt 2");
    ctrl.stopSearch();
    expect(signals[1].aborted).toBe(true);
    expect(ctrl.getSnapshot().loading).toBe(false);
    expect(ctrl.getSnapshot().cancelledMessage).toBe(CANCELLED_SEARCH_MESSAGE);

    await ctrl.runSearch("Final Query");
    expect(ctrl.getSnapshot().loading).toBe(false);
    expect(ctrl.getSnapshot().cancelledMessage).toBeNull();
    expect(ctrl.getSnapshot().response?.results[0].professor_name).toBe("Final Prof");
  });

  it("SearchResultsPage immediately hides skeletons, restores Search button, preserves query, and shows cancellation message upon stopSearch while old promise stays pending", async () => {
    let rejectOld!: (err: Error) => void;
    const ctrl = createSearchController(
      () =>
        new Promise<SearchResponse>((_resolve, reject) => {
          rejectOld = reject;
        }),
    );

    const renderPage = () =>
      renderToStaticMarkup(
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/results?q=Transformer%20architecture%20in%20AI"] },
          React.createElement(SearchProvider, {
            controller: ctrl,
            children: React.createElement(
              Routes,
              null,
              React.createElement(Route, { path: "/results", element: React.createElement(SearchResultsPage) }),
            ),
          }),
        ),
      );

    // Start pending search
    const pOld = ctrl.runSearch("Transformer architecture in AI");
    const loadingHtml = renderPage();
    expect(loadingHtml).toContain("Stop Search");
    expect(loadingHtml).toContain("animate-pulse");
    expect(loadingHtml).toContain("Searching faculty evidence");

    // Synchronously stop while pOld is still unresolved
    ctrl.stopSearch();
    const stoppedHtml = renderPage();
    expect(stoppedHtml).not.toContain("Stop Search");
    expect(stoppedHtml).not.toContain("animate-pulse");
    expect(stoppedHtml).toContain(">Search<");
    expect(stoppedHtml).toContain(CANCELLED_SEARCH_MESSAGE);
    expect(stoppedHtml).toContain('value="Transformer architecture in AI"');

    // Scenario A: old promise rejecting later must not restore loading or show an error
    rejectOld(new TypeError("Failed to fetch"));
    await pOld;
    expect(ctrl.getSnapshot().loading).toBe(false);
    expect(ctrl.getSnapshot().error).toBeNull();
    expect(ctrl.getSnapshot().cancelledMessage).toBe(CANCELLED_SEARCH_MESSAGE);
  });

  it("notifies backend cancellation endpoint with the active request_id when Stop Search is clicked", () => {
    const cancelledIds: string[] = [];
    const seenRequestIds: string[] = [];
    const ctrl = createSearchController(
      (req) => {
        if (req.request_id) seenRequestIds.push(req.request_id);
        return new Promise<SearchResponse>(() => {});
      },
      (id) => cancelledIds.push(id),
    );

    void ctrl.runSearch("NLP");
    expect(seenRequestIds).toHaveLength(1);
    ctrl.stopSearch();
    expect(cancelledIds).toEqual(seenRequestIds);

    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    cancelSearchRequest("req-xyz", fetchMock as unknown as typeof fetch);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/search\/cancel\/req-xyz$/), {
      method: "POST",
      keepalive: true,
    });
  });
});
