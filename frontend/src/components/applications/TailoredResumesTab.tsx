import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  exportTailoredResume,
  generateTailoredResume,
  getProfessorProfile,
} from "../../api/client";
import {
  countSelectedItems,
  type ApplicationDocumentVersion,
  type ApplicationProfileSelections,
  type NewResumeVersionInput,
  type ProfessorApplication,
  type UpdateResumeVersionInput,
} from "../../context/ApplicationsContext";
import type {
  ProfessorProfile,
  ResumeLength,
  ResumeSectionKey,
  ResumeTemplate,
  StudentCompleteProfile,
  TailoredResumeContent,
} from "../../types/api";
import { ConfirmDeleteModal } from "../profile/ProfileModal";
import ResumeEditorModal from "./ResumeEditorModal";

const ALL_SECTIONS: { key: ResumeSectionKey; label: string }[] = [
  { key: "summary", label: "Professional Summary" },
  { key: "education", label: "Education" },
  { key: "research_interests", label: "Research Interests" },
  { key: "skills", label: "Skills" },
  { key: "projects", label: "Projects" },
  { key: "research_experience", label: "Research Experience" },
  { key: "experience", label: "Internships & Work" },
  { key: "publications", label: "Publications" },
  { key: "achievements", label: "Achievements & Certs" },
];

const TEMPLATE_LABELS: Record<ResumeTemplate, string> = {
  academic_research: "Academic Research",
  modern_professional: "Modern Professional",
  technical_ai_ml: "Technical / AI-ML",
};

