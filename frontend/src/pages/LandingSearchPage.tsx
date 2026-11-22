import SearchBar from "../components/SearchBar";
import { useSearch } from "../context/SearchContext";
import { useSearchNavigation } from "../hooks/useSearchNavigation";

export const EXAMPLE_QUERIES = [
  "NLP for Indian languages",
  "Generative AI for healthcare",
  "Computer vision for autonomous systems",
  "Mineral processing",
  "Geotechnical engineering",
];

const STEPS = [
  { title: "Describe your interest", text: "Type a research topic in plain language — no keywords or department names required." },
  { title: "Evidence-based matching", text: "We search publications, research interests, projects and biographies of IIT Kharagpur faculty." },
  { title: "Understand every match", text: "Each recommendation explains why, with links to its sources and clear verification labels." },
];

export default function LandingSearchPage() {
  const { loading, stopSearch, cancelledMessage } = useSearch();
  const submit = useSearchNavigation();

  return (
    <div>
      <section className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-3xl px-6 py-20 text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-navy-600">IIT Kharagpur · Research Discovery</p>
          <h1 className="mt-4 font-serif text-4xl text-navy-900 sm:text-5xl">Find the right professor for your research</h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-600">
            Discover faculty whose publications, projects and documented expertise align with what you want to study.
          </p>
          <div className="mt-10">
            <SearchBar loading={loading} onSubmit={submit} onStop={stopSearch} />
          </div>
          {!loading && cancelledMessage && (
            <p role="status" className="mt-3 text-sm text-slate-600">
              {cancelledMessage}
            </p>
          )}
          <div className="mt-6 flex flex-wrap justify-center gap-2">
            <span className="text-sm text-slate-500">Try:</span>
            {EXAMPLE_QUERIES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => submit(q)}
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-sm text-slate-700 hover:border-navy-600 hover:text-navy-800"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center font-serif text-2xl text-navy-900">How it works</h2>
        <div className="mt-10 grid gap-6 md:grid-cols-3">
          {STEPS.map((s, i) => (
            <div key={s.title} className="rounded-lg border border-slate-200 bg-white p-6">
              <span className="font-serif text-2xl text-navy-600">{i + 1}</span>
              <h3 className="mt-2 font-medium text-slate-900">{s.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{s.text}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
