import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, getProfessorProfile } from "../api/client";
import ProfessorContactCard from "../components/ProfessorContactCard";
import { useApplications } from "../context/ApplicationsContext";
import { useSearch } from "../context/SearchContext";
import type { ProfessorProfile, ProfessorProfileProject, ProfessorProfilePublication } from "../types/api";

const PROJECT_CATEGORY_LABELS: Record<string, string> = {
  sponsored_research: "Sponsored Research",
  industrial_consultancy: "Industrial Consultancy",
  routine_testing_vetting: "Testing & Vetting",
  administrative_or_grant: "Administrative / Grant",
};

function ProfileSkeleton() {
  return (
    <div className="mx-auto max-w-4xl animate-pulse space-y-6 px-6 py-10">
      <div className="h-4 w-40 rounded bg-slate-200" />
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="h-7 w-1/2 rounded bg-slate-200" />
        <div className="mt-2 h-4 w-1/3 rounded bg-slate-100" />
        <div className="mt-4 flex gap-3">
          <div className="h-9 w-36 rounded bg-slate-200" />
          <div className="h-9 w-36 rounded bg-slate-100" />
          <div className="h-9 w-40 rounded bg-slate-100" />
        </div>
      </div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="h-5 w-1/4 rounded bg-slate-200" />
          <div className="mt-3 h-3 w-full rounded bg-slate-100" />
          <div className="mt-2 h-3 w-5/6 rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

function PublicationEntry({
  pub,
  expanded,
  onToggleAbstract,
}: {
  pub: ProfessorProfilePublication;
  expanded: boolean;
  onToggleAbstract: () => void;
}) {
  const doiUrl = pub.doi ? (pub.doi.startsWith("http") ? pub.doi : `https://doi.org/${pub.doi}`) : null;
  const primaryLink = pub.paper_url || doiUrl || pub.source_url;

  return (
    <li className="py-3.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {pub.is_unverified ? (
          <span className="rounded bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">
            Unverified ({pub.verification_status})
          </span>
        ) : (
          <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200">
            Verified
          </span>
        )}
        {pub.publication_year && <span className="text-xs font-medium text-slate-600">{pub.publication_year}</span>}
        {pub.journal_or_conference && <span className="text-xs text-slate-500">· {pub.journal_or_conference}</span>}
        {pub.citation_count > 0 && <span className="text-xs text-slate-500">· {pub.citation_count} citations</span>}
        {pub.is_unverified && pub.confidence_score != null && (
          <span className="text-xs text-amber-700">· Confidence: {Math.round(pub.confidence_score * 100)}%</span>
        )}
      </div>

      <p className="mt-1.5 font-medium text-slate-900">
        {primaryLink ? (
          <a href={primaryLink} target="_blank" rel="noreferrer" className="hover:text-navy-700 hover:underline">
            {pub.title}
          </a>
        ) : (
          pub.title
        )}
      </p>

      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-slate-600">
        {doiUrl && (
          <a href={doiUrl} target="_blank" rel="noreferrer" className="text-navy-700 hover:underline">
            DOI
          </a>
        )}
        {pub.paper_url && pub.paper_url !== doiUrl && (
          <a href={pub.paper_url} target="_blank" rel="noreferrer" className="text-navy-700 hover:underline">
            Paper Link
          </a>
        )}
        {pub.source_url && pub.source_url !== primaryLink && (
          <a href={pub.source_url} target="_blank" rel="noreferrer" className="text-navy-700 hover:underline">
            Source ({pub.source_name || "record"})
          </a>
        )}
        {pub.abstract && (
          <button
            type="button"
            onClick={onToggleAbstract}
            className="font-medium text-navy-700 hover:underline"
          >
            {expanded ? "Hide Abstract" : "Read Abstract"}
          </button>
        )}
        {!pub.abstract && <span className="italic text-slate-400">Abstract unavailable</span>}
      </div>

      {pub.abstract && expanded && (
        <p className="mt-2 rounded bg-slate-50 p-3 text-xs leading-relaxed text-slate-700">{pub.abstract}</p>
      )}
    </li>
  );
}

