import { useEffect, useState, type FormEvent } from "react";

interface Props {
  initialValue?: string;
  loading?: boolean;
  onSubmit: (query: string) => void;
  onStop?: () => void;
  size?: "lg" | "md";
}

export default function SearchBar({ initialValue = "", loading = false, onSubmit, onStop, size = "lg" }: Props) {
  const [value, setValue] = useState(initialValue);
  const [touchedEmpty, setTouchedEmpty] = useState(false);

  useEffect(() => setValue(initialValue), [initialValue]);

  const handle = (e: FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      setTouchedEmpty(true);
      return;
    }
    setTouchedEmpty(false);
    onSubmit(value);
  };

  const pad = size === "lg" ? "py-4 text-base" : "py-2.5 text-sm";
  return (
    <form onSubmit={handle} className="w-full" role="search">
      <div className="flex gap-2">
        <input
          aria-label="Research topic"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Enter a research topic, e.g. NLP for Indian languages"
          className={`w-full rounded-md border border-slate-300 bg-white px-4 ${pad} shadow-sm outline-none focus:border-navy-600 focus:ring-2 focus:ring-navy-100`}
        />
        {loading ? (
          <button
            key="stop-search-btn"
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onStop?.();
            }}
            aria-label="Stop Search"
            className={`inline-flex shrink-0 items-center gap-2 rounded-md bg-red-700 px-5 ${pad} font-medium text-white shadow-sm hover:bg-red-800`}
          >
            <svg className="h-3.5 w-3.5 fill-current" viewBox="0 0 16 16" aria-hidden="true">
              <rect x="2" y="2" width="12" height="12" rx="1.5" />
            </svg>
            <span>Stop Search</span>
          </button>
        ) : (
          <button
            key="submit-search-btn"
            type="submit"
            className={`shrink-0 rounded-md bg-navy-800 px-6 ${pad} font-medium text-white hover:bg-navy-700`}
          >
            Search
          </button>
        )}
      </div>
      {touchedEmpty && <p className="mt-2 text-sm text-red-700">Please enter a research topic.</p>}
    </form>
  );
}
