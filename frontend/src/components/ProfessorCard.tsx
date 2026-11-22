import { Link } from "react-router-dom";
import type { SearchProfessorResult, SupportingEvidence } from "../types/api";
import { EVIDENCE_LABELS, MatchBadge, VerificationBadge } from "./Badges";

const GROUP_ORDER: Array<{ key: string; label: string }> = [
  { key: "exact_topic_publication", label: "Publications relevant to this query" },
  { key: "other_domain_publication", label: "Other AI / domain publications" },
  { key: "research_interest", label: "Official research interests" },
  { key: "research_project", label: "Research projects" },
  { key: "candidate_publication", label: "Unverified candidate publications" },
  { key: "biography", label: "Biography" },
];

function resolveGroupKey(ev: SupportingEvidence): string {
  if (ev.relevance_group) return ev.relevance_group;
  if (ev.evidence_type === "verified_publication") return "exact_topic_publication";
  return ev.evidence_type;
}

function getOneLineSummary(prof: SearchProfessorResult): string {
  const bio = (prof.biography || "").replace(/\s+/g, " ").trim();
  if (bio) return bio;
  const interests = (prof.research_interests || "").replace(/\s+/g, " ").trim();
  if (interests) return `Research interests: ${interests}`;
  return "No biography available in official profile.";
}

interface Props {
  prof: SearchProfessorResult;
  expanded: boolean;
  onToggle: () => void;
}

export default function ProfessorCard({ prof, expanded, onToggle }: Props) {
  const oneLineSummary = getOneLineSummary(prof);
  const isBroadDomainOnly = prof.explanation.startsWith("Broader AI/domain match");
  const displayCategory = isBroadDomainOnly ? "broad_domain" : prof.match_category;

  // Defer grouping/rendering detailed evidence until expanded for smooth browsing of 50-100+ cards
  const sections = expanded
    ? (() => {
        const grouped = new Map<string, SupportingEvidence[]>();
        for (const ev of prof.supporting_evidence) {
          const key = resolveGroupKey(ev);
          const list = grouped.get(key) ?? [];
          if (list.length < 3) {
            list.push(ev);
            grouped.set(key, list);
          }
        }
        return GROUP_ORDER.map((g) => ({ ...g, items: grouped.get(g.key) ?? [] })).filter((g) => g.items.length > 0);
      })()
    : [];

  return (
    <article className="rounded-lg border border-slate-200 bg-white px-5 py-4 shadow-sm transition-colors hover:border-slate-300">
      {/* Compact collapsed header */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h3 className="font-serif text-lg font-medium text-navy-900">{prof.professor_name}</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            {prof.department_name || prof.department}
            {prof.designation ? ` · ${prof.designation}` : ""}
          </p>
          {!expanded && (
            <p className="mt-2 truncate text-sm text-slate-500" title={oneLineSummary}>
              {oneLineSummary}
            </p>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 sm:pt-0.5">
          <MatchBadge category={displayCategory} />
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3.5 py-1.5 text-sm font-medium text-navy-800 hover:bg-slate-50"
          >
            <span>{expanded ? "Show Less" : "View Details"}</span>
            <svg
              className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
              aria-hidden="true"
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded details — rendered only when expanded */}
      {expanded && (
        <div className="mt-4 border-t border-slate-200 pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <MatchBadge category={prof.match_category} />
            {prof.email && <span className="text-xs text-slate-500">{prof.email}</span>}
          </div>

          {prof.biography && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Biography</h4>
              <p className="mt-1 whitespace-pre-line text-sm leading-relaxed text-slate-700">{prof.biography}</p>
            </div>
          )}

          {prof.research_interests && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Research interests</h4>
              <p className="mt-1 text-sm text-slate-700">{prof.research_interests}</p>
            </div>
          )}

          <div className="mt-4 rounded-md bg-navy-50 px-4 py-3 text-sm text-navy-800">
            <span className="font-medium">Why recommended: </span>
            {prof.explanation}
          </div>

          {sections.length > 0 && (
            <div className="mt-4 space-y-4">
              {sections.map((sec) => (
                <div key={sec.key}>
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">{sec.label}</h4>
                  <ul className="mt-1.5 divide-y divide-slate-100">
                    {sec.items.map((ev, i) => (
                      <li key={ev.evidence_id ?? i} className="py-2 text-sm">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs text-slate-500">
                            {EVIDENCE_LABELS[ev.evidence_type] ?? ev.evidence_type}
                          </span>
                          <VerificationBadge evidenceType={ev.evidence_type} status={ev.verification_status} />
                        </div>
                        <p className="mt-1 text-slate-800">
                          {ev.source_url ? (
                            <a href={ev.source_url} target="_blank" rel="noreferrer" className="hover:underline">
                              {ev.title || "Untitled evidence"}
                            </a>
                          ) : (
                            ev.title || "Untitled evidence"
                          )}
                        </p>
                        {ev.topic_relevance_note && (
                          <p className="text-xs italic text-amber-700">{ev.topic_relevance_note}</p>
                        )}
                        {ev.authorship_note && <p className="text-xs italic text-amber-700">{ev.authorship_note}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              to={`/professors/${prof.professor_id}`}
              className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-700"
            >
              Open Full Profile
            </Link>
            {prof.profile_url && (
              <a
                href={prof.profile_url}
                target="_blank"
                rel="noreferrer"
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
              >
                Official IIT KGP page
              </a>
            )}
          </div>
        </div>
      )}
    </article>
  );
}
