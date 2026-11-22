import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ProfessorCard from "../components/ProfessorCard";
import SearchBar from "../components/SearchBar";
import { ResultSkeleton, StatePanel } from "../components/States";
import { useSearch } from "../context/SearchContext";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

export default function SearchResultsPage() {
  const [params] = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  const urlUnivRaw = params.get("university_id");
  const urlUnivId = urlUnivRaw && /^\d+$/.test(urlUnivRaw) ? Number(urlUnivRaw) : null;

  const {
    query,
    response,
    results,
    totalQualifying,
    hasMore,
    loading,
    loadingMore,
    error,
    cancelledMessage,
    runSearch,
    loadMore,
    stopSearch,
  } = useSearch();
  const submit = useSearchNavigation();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => new Set());

  // Direct visit / refresh: run the search from the URL if context has nothing for it.
  useEffect(() => {
    if (urlQuery && urlQuery !== query && !loading && !cancelledMessage) {
      void runSearch(urlQuery, urlUnivId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery, urlUnivId]);

  // Reset expanded cards only when the active search query changes (preserved across Load More)
  useEffect(() => {
    setExpandedIds(new Set());
  }, [query]);

  const toggleCard = (professorId: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(professorId)) next.delete(professorId);
      else next.add(professorId);
      return next;
    });
  };

  const empty = response && (response.status === "insufficient_evidence" || results.length === 0);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <SearchBar size="md" initialValue={query || urlQuery} loading={loading} onSubmit={submit} onStop={stopSearch} />

      <div className="mt-8">
        {loading && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600" role="status">
              Searching faculty evidence for “{query || urlQuery}”… this can take up to a minute.
            </p>
            {[0, 1, 2].map((i) => (
              <ResultSkeleton key={i} />
            ))}
          </div>
        )}

        {!loading && error && <StatePanel tone="error" title="Search could not be completed" message={error.message} />}

        {!loading && !error && cancelledMessage && (
          <StatePanel title="Search stopped" message={cancelledMessage} />
        )}

        {!loading && !error && !cancelledMessage && empty && (
          <StatePanel
            title="No relevant faculty found"
            message={response?.message || "No sufficiently relevant professors found. Try a broader or differently worded research topic."}
          />
        )}

        {!loading && !error && !cancelledMessage && response && results.length > 0 && (
          <>
            <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
              <h1 className="font-serif text-2xl text-navy-900">
                {totalQualifying} qualifying {totalQualifying === 1 ? "professor" : "professors"} for “{response.query}”
              </h1>
              <span className="text-xs text-slate-500">
                Showing {results.length} of {totalQualifying} · {(response.search_latency_ms / 1000).toFixed(1)} s
              </span>
            </div>

            <div className="space-y-3">
              {results.map((p) => (
                <ProfessorCard
                  key={p.professor_id}
                  prof={p}
                  expanded={expandedIds.has(p.professor_id)}
                  onToggle={() => toggleCard(p.professor_id)}
                />
              ))}
            </div>

            {hasMore && (
              <div className="mt-6 text-center">
                <button
                  type="button"
                  disabled={loadingMore}
                  onClick={() => void loadMore()}
                  className="rounded-md border border-slate-300 bg-white px-6 py-2.5 text-sm font-medium text-navy-800 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loadingMore
                    ? "Loading more professors…"
                    : `Load More (${totalQualifying - results.length} remaining)`}
                </button>
              </div>
            )}
          </>
        )}

        {!loading && !error && !cancelledMessage && !response && !urlQuery && (
          <StatePanel title="Start a search" message="Enter a research topic above to discover relevant professors." />
        )}
      </div>
    </div>
  );
}
