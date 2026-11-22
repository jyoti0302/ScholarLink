import { useEffect, useState } from "react";
import type { ApplicationDocumentVersion } from "../../context/ApplicationsContext";
import type {
  ResumeLength,
  ResumeSectionKey,
  ResumeTemplate,
  TailoredResumeContent,
} from "../../types/api";
import ResumePreview from "./ResumePreview";

interface ResumeEditorModalProps {
  open: boolean;
  mode: "edit" | "preview";
  version: ApplicationDocumentVersion | null;
  professorName: string;
  exportingFormat: "pdf" | "docx" | null;
  onClose: () => void;
  onSave: (
    versionId: string,
    updates: {
      title: string;
      template: ResumeTemplate;
      preferredLength: ResumeLength;
      status: "draft" | "approved";
      content: TailoredResumeContent;
    },
  ) => void;
  onExport: (format: "pdf" | "docx", content: TailoredResumeContent, filename: string) => void;
}

const SECTION_LABELS: Record<ResumeSectionKey, string> = {
  summary: "Professional Summary",
  education: "Education",
  research_interests: "Research Interests",
  skills: "Skills",
  projects: "Projects",
  research_experience: "Research Experience",
  experience: "Internships & Work",
  publications: "Publications",
  achievements: "Achievements & Certs",
};

function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const copy = [...list];
  const [item] = copy.splice(index, 1);
  copy.splice(target, 0, item);
  return copy;
}

