import { Link, useLocation, useParams, useSearchParams } from "react-router-dom";

interface BuilderLocationState {
  professorId?: number;
  professorName?: string;
  department?: string;
  university?: string;
}

export function PlaceholderPage({ title, description }: { title: string; description: string }) {
  return (
    <div className="mx-auto max-w-3xl px-6 py-20 text-center">
      <h1 className="font-serif text-3xl text-navy-900">{title}</h1>
      <p className="mt-4 text-slate-600">{description}</p>
      <p className="mt-6 inline-block rounded bg-slate-100 px-3 py-1 text-xs uppercase tracking-wider text-slate-500">Coming soon</p>
    </div>
  );
}

export function BuilderPlaceholderPage({ title, description }: { title: string; description: string }) {
  const [params] = useSearchParams();
  const location = useLocation();
  const state = (location.state as BuilderLocationState | null) ?? null;
  const profId = state?.professorId ?? (params.get("professor_id") ? Number(params.get("professor_id")) : null);

  return (
    <div className="mx-auto max-w-3xl px-6 py-20 text-center">
      <h1 className="font-serif text-3xl text-navy-900">{title}</h1>
      <p className="mt-4 text-slate-600">{description}</p>
      {profId && (
        <div className="mx-auto mt-6 max-w-md rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
          <p className="font-medium text-navy-900">
            Selected professor: {state?.professorName || `Professor #${profId}`}
          </p>
          {state?.department && <p className="mt-0.5 text-xs text-slate-500">{state.department}</p>}
          <Link to={`/professors/${profId}`} className="mt-2 inline-block text-xs font-medium text-navy-700 hover:underline">
            ← Return to Professor Profile
          </Link>
        </div>
      )}
      <p className="mt-6 inline-block rounded bg-slate-100 px-3 py-1 text-xs uppercase tracking-wider text-slate-500">Coming soon</p>
    </div>
  );
}

export function ProfessorProfilePlaceholder() {
  const { id } = useParams();
  return (
    <PlaceholderPage
      title="Professor profile"
      description={`The detailed profile view for professor #${id} will be available in the next release.`}
    />
  );
}

export function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="font-serif text-3xl text-navy-900">About ScholarLink</h1>
      <p className="mt-4 text-slate-700">
        ScholarLink helps students at IIT Kharagpur discover faculty whose research matches their interests. Recommendations
        are grounded in official faculty profiles, research projects, biographies and publication records.
      </p>
      <p className="mt-4 text-slate-700">
        Publications whose authorship has not yet been confirmed are always labelled <em>Unverified</em>. Every recommendation
        includes an explanation and links to its sources so you can judge the match yourself.
      </p>
    </div>
  );
}

export function NotFoundPage() {
  return <PlaceholderPage title="Page not found" description="The page you are looking for does not exist." />;
}
