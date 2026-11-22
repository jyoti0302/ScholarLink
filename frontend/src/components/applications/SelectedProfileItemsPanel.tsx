import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  countSelectedItems,
  toggleSelectedId,
  type ApplicationProfileSelections,
} from "../../context/ApplicationsContext";
import type { StudentCompleteProfile } from "../../types/api";

interface SelectedProfileItemsPanelProps {
  professorName: string;
  profile: StudentCompleteProfile;
  savedSelections: ApplicationProfileSelections;
  onSaveSelections: (selections: ApplicationProfileSelections) => void;
}

const SKILL_CATEGORY_LABELS: Record<string, string> = {
  technical: "Technical",
  tool: "Tool / Framework",
  language: "Language",
  research: "Research",
};

function selectionsEqual(a: ApplicationProfileSelections, b: ApplicationProfileSelections): boolean {
  const eqArr = (x: number[], y: number[]) =>
    x.length === y.length && [...x].sort((m, n) => m - n).every((val, i) => val === [...y].sort((m, n) => m - n)[i]);
  return (
    a.includeResearchInterests === b.includeResearchInterests &&
    eqArr(a.projectIds, b.projectIds) &&
    eqArr(a.researchExperienceIds, b.researchExperienceIds) &&
    eqArr(a.technicalSkillIds, b.technicalSkillIds) &&
    eqArr(a.researchSkillIds, b.researchSkillIds) &&
    eqArr(a.experienceIds, b.experienceIds) &&
    eqArr(a.achievementIds, b.achievementIds) &&
    eqArr(a.publicationIds, b.publicationIds)
  );
}

function formatDuration(start?: string | null, end?: string | null): string | null {
  const parts = [start?.trim(), end?.trim()].filter(Boolean);
  return parts.length > 0 ? parts.join(" – ") : null;
}

