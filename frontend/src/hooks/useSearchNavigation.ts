import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useSearch } from "../context/SearchContext";

/**
 * Submits a search immediately (aborting any previous in-flight request)
 * and navigates to the results page with the query preserved in URL + context.
 */
export function useSearchNavigation() {
  const navigate = useNavigate();
  const { runSearch } = useSearch();
  return useCallback(
    (q: string) => {
      const trimmed = q.trim();
      if (!trimmed) return false;
      navigate(`/results?q=${encodeURIComponent(trimmed)}`);
      void runSearch(trimmed);
      return true;
    },
    [navigate, runSearch],
  );
}