function formatTimestamp(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

interface TailoredResumesTabProps {
  application: ProfessorApplication;
  isAuthenticated: boolean;
  studentProfile: StudentCompleteProfile | null;
  studentProfileLoading: boolean;
  onJumpToSelections: () => void;
  onAddResumeVersion: (input: NewResumeVersionInput) => ApplicationDocumentVersion | null;
  onUpdateResumeVersion: (versionId: string, updates: UpdateResumeVersionInput) => void;
  onDuplicateResumeVersion: (versionId: string) => ApplicationDocumentVersion | null;
  onDeleteResumeVersion: (versionId: string) => void;
  onAuthExpired: () => void;
}

export default function TailoredResumesTab({
  application,
  isAuthenticated,
  studentProfile,
  studentProfileLoading,
  onJumpToSelections,
  onAddResumeVersion,
  onUpdateResumeVersion,
  onDuplicateResumeVersion,
  onDeleteResumeVersion,
  onAuthExpired,
}: TailoredResumesTabProps) {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [profContext, setProfContext] = useState<ProfessorProfile | null>(null);
  const [profLoading, setProfLoading] = useState(false);
  const [profError, setProfError] = useState<string | null>(null);

  // Preferences state (Step C)
  const [title, setTitle] = useState(`Tailored Resume for ${application.professorName}`);
  const [targetPosition, setTargetPosition] = useState("Undergraduate Research Intern");
  const [template, setTemplate] = useState<ResumeTemplate>("academic_research");
  const [preferredLength, setPreferredLength] = useState<ResumeLength>("1_page");
  const [includedSections, setIncludedSections] = useState<ResumeSectionKey[]>(ALL_SECTIONS.map((s) => s.key));
  const [additionalInstructions, setAdditionalInstructions] = useState("");

  // Generation & Export state
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [bannerNotice, setBannerNotice] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<"pdf" | "docx" | null>(null);

  // Editor / Preview / Delete modals
  const [editorState, setEditorState] = useState<{
    open: boolean;
    mode: "edit" | "preview";
    versionId: string | null;
  }>({ open: false, mode: "edit", versionId: null });
  const [deleteTarget, setDeleteTarget] = useState<ApplicationDocumentVersion | null>(null);

  const selectedCount = countSelectedItems(application.selections);
  const activeVersion =
    editorState.versionId != null
      ? application.resumeVersions.find((v) => v.id === editorState.versionId) ?? null
      : null;

  useEffect(() => {
    setTitle(`Tailored Resume for ${application.professorName}`);
  }, [application.professorName]);

  useEffect(() => {
    if (!wizardOpen || profContext) return;
    const ctrl = new AbortController();
    setProfLoading(true);
    setProfError(null);
    getProfessorProfile(application.professorId, { signal: ctrl.signal })
      .then((data) => setProfContext(data))
      .catch((err) => {
        if ((err as ApiError)?.kind !== "aborted") {
          setProfError(err instanceof Error ? err.message : "Could not load professor research details.");
        }
      })
      .finally(() => setProfLoading(false));
    return () => ctrl.abort();
  }, [wizardOpen, profContext, application.professorId]);

  function toggleIncludedSection(key: ResumeSectionKey) {
    setIncludedSections((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    );
  }

  async function handleGenerate() {
    setGenError(null);
    setBannerNotice(null);
    if (!title.trim()) {
      setGenError("Please enter a resume title.");
      return;
    }
    if (includedSections.length === 0) {
      setGenError("Please include at least one resume section.");
      return;
    }

    const sel: ApplicationProfileSelections = application.selections;
    setGenerating(true);
    try {
      const response = await generateTailoredResume(application.professorId, {
        selected_items: {
          project_ids: sel.projectIds,
          research_experience_ids: sel.researchExperienceIds,
          technical_skill_ids: sel.technicalSkillIds,
          research_skill_ids: sel.researchSkillIds,
          include_research_interests: sel.includeResearchInterests,
          experience_ids: sel.experienceIds,
          achievement_ids: sel.achievementIds,
          publication_ids: sel.publicationIds,
        },
        preferences: {
          title: title.trim(),
          target_position: targetPosition.trim() || null,
          template,
          preferred_length: preferredLength,
          included_sections: includedSections,
          additional_instructions: additionalInstructions.trim() || null,
        },
      });

      const created = onAddResumeVersion({
        title: response.content.title,
        targetPosition: response.content.target_position,
        template: response.content.template,
        preferredLength: response.content.preferred_length,
        generationMode: response.generation_mode,
        providerNotice: response.provider_notice,
        selectedSourceIds: sel,
        content: response.content,
      });

      setWizardOpen(false);
      if (response.provider_notice) {
        setBannerNotice(response.provider_notice);
      } else {
        setBannerNotice(`Generated tailored resume v${created?.version ?? 1} for ${application.professorName}.`);
      }
      if (created) {
        setEditorState({ open: true, mode: "edit", versionId: created.id });
      }
    } catch (err) {
      if (err instanceof ApiError && err.kind === "unauthorized") {
        onAuthExpired();
        return;
      }
      setGenError(err instanceof Error ? err.message : "Failed to generate tailored resume.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleExport(format: "pdf" | "docx", content: TailoredResumeContent, filename: string) {
    setExportingFormat(format);
    setGenError(null);
    try {
      const { blob, filename: serverFilename } = await exportTailoredResume(application.professorId, {
        format,
        template: content.template,
        filename,
        content,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = serverFilename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "unauthorized") {
        onAuthExpired();
        return;
      }
      setGenError(err instanceof Error ? err.message : `Failed to export ${format.toUpperCase()}.`);
    } finally {
      setExportingFormat(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
        <div>
          <h2 className="font-serif text-xl text-navy-900">Tailored Resumes</h2>
          <p className="mt-1 text-sm text-slate-600">
            Generate, edit, version, and export resumes tailored specifically for{" "}
            <span className="font-medium text-slate-800">{application.professorName}</span>.
          </p>
        </div>
        {isAuthenticated && (
          <button
            type="button"
            onClick={() => {
              setWizardOpen((prev) => !prev);
              setGenError(null);
            }}
            className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
          >
            {wizardOpen ? "Close Generator" : "+ Create New Resume"}
          </button>
        )}
      </div>

      {bannerNotice && (
        <div
          role="status"
          className="flex items-center justify-between rounded-md border border-sky-200 bg-sky-50 px-4 py-2.5 text-xs text-sky-900"
        >
          <span>{bannerNotice}</span>
          <button type="button" onClick={() => setBannerNotice(null)} className="ml-3 font-medium opacity-70">
            Dismiss
          </button>
        </div>
      )}

      {genError && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-800">
          {genError}
        </div>
      )}

      {!isAuthenticated ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-8 text-center">
          <p className="font-medium text-slate-900">Sign in to generate tailored resumes</p>
          <p className="mx-auto mt-1 max-w-md text-xs text-slate-600">
            Sign in with your student account to generate, edit, and export professor-specific resumes grounded in your
            Academic Profile.
          </p>
          <div className="mt-4 flex justify-center gap-3">
            <Link
              to="/login"
              state={{ from: { pathname: `/applications/${application.professorId}`, search: "?tab=resume" } }}
              className="rounded-md bg-navy-800 px-4 py-2 text-xs font-medium text-white hover:bg-navy-900"
            >
              Sign in
            </Link>
          </div>
        </div>
      ) : (
        <>
          {/* Guided Resume Generation Wizard */}
          {wizardOpen && (
            <div className="space-y-5 rounded-lg border border-navy-200 bg-slate-50/60 p-5">
              <div>
                <h3 className="font-serif text-lg text-navy-900">Guided Tailored Resume Generator</h3>
                <p className="text-xs text-slate-600">
                  Strictly grounded in your real Academic Profile — never invents projects, skills, dates, or metrics.
                </p>
              </div>

              {/* Step A — Confirm Selected Profile Items */}
              <div className="rounded-md border border-slate-200 bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-navy-800">
                      Step A · Selected Profile Items
                    </p>
                    <p className="mt-0.5 text-xs text-slate-600">
                      {studentProfileLoading
                        ? "Loading your Academic Profile..."
                        : `${selectedCount} item(s) selected for ${application.professorName} (${application.selections.projectIds.length} projects, ${application.selections.researchExperienceIds.length} research exp, ${application.selections.technicalSkillIds.length} tech skills, ${application.selections.researchSkillIds.length} research skills, ${application.selections.experienceIds.length} internships, ${application.selections.achievementIds.length} achievements, ${application.selections.publicationIds.length} publications).`}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={onJumpToSelections}
                    className="rounded border border-navy-700 px-3 py-1 text-xs font-medium text-navy-800 hover:bg-navy-50"
                  >
                    Adjust Selections
                  </button>
                </div>
                {studentProfile && selectedCount === 0 && (
                  <p className="mt-2 rounded bg-amber-50 px-3 py-1.5 text-xs text-amber-800">
                    Tip: Select relevant projects, skills, and experiences in Selected Profile Items first so your
                    generated resume highlights your strongest work for this professor.
                  </p>
                )}
              </div>

              {/* Step B — Professor Research Context */}
              <div className="rounded-md border border-slate-200 bg-white p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-navy-800">
                  Step B · Professor Research Context (Loaded Automatically)
                </p>
                {profLoading ? (
                  <p className="mt-2 text-xs text-slate-500">Loading {application.professorName}&apos;s research profile...</p>
                ) : profError ? (
                  <p className="mt-2 text-xs text-amber-700">
                    {profError} (Backend generation will still load {application.professorName}&apos;s profile directly
                    from PostgreSQL.)
                  </p>
                ) : profContext ? (
                  <div className="mt-2 space-y-1.5 text-xs text-slate-700">
                    <p className="font-medium text-slate-900">
                      {profContext.name}
                      {profContext.designation ? ` · ${profContext.designation}` : ""}
                      {profContext.department_name ? ` · ${profContext.department_name}` : ""}
                    </p>
                    {profContext.research_interests && (
                      <p>
                        <span className="font-semibold text-slate-800">Research Interests:</span>{" "}
                        {profContext.research_interests}
                      </p>
                    )}
                    <p className="text-slate-500">
                      Context available: {profContext.research_projects.length} research project(s),{" "}
                      {profContext.verified_publications.length} verified publication(s).
                    </p>
                  </div>
                ) : null}
              </div>

              {/* Step C — Resume Preferences */}
              <div className="rounded-md border border-slate-200 bg-white p-4 space-y-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-navy-800">
                  Step C · Resume Preferences
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-700">Resume Title *</label>
                    <input
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700">Target Position</label>
                    <input
                      type="text"
                      value={targetPosition}
                      onChange={(e) => setTargetPosition(e.target.value)}
                      placeholder="e.g. Summer Research Intern / BTP Student"
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700">Resume Template</label>
                    <select
                      value={template}
                      onChange={(e) => setTemplate(e.target.value as ResumeTemplate)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                    >
                      <option value="academic_research">Academic Research</option>
                      <option value="modern_professional">Modern Professional</option>
                      <option value="technical_ai_ml">Technical / AI-ML</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-700">Preferred Length</label>
                    <select
                      value={preferredLength}
                      onChange={(e) => setPreferredLength(e.target.value as ResumeLength)}
                      className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
                    >
                      <option value="1_page">1 Page (Concise)</option>
                      <option value="2_pages">2 Pages (Detailed)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700">Sections to Include</label>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {ALL_SECTIONS.map((sec) => {
                      const checked = includedSections.includes(sec.key);
                      return (
                        <label
                          key={sec.key}
                          className={`inline-flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                            checked
                              ? "border-navy-600 bg-navy-50 text-navy-900"
                              : "border-slate-200 bg-white text-slate-600"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleIncludedSection(sec.key)}
                            className="h-3 w-3 rounded border-slate-300 text-navy-800"
                          />
                          <span>{sec.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700">
                    Optional Additional Instructions
                  </label>
                  <textarea
                    rows={2}
                    value={additionalInstructions}
                    onChange={(e) => setAdditionalInstructions(e.target.value)}
                    placeholder="e.g. Emphasize transformer fine-tuning and evaluation methodology..."
                    className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-xs"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setWizardOpen(false)}
                    className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={generating}
                    onClick={() => void handleGenerate()}
                    className="rounded-md bg-navy-800 px-4 py-2 text-xs font-medium text-white hover:bg-navy-900 disabled:opacity-60"
                  >
                    {generating ? "Generating Tailored Resume..." : "Generate Tailored Resume"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Resume Versions List */}
          {application.resumeVersions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 p-8 text-center">
              <p className="font-medium text-slate-800">No tailored resume versions yet</p>
              <p className="mx-auto mt-1 max-w-md text-xs text-slate-600">
                Click <span className="font-medium text-slate-800">+ Create New Resume</span> to generate a resume
                tailored to {application.professorName}&apos;s research using your selected Academic Profile items.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {application.resumeVersions.map((ver) => (
                <article
                  key={ver.id}
                  className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded bg-navy-50 px-2 py-0.5 text-xs font-semibold text-navy-800">
                          v{ver.version}
                        </span>
                        <h3 className="font-medium text-navy-900">{ver.title}</h3>
                        <span
                          className={`rounded-full px-2 py-0.5 text-[11px] font-medium capitalize ring-1 ${
                            ver.status === "approved"
                              ? "bg-emerald-50 text-emerald-800 ring-emerald-200"
                              : "bg-amber-50 text-amber-800 ring-amber-200"
                          }`}
                        >
                          {ver.status}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        Template: {ver.template ? TEMPLATE_LABELS[ver.template] : "Academic Research"} · Created{" "}
                        {formatTimestamp(ver.createdAt ?? ver.updatedAt)} · Updated {formatTimestamp(ver.updatedAt)}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2 border-t border-slate-100 pt-3 text-xs">
                    <button
                      type="button"
                      disabled={!ver.content}
                      onClick={() => setEditorState({ open: true, mode: "preview", versionId: ver.id })}
                      className="rounded border border-slate-300 bg-white px-2.5 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Preview
                    </button>
                    <button
                      type="button"
                      disabled={!ver.content}
                      onClick={() => setEditorState({ open: true, mode: "edit", versionId: ver.id })}
                      className="rounded border border-navy-700 bg-white px-2.5 py-1 font-medium text-navy-800 hover:bg-navy-50 disabled:opacity-40"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        onDuplicateResumeVersion(ver.id);
                        setBannerNotice(`Duplicated "${ver.title}" as a new draft version.`);
                      }}
                      className="rounded border border-slate-300 bg-white px-2.5 py-1 font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Duplicate
                    </button>
                    <button
                      type="button"
                      disabled={!ver.content || exportingFormat !== null}
                      onClick={() =>
                        ver.content && void handleExport("pdf", ver.content, `${ver.title}_v${ver.version}`)
                      }
                      className="rounded border border-slate-300 bg-white px-2.5 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Download PDF
                    </button>
                    <button
                      type="button"
                      disabled={!ver.content || exportingFormat !== null}
                      onClick={() =>
                        ver.content && void handleExport("docx", ver.content, `${ver.title}_v${ver.version}`)
                      }
                      className="rounded border border-slate-300 bg-white px-2.5 py-1 font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Download DOCX
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(ver)}
                      className="ml-auto rounded border border-red-200 px-2.5 py-1 font-medium text-red-700 hover:bg-red-50"
                    >
                      Delete
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </>
      )}

      {/* Editor & Live Preview Modal */}
      <ResumeEditorModal
        open={editorState.open}
        mode={editorState.mode}
        version={activeVersion}
        professorName={application.professorName}
        exportingFormat={exportingFormat}
        onClose={() => setEditorState({ open: false, mode: "edit", versionId: null })}
        onSave={(versionId, updates) => onUpdateResumeVersion(versionId, updates)}
        onExport={(fmt, content, filename) => void handleExport(fmt, content, filename)}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmDeleteModal
        open={Boolean(deleteTarget)}
        itemLabel={deleteTarget ? `${deleteTarget.title} (v${deleteTarget.version})` : ""}
        deleting={false}
        error={null}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            onDeleteResumeVersion(deleteTarget.id);
            setBannerNotice(
              `Deleted resume v${deleteTarget.version}. Your master Academic Profile was not affected.`,
            );
            setDeleteTarget(null);
          }
        }}
      />
    </div>
  );
}