function ProjectEntry({ proj }: { proj: ProfessorProfileProject }) {
  return (
    <li className="py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
          {PROJECT_CATEGORY_LABELS[proj.category] ?? proj.category}
        </span>
        {proj.role && <span className="text-xs text-slate-600">{proj.role}</span>}
        {proj.status && <span className="text-xs capitalize text-slate-500">· {proj.status}</span>}
      </div>
      <p className="mt-1 font-medium text-slate-900">
        {proj.source_url ? (
          <a href={proj.source_url} target="_blank" rel="noreferrer" className="hover:text-navy-700 hover:underline">
            {proj.title}
          </a>
        ) : (
          proj.title
        )}
      </p>
      {proj.sponsor && <p className="mt-0.5 text-xs text-slate-600">Sponsor: {proj.sponsor}</p>}
      {proj.description && !proj.description.startsWith("Sponsor:") && (
        <p className="mt-1 text-xs leading-relaxed text-slate-600">{proj.description}</p>
      )}
    </li>
  );
}

export default function ProfessorProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { query, universityId } = useSearch();
  const { ensureApplication } = useApplications();

  const [profile, setProfile] = useState<ProfessorProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [bioExpanded, setBioExpanded] = useState(false);
  const [showAdminProjects, setShowAdminProjects] = useState(false);
  const [expandedAbstracts, setExpandedAbstracts] = useState<Set<number>>(() => new Set());

  const professorId = id && /^\d+$/.test(id) ? Number(id) : NaN;

  const loadProfile = useCallback(
    (bypassCache = false) => {
      if (!Number.isInteger(professorId) || professorId <= 0) {
        setLoading(false);
        setProfile(null);
        setError(new ApiError("not_found", "Professor not found.", 404));
        return () => {};
      }
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      getProfessorProfile(professorId, { signal: controller.signal, bypassCache })
        .then((data) => {
          if (!controller.signal.aborted) {
            setProfile(data);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (controller.signal.aborted) return;
          setProfile(null);
          setError(err instanceof ApiError ? err : new ApiError("unknown", "Failed to load professor profile."));
          setLoading(false);
        });
      return () => controller.abort();
    },
    [professorId],
  );

  useEffect(() => {
    setBioExpanded(false);
    setShowAdminProjects(false);
    setExpandedAbstracts(new Set());
    return loadProfile(false);
  }, [loadProfile]);

  const toggleAbstract = (pubId: number) => {
    setExpandedAbstracts((prev) => {
      const next = new Set(prev);
      if (next.has(pubId)) next.delete(pubId);
      else next.add(pubId);
      return next;
    });
  };

  const backHref = query
    ? `/results?q=${encodeURIComponent(query)}${universityId ? `&university_id=${universityId}` : ""}`
    : "/";

  if (loading) return <ProfileSkeleton />;

  if (error?.kind === "not_found") {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 text-center">
        <h1 className="font-serif text-3xl text-navy-900">Professor not found</h1>
        <p className="mt-3 text-sm text-slate-600">
          We could not find an indexed faculty profile for ID #{id}.
        </p>
        <div className="mt-6">
          <Link to={backHref} className="rounded-md bg-navy-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-navy-700">
            {query ? "Back to Search Results" : "Back to Search"}
          </Link>
        </div>
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-20 text-center">
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-8 text-red-900">
          <h1 className="font-serif text-xl">Could not load professor profile</h1>
          <p className="mt-2 text-sm">{error?.message || "An unexpected error occurred."}</p>
          <div className="mt-5 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => loadProfile(true)}
              className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-700"
            >
              Retry
            </button>
            <Link
              to={backHref}
              className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {query ? "Back to Search Results" : "Back to Search"}
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const primaryProjects = profile.research_projects.filter((p) => !p.is_administrative_or_grant);
  const adminProjects = profile.research_projects.filter((p) => p.is_administrative_or_grant);
  const bioIsLong = (profile.biography?.length ?? 0) > 650;
  const displayedBio =
    profile.biography && bioIsLong && !bioExpanded ? `${profile.biography.slice(0, 650).trimEnd()}…` : profile.biography;
  const builderNavState = {
    professorId: profile.professor_id,
    professorName: profile.name,
    department: profile.department_name || profile.department_code || "",
    university: profile.university_name || "",
  };
  const researchGroupIsUrl = Boolean(profile.research_group && /^https?:\/\//i.test(profile.research_group.trim()));

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      {/* Back navigation */}
      <div className="mb-5">
        <Link to={backHref} className="inline-flex items-center gap-1.5 text-sm font-medium text-navy-700 hover:underline">
          <span>←</span>
          <span>{query ? `Back to results for “${query}”` : "Back to Discover Professors"}</span>
        </Link>
      </div>

      {/* Profile Header */}
      <header className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="font-serif text-3xl text-navy-900">{profile.name}</h1>
            {profile.designation && <p className="mt-1 text-base text-slate-700">{profile.designation}</p>}
            <p className="mt-1 text-sm text-slate-600">
              {profile.department_name || "Department unavailable"}
              {profile.department_code ? ` (${profile.department_code})` : ""}
              {profile.university_name ? ` · ${profile.university_name}` : ""}
            </p>
          </div>
          {profile.verification_status && (
            <span className="rounded bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700 ring-1 ring-slate-200">
              Profile: {profile.verification_status.replace("_", " ")}
            </span>
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-sm text-slate-600">
          {profile.email && (
            <a href={`mailto:${profile.email}`} className="text-navy-700 hover:underline">
              {profile.email}
            </a>
          )}
          {profile.orcid && <span>ORCID: {profile.orcid}</span>}
          {profile.irins_id && <span>IRINS: {profile.irins_id}</span>}
        </div>

        {/* Three Prominent Action Buttons */}
        <div className="mt-6 flex flex-wrap gap-3 border-t border-slate-100 pt-5">
          {profile.profile_url ? (
            <a
              href={profile.profile_url}
              target="_blank"
              rel="noreferrer"
              className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-700"
            >
              Official Website ↗
            </a>
          ) : (
            <button
              type="button"
              disabled
              className="cursor-not-allowed rounded-md bg-slate-200 px-4 py-2 text-sm font-medium text-slate-500"
            >
              Official Website Unavailable
            </button>
          )}

          <button
            type="button"
            onClick={() => {
              ensureApplication(builderNavState);
              navigate(`/applications/${profile.professor_id}?tab=resume`, { state: builderNavState });
            }}
            className="rounded-md border border-navy-700 bg-white px-4 py-2 text-sm font-medium text-navy-800 hover:bg-navy-50"
          >
            Create Tailored Resume
          </button>

          <button
            type="button"
            onClick={() => {
              ensureApplication(builderNavState);
              navigate(`/applications/${profile.professor_id}?tab=cover-letter`, { state: builderNavState });
            }}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Create Cover Letter
          </button>

          <button
            type="button"
            onClick={() => {
              ensureApplication(builderNavState);
              navigate(`/applications/${profile.professor_id}?tab=outreach`, { state: builderNavState });
            }}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            Generate Outreach Email
          </button>
        </div>
      </header>

      <div className="mt-6 space-y-6">
        {/* Dedicated Contact Information Card */}
        <ProfessorContactCard profile={profile} />

        {/* About Section */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="font-serif text-xl text-navy-900">About</h2>
          {displayedBio ? (
            <div className="mt-3">
              <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700">{displayedBio}</p>
              {bioIsLong && (
                <button
                  type="button"
                  onClick={() => setBioExpanded((v) => !v)}
                  className="mt-2 text-xs font-medium text-navy-700 hover:underline"
                >
                  {bioExpanded ? "Show Less" : "Read Full Biography"}
                </button>
              )}
            </div>
          ) : (
            <p className="mt-2 text-sm italic text-slate-500">No biography is listed in the official profile record.</p>
          )}

          {profile.educational_background && (
            <div className="mt-4 border-t border-slate-100 pt-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Educational Background</h3>
              <p className="mt-1 whitespace-pre-line text-sm text-slate-700">{profile.educational_background}</p>
            </div>
          )}
        </section>

        {/* Research Interests Section */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="font-serif text-xl text-navy-900">Research Interests</h2>
          {profile.research_interests ? (
            <p className="mt-3 text-sm leading-relaxed text-slate-700">{profile.research_interests}</p>
          ) : (
            <p className="mt-2 text-sm italic text-slate-500">No explicit research interests recorded.</p>
          )}

          {profile.research_group && (
            <p className="mt-3 text-sm text-slate-700">
              <span className="font-medium text-slate-900">Research Group: </span>
              {researchGroupIsUrl ? (
                <a
                  href={profile.research_group.trim()}
                  target="_blank"
                  rel="noreferrer"
                  className="text-navy-700 hover:underline"
                >
                  {profile.research_group.trim()}
                </a>
              ) : (
                profile.research_group
              )}
            </p>
          )}

          {profile.research_topics.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {profile.research_topics.map((t) => (
                <span
                  key={t.id}
                  className="rounded-full bg-navy-50 px-3 py-1 text-xs font-medium text-navy-800 ring-1 ring-navy-100"
                >
                  {t.canonical_topic_name || t.topic_name}
                </span>
              ))}
            </div>
          )}
        </section>

        {/* Research Projects Section */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="flex items-baseline justify-between">
            <h2 className="font-serif text-xl text-navy-900">Research Projects</h2>
            <span className="text-xs text-slate-500">{primaryProjects.length} research project(s)</span>
          </div>

          {primaryProjects.length > 0 ? (
            <ul className="mt-3 divide-y divide-slate-100">
              {primaryProjects.map((p) => (
                <ProjectEntry key={`${p.project_id}-${p.role ?? ""}`} proj={p} />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm italic text-slate-500">No sponsored or consultancy research projects recorded.</p>
          )}

          {adminProjects.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-4">
              <button
                type="button"
                onClick={() => setShowAdminProjects((v) => !v)}
                className="text-xs font-medium text-slate-600 hover:text-navy-800 hover:underline"
              >
                {showAdminProjects
                  ? `Hide Administrative & Grant Records (${adminProjects.length})`
                  : `Show Administrative & Grant Records (${adminProjects.length})`}
              </button>
              {showAdminProjects && (
                <ul className="mt-2 divide-y divide-slate-100">
                  {adminProjects.map((p) => (
                    <ProjectEntry key={`${p.project_id}-${p.role ?? ""}`} proj={p} />
                  ))}
                </ul>
              )}
            </div>
          )}
        </section>

        {/* Verified Publications Section */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="flex items-baseline justify-between">
            <h2 className="font-serif text-xl text-navy-900">Verified Publications</h2>
            <span className="text-xs text-slate-500">{profile.verified_publications.length} verified</span>
          </div>

          {profile.verified_publications.length > 0 ? (
            <ul className="mt-3 divide-y divide-slate-100">
              {profile.verified_publications.map((pub) => (
                <PublicationEntry
                  key={pub.publication_id}
                  pub={pub}
                  expanded={expandedAbstracts.has(pub.publication_id)}
                  onToggleAbstract={() => toggleAbstract(pub.publication_id)}
                />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm italic text-slate-500">
              No publications with verified authorship are currently recorded for this professor.
            </p>
          )}
        </section>

        {/* Unverified Candidate Publications Section (Strictly Separate) */}
        <section className="rounded-lg border border-amber-200 bg-white p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="font-serif text-xl text-navy-900">Unverified Candidate Publications</h2>
            <span className="text-xs text-amber-800">{profile.candidate_publications.length} candidate(s)</span>
          </div>

          <div className="mt-3 rounded-md bg-amber-50 px-4 py-2.5 text-xs text-amber-900 ring-1 ring-amber-200">
            <strong>Authorship not yet verified.</strong> These candidate publication links were matched automatically and
            have not undergone manual authorship confirmation.
          </div>

          {profile.candidate_publications.length > 0 ? (
            <ul className="mt-3 divide-y divide-slate-100">
              {profile.candidate_publications.map((pub) => (
                <PublicationEntry
                  key={pub.publication_id}
                  pub={pub}
                  expanded={expandedAbstracts.has(pub.publication_id)}
                  onToggleAbstract={() => toggleAbstract(pub.publication_id)}
                />
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm italic text-slate-500">No unverified candidate publications recorded.</p>
          )}
        </section>
      </div>
    </div>
  );
}