export default function SelectedProfileItemsPanel({
  professorName,
  profile,
  savedSelections,
  onSaveSelections,
}: SelectedProfileItemsPanelProps) {
  const [draft, setDraft] = useState<ApplicationProfileSelections>(savedSelections);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);

  useEffect(() => {
    setDraft(savedSelections);
  }, [savedSelections]);

  const projects = useMemo(
    () => profile.projects.filter((p) => p.entry_type === "project"),
    [profile.projects],
  );
  const researchExperiences = useMemo(
    () => profile.projects.filter((p) => p.entry_type === "research_experience"),
    [profile.projects],
  );
  const technicalSkills = useMemo(
    () => profile.skills.filter((s) => s.category !== "research"),
    [profile.skills],
  );
  const researchSkills = useMemo(
    () => profile.skills.filter((s) => s.category === "research"),
    [profile.skills],
  );

  // Filter saved/draft IDs to currently existing profile items for accurate live counts
  const validProjectIds = useMemo(() => new Set(projects.map((p) => p.id)), [projects]);
  const validResearchExpIds = useMemo(() => new Set(researchExperiences.map((p) => p.id)), [researchExperiences]);
  const validTechSkillIds = useMemo(() => new Set(technicalSkills.map((s) => s.id)), [technicalSkills]);
  const validResearchSkillIds = useMemo(() => new Set(researchSkills.map((s) => s.id)), [researchSkills]);
  const validExpIds = useMemo(() => new Set(profile.experiences.map((e) => e.id)), [profile.experiences]);
  const validAchIds = useMemo(() => new Set(profile.achievements.map((a) => a.id)), [profile.achievements]);
  const validPubIds = useMemo(() => new Set(profile.publications.map((p) => p.id)), [profile.publications]);

  const cleanedDraft: ApplicationProfileSelections = useMemo(
    () => ({
      projectIds: draft.projectIds.filter((id) => validProjectIds.has(id)),
      researchExperienceIds: draft.researchExperienceIds.filter((id) => validResearchExpIds.has(id)),
      technicalSkillIds: draft.technicalSkillIds.filter((id) => validTechSkillIds.has(id)),
      researchSkillIds: draft.researchSkillIds.filter((id) => validResearchSkillIds.has(id)),
      includeResearchInterests:
        draft.includeResearchInterests && Boolean(profile.research_interests_summary?.trim()),
      experienceIds: draft.experienceIds.filter((id) => validExpIds.has(id)),
      achievementIds: draft.achievementIds.filter((id) => validAchIds.has(id)),
      publicationIds: draft.publicationIds.filter((id) => validPubIds.has(id)),
    }),
    [
      draft,
      validProjectIds,
      validResearchExpIds,
      validTechSkillIds,
      validResearchSkillIds,
      validExpIds,
      validAchIds,
      validPubIds,
      profile.research_interests_summary,
    ],
  );

  const totalSelected = countSelectedItems(cleanedDraft);
  const hasUnsavedChanges = !selectionsEqual(cleanedDraft, savedSelections);

  function handleSave() {
    onSaveSelections(cleanedDraft);
    setSaveNotice(
      `Saved ${totalSelected} selected item${totalSelected === 1 ? "" : "s"} for ${professorName}. Your master Academic Profile was not modified.`,
    );
  }

  const updateDraft = (updater: (prev: ApplicationProfileSelections) => ApplicationProfileSelections) => {
    setSaveNotice(null);
    setDraft(updater);
  };

  return (
    <div className="space-y-6">
      {/* Header + Live Selection Summary + Save Action */}
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <h2 className="font-serif text-xl text-navy-900">Selected Profile Items</h2>
          <p className="mt-1 text-sm text-slate-600">
            Select items from your master Academic Profile to highlight for{" "}
            <span className="font-medium text-slate-800">{professorName}</span>. Selections are isolated to this
            professor and will feed into tailored resumes, cover letters, and outreach emails.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {hasUnsavedChanges && (
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200">
              Unsaved changes
            </span>
          )}
          <button
            type="button"
            onClick={handleSave}
            className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
          >
            Save Selections
          </button>
        </div>
      </div>

      {saveNotice && (
        <div
          role="status"
          className="flex items-center justify-between rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-900"
        >
          <span>{saveNotice}</span>
          <button
            type="button"
            onClick={() => setSaveNotice(null)}
            className="ml-3 text-xs font-medium opacity-70 hover:opacity-100"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Live Selection Counts */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <div className="rounded-md border border-navy-200 bg-navy-50/50 p-3">
          <p className="text-[11px] font-medium uppercase tracking-wide text-navy-700">Total Selected</p>
          <p className="mt-0.5 text-lg font-semibold text-navy-900">{totalSelected}</p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Projects</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.projectIds.length} / {projects.length}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Technical Skills</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.technicalSkillIds.length} / {technicalSkills.length}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Research Skills &amp; Interests</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.researchSkillIds.length + (cleanedDraft.includeResearchInterests ? 1 : 0)} /{" "}
            {researchSkills.length + (profile.research_interests_summary?.trim() ? 1 : 0)}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Research Experience</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.researchExperienceIds.length} / {researchExperiences.length}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Internships &amp; Work</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.experienceIds.length} / {profile.experiences.length}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Achievements &amp; Certs</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.achievementIds.length} / {profile.achievements.length}
          </p>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50/70 p-3">
          <p className="text-[11px] text-slate-500">Publications</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-900">
            {cleanedDraft.publicationIds.length} / {profile.publications.length}
          </p>
        </div>
      </div>

      {/* 1. Projects */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-serif text-lg text-navy-900">Projects ({cleanedDraft.projectIds.length} selected)</h3>
        </div>
        {projects.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No projects in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add projects in My Academic Profile
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {projects.map((proj) => {
              const checked = cleanedDraft.projectIds.includes(proj.id);
              const duration = formatDuration(proj.start_date, proj.end_date);
              return (
                <label
                  key={proj.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        projectIds: toggleSelectedId(prev.projectIds, proj.id),
                      }))
                    }
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1 space-y-1 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-medium text-navy-900">{proj.title}</span>
                      {duration && <span className="text-xs text-slate-500">{duration}</span>}
                    </div>
                    {proj.description && <p className="text-xs text-slate-700">{proj.description}</p>}
                    {(proj.role || proj.methodology) && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Individual Contribution:</span>{" "}
                        {[proj.role, proj.organization, proj.methodology].filter(Boolean).join(" — ")}
                      </p>
                    )}
                    {proj.technologies_tools && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Technologies:</span> {proj.technologies_tools}
                      </p>
                    )}
                    {proj.outcomes_results && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Outcomes &amp; Measurable Results:</span>{" "}
                        {proj.outcomes_results}
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* 2. Research Experience */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Research Experience ({cleanedDraft.researchExperienceIds.length} selected)
        </h3>
        {researchExperiences.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No research experience entries in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add research experience
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {researchExperiences.map((item) => {
              const checked = cleanedDraft.researchExperienceIds.includes(item.id);
              const duration = formatDuration(item.start_date, item.end_date);
              return (
                <label
                  key={item.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        researchExperienceIds: toggleSelectedId(prev.researchExperienceIds, item.id),
                      }))
                    }
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1 space-y-1 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-medium text-navy-900">{item.title}</span>
                      {duration && <span className="text-xs text-slate-500">{duration}</span>}
                    </div>
                    {(item.role || item.organization) && (
                      <p className="text-xs text-slate-600">
                        {[item.role, item.organization].filter(Boolean).join(" · ")}
                      </p>
                    )}
                    {item.description && <p className="text-xs text-slate-700">{item.description}</p>}
                    {item.methodology && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Methodology:</span> {item.methodology}
                      </p>
                    )}
                    {item.outcomes_results && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Findings &amp; Results:</span>{" "}
                        {item.outcomes_results}
                      </p>
                    )}
                    {item.technologies_tools && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Tools &amp; Techniques:</span>{" "}
                        {item.technologies_tools}
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* 3. Technical Skills */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Technical Skills ({cleanedDraft.technicalSkillIds.length} selected)
        </h3>
        {technicalSkills.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No technical skills in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add technical skills
            </Link>
            .
          </p>
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {technicalSkills.map((skill) => {
              const checked = cleanedDraft.technicalSkillIds.includes(skill.id);
              return (
                <label
                  key={skill.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        technicalSkillIds: toggleSelectedId(prev.technicalSkillIds, skill.id),
                      }))
                    }
                    className="mt-0.5 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-sm font-medium text-navy-900">{skill.name}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">
                        {SKILL_CATEGORY_LABELS[skill.category] || skill.category}
                      </span>
                      {skill.proficiency_level && (
                        <span className="text-[11px] text-slate-500">· {skill.proficiency_level}</span>
                      )}
                    </div>
                    {skill.experience_context && (
                      <p className="mt-1 text-xs text-slate-600">{skill.experience_context}</p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* 4. Research Skills and Interests */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Research Skills &amp; Interests (
          {cleanedDraft.researchSkillIds.length + (cleanedDraft.includeResearchInterests ? 1 : 0)} selected)
        </h3>
        {!profile.research_interests_summary?.trim() && researchSkills.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No research interests or research skills listed in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add research interests &amp; skills
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {profile.research_interests_summary?.trim() && (
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition ${
                  cleanedDraft.includeResearchInterests
                    ? "border-navy-600 bg-navy-50/30"
                    : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={cleanedDraft.includeResearchInterests}
                  onChange={() =>
                    updateDraft((prev) => ({
                      ...prev,
                      includeResearchInterests: !prev.includeResearchInterests,
                    }))
                  }
                  className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-navy-900">Research Interests Summary</p>
                  <p className="mt-1 whitespace-pre-line text-xs text-slate-700">
                    {profile.research_interests_summary}
                  </p>
                </div>
              </label>
            )}

            {researchSkills.length > 0 && (
              <div className="grid gap-2.5 sm:grid-cols-2">
                {researchSkills.map((skill) => {
                  const checked = cleanedDraft.researchSkillIds.includes(skill.id);
                  return (
                    <label
                      key={skill.id}
                      className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${
                        checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() =>
                          updateDraft((prev) => ({
                            ...prev,
                            researchSkillIds: toggleSelectedId(prev.researchSkillIds, skill.id),
                          }))
                        }
                        className="mt-0.5 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-medium text-navy-900">{skill.name}</span>
                          {skill.proficiency_level && (
                            <span className="text-[11px] text-slate-500">· {skill.proficiency_level}</span>
                          )}
                        </div>
                        {skill.experience_context && (
                          <p className="mt-1 text-xs text-slate-600">{skill.experience_context}</p>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 5. Internships and Work Experience */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Internships &amp; Work Experience ({cleanedDraft.experienceIds.length} selected)
        </h3>
        {profile.experiences.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No internships or work experience records in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add experience
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {profile.experiences.map((exp) => {
              const checked = cleanedDraft.experienceIds.includes(exp.id);
              const duration = formatDuration(exp.start_date, exp.end_date);
              return (
                <label
                  key={exp.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        experienceIds: toggleSelectedId(prev.experienceIds, exp.id),
                      }))
                    }
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1 space-y-1 text-sm">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="font-medium text-navy-900">
                        {exp.role} — {exp.organization}
                      </span>
                      {duration && <span className="text-xs text-slate-500">{duration}</span>}
                    </div>
                    {exp.location && <p className="text-xs text-slate-500">{exp.location}</p>}
                    {exp.responsibilities && (
                      <p className="text-xs text-slate-700">
                        <span className="font-semibold text-slate-700">Responsibilities:</span> {exp.responsibilities}
                      </p>
                    )}
                    {exp.achievements && (
                      <p className="text-xs text-slate-600">
                        <span className="font-semibold text-slate-700">Achievements:</span> {exp.achievements}
                      </p>
                    )}
                    {exp.technologies_used && (
                      <p className="text-xs text-slate-500">
                        <span className="font-medium text-slate-700">Technologies:</span> {exp.technologies_used}
                      </p>
                    )}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* 6. Achievements and Certifications */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Achievements &amp; Certifications ({cleanedDraft.achievementIds.length} selected)
        </h3>
        {profile.achievements.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No achievements or certifications in your Academic Profile yet.{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add achievements or certifications
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {profile.achievements.map((ach) => {
              const checked = cleanedDraft.achievementIds.includes(ach.id);
              return (
                <label
                  key={ach.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        achievementIds: toggleSelectedId(prev.achievementIds, ach.id),
                      }))
                    }
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1 space-y-0.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-navy-900">{ach.title}</span>
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] capitalize text-slate-600">
                        {ach.entry_type}
                      </span>
                      {ach.date_awarded && <span className="text-xs text-slate-500">{ach.date_awarded}</span>}
                    </div>
                    {ach.issuing_organization && (
                      <p className="text-xs text-slate-600">Issuer: {ach.issuing_organization}</p>
                    )}
                    {ach.description && <p className="text-xs text-slate-600">{ach.description}</p>}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* 7. Publications (if available) */}
      <section className="space-y-3">
        <h3 className="font-serif text-lg text-navy-900">
          Publications ({cleanedDraft.publicationIds.length} selected)
        </h3>
        {profile.publications.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-500">
            No publications in your Academic Profile yet (optional).{" "}
            <Link to="/profile" className="font-medium text-navy-700 hover:underline">
              Add publications
            </Link>
            .
          </p>
        ) : (
          <div className="space-y-2.5">
            {profile.publications.map((pub) => {
              const checked = cleanedDraft.publicationIds.includes(pub.id);
              return (
                <label
                  key={pub.id}
                  className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3.5 transition ${
                    checked ? "border-navy-600 bg-navy-50/30" : "border-slate-200 bg-white hover:border-slate-300"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      updateDraft((prev) => ({
                        ...prev,
                        publicationIds: toggleSelectedId(prev.publicationIds, pub.id),
                      }))
                    }
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-navy-800 focus:ring-navy-700"
                  />
                  <div className="min-w-0 flex-1 space-y-0.5 text-sm">
                    <p className="font-medium text-navy-900">{pub.title}</p>
                    {pub.authors && <p className="text-xs text-slate-600">{pub.authors}</p>}
                    {(pub.journal_or_conference || pub.publication_date) && (
                      <p className="text-xs text-slate-500">
                        {[pub.journal_or_conference, pub.publication_date].filter(Boolean).join(" · ")}
                      </p>
                    )}
                    {pub.abstract && <p className="text-xs text-slate-600">{pub.abstract}</p>}
                  </div>
                </label>
              );
            })}
          </div>
        )}
      </section>

      {/* Bottom Save Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
        <p className="text-xs text-slate-500">
          {totalSelected} item{totalSelected === 1 ? "" : "s"} selected for {professorName} · Stored locally per
          professor workspace without modifying your master Academic Profile.
        </p>
        <button
          type="button"
          onClick={handleSave}
          className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
        >
          Save Selections
        </button>
      </div>
    </div>
  );
}