export default function ResumeEditorModal({
  open,
  mode,
  version,
  professorName,
  exportingFormat,
  onClose,
  onSave,
  onExport,
}: ResumeEditorModalProps) {
  const [activeMode, setActiveMode] = useState<"edit" | "preview">(mode);
  const [draft, setDraft] = useState<TailoredResumeContent | null>(version?.content ?? null);
  const [status, setStatus] = useState<"draft" | "approved">(
    version?.status === "approved" ? "approved" : "draft",
  );
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => {
    if (!open || !version?.content) return;
    setActiveMode(mode);
    setDraft(JSON.parse(JSON.stringify(version.content)) as TailoredResumeContent);
    setStatus(version.status === "approved" ? "approved" : "draft");
    setSavedNotice(false);
  }, [open, version, mode]);

  if (!open || !version || !draft) return null;

  function handleSave() {
    if (!version || !draft) return;
    onSave(version.id, {
      title: draft.title,
      template: draft.template,
      preferredLength: draft.preferred_length,
      status,
      content: draft,
    });
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 2500);
  }

  const toggleSection = (key: ResumeSectionKey) => {
    setDraft((prev) => {
      if (!prev) return prev;
      const exists = prev.enabled_sections.includes(key);
      return {
        ...prev,
        enabled_sections: exists
          ? prev.enabled_sections.filter((k) => k !== key)
          : [...prev.enabled_sections, key],
      };
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-3 sm:p-5"
      role="dialog"
      aria-modal="true"
      aria-labelledby="resume-editor-title"
    >
      <div className="flex max-h-[94vh] w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-slate-200 bg-slate-50 shadow-2xl">
        {/* Top Action Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-white px-5 py-3.5">
          <div>
            <h2 id="resume-editor-title" className="font-serif text-xl text-navy-900">
              {draft.title} · v{version.version}
            </h2>
            <p className="text-xs text-slate-500">
              Tailored for {professorName} · Edits affect only this resume version and never modify your master Academic
              Profile.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-100 p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setActiveMode("edit")}
                className={`rounded px-2.5 py-1 font-medium ${
                  activeMode === "edit" ? "bg-white text-navy-900 shadow-sm" : "text-slate-600"
                }`}
              >
                Edit &amp; Live Preview
              </button>
              <button
                type="button"
                onClick={() => setActiveMode("preview")}
                className={`rounded px-2.5 py-1 font-medium ${
                  activeMode === "preview" ? "bg-white text-navy-900 shadow-sm" : "text-slate-600"
                }`}
              >
                Full Preview
              </button>
            </div>
            <button
              type="button"
              disabled={exportingFormat !== null}
              onClick={() => onExport("pdf", draft, `${draft.title}_v${version.version}`)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {exportingFormat === "pdf" ? "Exporting PDF..." : "Download PDF"}
            </button>
            <button
              type="button"
              disabled={exportingFormat !== null}
              onClick={() => onExport("docx", draft, `${draft.title}_v${version.version}`)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              {exportingFormat === "docx" ? "Exporting DOCX..." : "Download DOCX"}
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-md bg-navy-800 px-3.5 py-1.5 text-xs font-medium text-white hover:bg-navy-900"
            >
              Save Version
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close editor"
              className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            >
              ✕
            </button>
          </div>
        </div>

        {savedNotice && (
          <div className="border-b border-emerald-200 bg-emerald-50 px-5 py-2 text-xs font-medium text-emerald-800">
            Resume version v{version.version} saved. Downloads will reflect your latest edits.
          </div>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5">
          {activeMode === "preview" ? (
            <div className="mx-auto max-w-3xl">
              <ResumePreview content={draft} />
            </div>
          ) : (
            <div className="grid gap-6 lg:grid-cols-12">
              {/* Left: Structured Editor */}
              <div className="space-y-5 lg:col-span-6">
                {/* Formatting, Title & Version Status */}
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="text-sm font-semibold text-navy-900">Document Settings &amp; Template</h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-xs font-medium text-slate-600">Resume Title</label>
                      <input
                        type="text"
                        value={draft.title}
                        onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                        className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600">Template</label>
                      <select
                        value={draft.template}
                        onChange={(e) => setDraft({ ...draft, template: e.target.value as ResumeTemplate })}
                        className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                      >
                        <option value="academic_research">Academic Research</option>
                        <option value="modern_professional">Modern Professional</option>
                        <option value="technical_ai_ml">Technical / AI-ML</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600">Preferred Length</label>
                      <select
                        value={draft.preferred_length}
                        onChange={(e) => setDraft({ ...draft, preferred_length: e.target.value as ResumeLength })}
                        className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                      >
                        <option value="1_page">1 Page (Concise)</option>
                        <option value="2_pages">2 Pages (Detailed)</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-600">Version Status</label>
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value as "draft" | "approved")}
                        className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                      >
                        <option value="draft">Draft</option>
                        <option value="approved">Approved</option>
                      </select>
                    </div>
                  </div>
                </section>

                {/* Section Order & Visibility */}
                <section className="rounded-lg border border-slate-200 bg-white p-4">
                  <h3 className="text-sm font-semibold text-navy-900">Section Order &amp; Visibility</h3>
                  <div className="mt-2.5 space-y-1.5">
                    {draft.section_order.map((secKey, idx) => (
                      <div
                        key={secKey}
                        className="flex items-center justify-between rounded border border-slate-100 bg-slate-50 px-2.5 py-1.5 text-xs"
                      >
                        <label className="flex items-center gap-2 font-medium text-slate-700">
                          <input
                            type="checkbox"
                            checked={draft.enabled_sections.includes(secKey)}
                            onChange={() => toggleSection(secKey)}
                            className="h-3.5 w-3.5 rounded border-slate-300 text-navy-800"
                          />
                          <span>{SECTION_LABELS[secKey]}</span>
                        </label>
                        <div className="flex gap-1">
                          <button
                            type="button"
                            disabled={idx === 0}
                            onClick={() =>
                              setDraft({ ...draft, section_order: moveItem(draft.section_order, idx, -1) })
                            }
                            className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            disabled={idx === draft.section_order.length - 1}
                            onClick={() =>
                              setDraft({ ...draft, section_order: moveItem(draft.section_order, idx, 1) })
                            }
                            className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                          >
                            ↓
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>

                {/* Professional Summary & Research Interests */}
                <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                  <h3 className="text-sm font-semibold text-navy-900">Summary &amp; Research Interests</h3>
                  <div>
                    <label className="block text-xs font-medium text-slate-600">Professional Summary</label>
                    <textarea
                      rows={3}
                      value={draft.summary}
                      onChange={(e) => setDraft({ ...draft, summary: e.target.value })}
                      className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600">Research Interests</label>
                    <textarea
                      rows={2}
                      value={draft.research_interests ?? ""}
                      onChange={(e) => setDraft({ ...draft, research_interests: e.target.value || null })}
                      className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
                    />
                  </div>
                </section>

                {/* Education */}
                {draft.education.length > 0 && (
                  <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-navy-900">Education</h3>
                    {draft.education.map((edu, idx) => (
                      <div key={edu.source_id ?? idx} className="space-y-2 rounded border border-slate-100 p-3 text-xs">
                        <div className="grid gap-2 sm:grid-cols-2">
                          <input
                            type="text"
                            value={edu.degree}
                            onChange={(e) => {
                              const next = [...draft.education];
                              next[idx] = { ...edu, degree: e.target.value };
                              setDraft({ ...draft, education: next });
                            }}
                            placeholder="Degree"
                            className="rounded border border-slate-300 px-2 py-1"
                          />
                          <input
                            type="text"
                            value={edu.institution}
                            onChange={(e) => {
                              const next = [...draft.education];
                              next[idx] = { ...edu, institution: e.target.value };
                              setDraft({ ...draft, education: next });
                            }}
                            placeholder="Institution"
                            className="rounded border border-slate-300 px-2 py-1"
                          />
                        </div>
                        <input
                          type="text"
                          value={edu.relevant_coursework ?? ""}
                          onChange={(e) => {
                            const next = [...draft.education];
                            next[idx] = { ...edu, relevant_coursework: e.target.value || null };
                            setDraft({ ...draft, education: next });
                          }}
                          placeholder="Relevant coursework"
                          className="w-full rounded border border-slate-300 px-2 py-1"
                        />
                      </div>
                    ))}
                  </section>
                )}

                {/* Skills */}
                {draft.skills.length > 0 && (
                  <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-navy-900">Skill Categories</h3>
                    {draft.skills.map((grp, idx) => (
                      <div key={idx} className="space-y-1.5 text-xs">
                        <input
                          type="text"
                          value={grp.category}
                          onChange={(e) => {
                            const next = [...draft.skills];
                            next[idx] = { ...grp, category: e.target.value };
                            setDraft({ ...draft, skills: next });
                          }}
                          className="w-full rounded border border-slate-300 px-2 py-1 font-medium"
                        />
                        <input
                          type="text"
                          value={grp.items.join(", ")}
                          onChange={(e) => {
                            const next = [...draft.skills];
                            next[idx] = {
                              ...grp,
                              items: e.target.value
                                .split(",")
                                .map((s) => s.trim())
                                .filter(Boolean),
                            };
                            setDraft({ ...draft, skills: next });
                          }}
                          placeholder="Comma-separated skills"
                          className="w-full rounded border border-slate-300 px-2 py-1"
                        />
                      </div>
                    ))}
                  </section>
                )}

                {/* Projects (Editable & Reorderable) */}
                {draft.projects.length > 0 && (
                  <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-navy-900">Projects (Reorder &amp; Edit)</h3>
                    {draft.projects.map((proj, idx) => (
                      <div key={proj.source_id ?? idx} className="space-y-2 rounded border border-slate-200 p-3 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-navy-900">{proj.title}</span>
                          <div className="flex gap-1">
                            <button
                              type="button"
                              disabled={idx === 0}
                              onClick={() => setDraft({ ...draft, projects: moveItem(draft.projects, idx, -1) })}
                              className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              disabled={idx === draft.projects.length - 1}
                              onClick={() => setDraft({ ...draft, projects: moveItem(draft.projects, idx, 1) })}
                              className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] disabled:opacity-40"
                            >
                              ↓
                            </button>
                          </div>
                        </div>
                        <textarea
                          rows={3}
                          value={proj.bullets.join("\n")}
                          onChange={(e) => {
                            const next = [...draft.projects];
                            next[idx] = {
                              ...proj,
                              bullets: e.target.value
                                .split("\n")
                                .map((b) => b.trim())
                                .filter(Boolean),
                            };
                            setDraft({ ...draft, projects: next });
                          }}
                          placeholder="One bullet per line"
                          className="w-full rounded border border-slate-300 px-2 py-1.5"
                        />
                      </div>
                    ))}
                  </section>
                )}

                {/* Research Experience */}
                {draft.research_experience.length > 0 && (
                  <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-navy-900">Research Experience</h3>
                    {draft.research_experience.map((item, idx) => (
                      <div key={item.source_id ?? idx} className="space-y-1.5 rounded border border-slate-200 p-3 text-xs">
                        <p className="font-semibold text-navy-900">{item.title}</p>
                        <textarea
                          rows={3}
                          value={item.bullets.join("\n")}
                          onChange={(e) => {
                            const next = [...draft.research_experience];
                            next[idx] = {
                              ...item,
                              bullets: e.target.value
                                .split("\n")
                                .map((b) => b.trim())
                                .filter(Boolean),
                            };
                            setDraft({ ...draft, research_experience: next });
                          }}
                          className="w-full rounded border border-slate-300 px-2 py-1.5"
                        />
                      </div>
                    ))}
                  </section>
                )}

                {/* Internships & Work Experience */}
                {draft.experience.length > 0 && (
                  <section className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
                    <h3 className="text-sm font-semibold text-navy-900">Internships &amp; Work Experience</h3>
                    {draft.experience.map((exp, idx) => (
                      <div key={exp.source_id ?? idx} className="space-y-1.5 rounded border border-slate-200 p-3 text-xs">
                        <p className="font-semibold text-navy-900">
                          {exp.role} — {exp.organization}
                        </p>
                        <textarea
                          rows={3}
                          value={exp.bullets.join("\n")}
                          onChange={(e) => {
                            const next = [...draft.experience];
                            next[idx] = {
                              ...exp,
                              bullets: e.target.value
                                .split("\n")
                                .map((b) => b.trim())
                                .filter(Boolean),
                            };
                            setDraft({ ...draft, experience: next });
                          }}
                          className="w-full rounded border border-slate-300 px-2 py-1.5"
                        />
                      </div>
                    ))}
                  </section>
                )}
              </div>

              {/* Right: Live Preview */}
              <div className="lg:col-span-6">
                <div className="lg:sticky lg:top-0">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">Live Preview</p>
                  <ResumePreview content={draft} />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
