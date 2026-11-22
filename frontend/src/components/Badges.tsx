const MATCH_STYLES: Record<string, string> = {
  strong: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  related: "bg-sky-50 text-sky-800 ring-sky-200",
  limited: "bg-amber-50 text-amber-800 ring-amber-200",
  broad_domain: "bg-slate-100 text-slate-700 ring-slate-200",
};

const MATCH_LABELS: Record<string, string> = {
  strong: "Strong match",
  related: "Relevant match",
  limited: "Limited match",
  broad_domain: "Broad domain match",
};

export function MatchBadge({ category }: { category: string }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-medium ring-1 ${MATCH_STYLES[category] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>
      {MATCH_LABELS[category] ?? category}
    </span>
  );
}

export function isUnverifiedEvidence(evidenceType: string, status: string | null): boolean {
  return evidenceType === "candidate_publication" || (status !== null && status !== "verified");
}

export function VerificationBadge({ evidenceType, status }: { evidenceType: string; status: string | null }) {
  return isUnverifiedEvidence(evidenceType, status) ? (
    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800 ring-1 ring-amber-200">Unverified</span>
  ) : (
    <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200">Verified</span>
  );
}

export const EVIDENCE_LABELS: Record<string, string> = {
  verified_publication: "Publication",
  candidate_publication: "Possible publication",
  research_interest: "Research interests",
  research_project: "Research project",
  biography: "Biography",
};
