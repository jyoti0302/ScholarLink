import React, { useEffect, useState } from "react";
import type {
  StudentAchievement,
  StudentAchievementEntryType,
  StudentAchievementInput,
  StudentEducation,
  StudentEducationInput,
  StudentExperience,
  StudentExperienceInput,
  StudentProject,
  StudentProjectEntryType,
  StudentProjectInput,
  StudentPublication,
  StudentPublicationInput,
  StudentSkill,
  StudentSkillCategory,
  StudentSkillInput,
} from "../../types/api";
import { ProfileModal } from "./ProfileModal";

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-navy-700 focus:outline-none focus:ring-1 focus:ring-navy-700";
const labelClass = "block text-sm font-medium text-slate-700";

function parseYear(raw: string): number | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  return Number.isInteger(num) ? num : null;
}

function ModalFooter({
  saving,
  submitLabel,
  onCancel,
}: {
  saving: boolean;
  submitLabel: string;
  onCancel: () => void;
}) {
  return (
    <div className="mt-6 flex justify-end gap-3 border-t border-slate-100 pt-4">
      <button
        type="button"
        onClick={onCancel}
        disabled={saving}
        className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        Cancel
      </button>
      <button
        type="submit"
        disabled={saving}
        className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900 disabled:opacity-50"
      >
        {saving ? "Saving..." : submitLabel}
      </button>
    </div>
  );
}

// -------------------------------------------------------------------------
// Education Form Modal
// -------------------------------------------------------------------------

export function EducationFormModal({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: StudentEducation | null;
  onClose: () => void;
  onSave: (payload: StudentEducationInput) => Promise<void>;
}) {
  const [institution, setInstitution] = useState("");
  const [degree, setDegree] = useState("");
  const [departmentMajor, setDepartmentMajor] = useState("");
  const [startYear, setStartYear] = useState("");
  const [graduationYear, setGraduationYear] = useState("");
  const [cgpa, setCgpa] = useState("");
  const [coursework, setCoursework] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setInstitution(initial?.institution ?? "");
    setDegree(initial?.degree ?? "");
    setDepartmentMajor(initial?.department_major ?? "");
    setStartYear(initial?.start_year != null ? String(initial.start_year) : "");
    setGraduationYear(initial?.graduation_year != null ? String(initial.graduation_year) : "");
    setCgpa(initial?.cgpa_or_percentage ?? "");
    setCoursework(initial?.relevant_coursework ?? "");
    setError(null);
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!institution.trim() || !degree.trim()) {
      setError("Institution and degree are required.");
      return;
    }
    const sy = parseYear(startYear);
    const gy = parseYear(graduationYear);
    if (startYear.trim() && (sy === null || sy < 1950 || sy > 2100)) {
      setError("Start year must be a valid 4-digit year (1950–2100).");
      return;
    }
    if (graduationYear.trim() && (gy === null || gy < 1950 || gy > 2100)) {
      setError("End / graduation year must be a valid 4-digit year (1950–2100).");
      return;
    }

    setSaving(true);
    try {
      await onSave({
        institution: institution.trim(),
        degree: degree.trim(),
        department_major: departmentMajor.trim() || null,
        start_year: sy,
        graduation_year: gy,
        cgpa_or_percentage: cgpa.trim() || null,
        relevant_coursework: coursework.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save education record.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal open={open} title={initial ? "Edit Education" : "Add Education"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Institution *</label>
            <input
              type="text"
              required
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              placeholder="e.g. Indian Institute of Technology Kharagpur"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Degree *</label>
            <input
              type="text"
              required
              value={degree}
              onChange={(e) => setDegree(e.target.value)}
              placeholder="e.g. B.Tech, M.Tech, Dual Degree"
              className={inputClass}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-1">
            <label className={labelClass}>Department / Field of Study</label>
            <input
              type="text"
              value={departmentMajor}
              onChange={(e) => setDepartmentMajor(e.target.value)}
              placeholder="e.g. Computer Science"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Start Year</label>
            <input
              type="number"
              min={1950}
              max={2100}
              value={startYear}
              onChange={(e) => setStartYear(e.target.value)}
              placeholder="2023"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>End / Graduation Year</label>
            <input
              type="number"
              min={1950}
              max={2100}
              value={graduationYear}
              onChange={(e) => setGraduationYear(e.target.value)}
              placeholder="2027"
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>Grade / CGPA (optional)</label>
          <input
            type="text"
            value={cgpa}
            onChange={(e) => setCgpa(e.target.value)}
            placeholder="e.g. 9.1 / 10.0"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Relevant Coursework / Description (optional)</label>
          <textarea
            rows={3}
            value={coursework}
            onChange={(e) => setCoursework(e.target.value)}
            placeholder="Key courses, thesis focus, or academic honors"
            className={inputClass}
          />
        </div>
        <ModalFooter saving={saving} submitLabel={initial ? "Save changes" : "Add education"} onCancel={onClose} />
      </form>
    </ProfileModal>
  );
}

// -------------------------------------------------------------------------
// Skill Form Modal (Technical vs Research mode, sharing backend student_skills)
// -------------------------------------------------------------------------

export function SkillFormModal({
  open,
  mode,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  mode: "technical" | "research";
  initial: StudentSkill | null;
  onClose: () => void;
  onSave: (payload: StudentSkillInput) => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<StudentSkillCategory>(mode === "research" ? "research" : "technical");
  const [proficiency, setProficiency] = useState("");
  const [context, setContext] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setCategory(
      mode === "research"
        ? "research"
        : ((initial?.category as StudentSkillCategory | undefined) ?? "technical"),
    );
    setProficiency(initial?.proficiency_level ?? "");
    setContext(initial?.experience_context ?? "");
    setError(null);
  }, [open, initial, mode]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError("Skill name is required.");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        category: mode === "research" ? "research" : category,
        proficiency_level: proficiency.trim() || null,
        experience_context: context.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save skill.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal
      open={open}
      title={
        initial
          ? mode === "research"
            ? "Edit Research Skill / Method"
            : "Edit Technical Skill"
          : mode === "research"
            ? "Add Research Skill / Method"
            : "Add Technical Skill"
      }
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>{mode === "research" ? "Research Skill / Method *" : "Skill Name *"}</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={
                mode === "research"
                  ? "e.g. Transformer Fine-Tuning, Experimental Design"
                  : "e.g. PyTorch, Python, Docker"
              }
              className={inputClass}
            />
          </div>
          {mode === "technical" ? (
            <div>
              <label className={labelClass}>Category *</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as StudentSkillCategory)}
                className={inputClass}
              >
                <option value="technical">Technical</option>
                <option value="tool">Tool / Framework</option>
                <option value="language">Programming Language</option>
              </select>
            </div>
          ) : (
            <div>
              <label className={labelClass}>Category</label>
              <input type="text" value="Research" disabled className={`${inputClass} bg-slate-50 text-slate-500`} />
            </div>
          )}
        </div>
        <div>
          <label className={labelClass}>Proficiency Level (optional)</label>
          <select value={proficiency} onChange={(e) => setProficiency(e.target.value)} className={inputClass}>
            <option value="">Not specified</option>
            <option value="Beginner">Beginner</option>
            <option value="Intermediate">Intermediate</option>
            <option value="Advanced">Advanced</option>
            <option value="Expert">Expert</option>
          </select>
        </div>
        <div>
          <label className={labelClass}>Experience Context (optional)</label>
          <textarea
            rows={2}
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Where you applied this skill (course, lab, or project)"
            className={inputClass}
          />
        </div>
        <ModalFooter
          saving={saving}
          submitLabel={initial ? "Save changes" : mode === "research" ? "Add research skill" : "Add skill"}
          onCancel={onClose}
        />
      </form>
    </ProfileModal>
  );
}

// -------------------------------------------------------------------------
// Project / Research Experience Form Modal (student_projects entry_type)
// -------------------------------------------------------------------------

export function ProjectFormModal({
  open,
  entryType,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  entryType: StudentProjectEntryType;
  initial: StudentProject | null;
  onClose: () => void;
  onSave: (payload: StudentProjectInput) => Promise<void>;
}) {
  const isResearch = entryType === "research_experience";
  const [title, setTitle] = useState("");
  const [role, setRole] = useState("");
  const [organization, setOrganization] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [description, setDescription] = useState("");
  const [methodology, setMethodology] = useState("");
  const [outcomes, setOutcomes] = useState("");
  const [technologies, setTechnologies] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [projectUrl, setProjectUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(initial?.title ?? "");
    setRole(initial?.role ?? "");
    setOrganization(initial?.organization ?? "");
    setStartDate(initial?.start_date ?? "");
    setEndDate(initial?.end_date ?? "");
    setDescription(initial?.description ?? "");
    setMethodology(initial?.methodology ?? "");
    setOutcomes(initial?.outcomes_results ?? "");
    setTechnologies(initial?.technologies_tools ?? "");
    setGithubUrl(initial?.github_url ?? "");
    setProjectUrl(initial?.project_url ?? "");
    setError(null);
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError(isResearch ? "Research title is required." : "Project title is required.");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        entry_type: entryType,
        title: title.trim(),
        role: role.trim() || null,
        organization: organization.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        description: description.trim() || null,
        methodology: methodology.trim() || null,
        outcomes_results: outcomes.trim() || null,
        technologies_tools: technologies.trim() || null,
        github_url: githubUrl.trim() || null,
        project_url: projectUrl.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save record.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal
      open={open}
      title={
        initial
          ? isResearch
            ? "Edit Research Experience"
            : "Edit Project"
          : isResearch
            ? "Add Research Experience"
            : "Add Project"
      }
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div>
          <label className={labelClass}>{isResearch ? "Research Title *" : "Project Title *"}</label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder={
              isResearch
                ? "e.g. Low-Resource Neural Machine Translation for Indian Languages"
                : "e.g. Distributed Vector Search Engine"
            }
            className={inputClass}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Role</label>
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder={isResearch ? "e.g. Undergraduate Research Assistant" : "e.g. Lead Developer"}
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>
              {isResearch ? "Professor / Lab / Organization" : "Organization / Team"}
            </label>
            <input
              type="text"
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              placeholder={isResearch ? "e.g. CNeRG Lab, IIT Kharagpur" : "e.g. Course Project / Personal"}
              className={inputClass}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Start Date</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="e.g. May 2025"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>End Date</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="e.g. Present or Dec 2025"
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>{isResearch ? "Research Summary" : "Project Summary"}</label>
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief overview of goals and context"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Methodology</label>
          <textarea
            rows={2}
            value={methodology}
            onChange={(e) => setMethodology(e.target.value)}
            placeholder="Approach, models, datasets, or experimental setup"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>{isResearch ? "Findings / Results" : "Results / Impact"}</label>
          <textarea
            rows={2}
            value={outcomes}
            onChange={(e) => setOutcomes(e.target.value)}
            placeholder="Measured metrics, deliverables, or key outcomes"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>{isResearch ? "Tools & Techniques" : "Technologies / Tools"}</label>
          <input
            type="text"
            value={technologies}
            onChange={(e) => setTechnologies(e.target.value)}
            placeholder="e.g. PyTorch, Hugging Face, PostgreSQL, Qdrant"
            className={inputClass}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Repository URL</label>
            <input
              type="url"
              value={githubUrl}
              onChange={(e) => setGithubUrl(e.target.value)}
              placeholder="https://github.com/..."
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>{isResearch ? "Paper / Publication URL" : "Live / Project URL"}</label>
            <input
              type="url"
              value={projectUrl}
              onChange={(e) => setProjectUrl(e.target.value)}
              placeholder="https://..."
              className={inputClass}
            />
          </div>
        </div>
        <ModalFooter
          saving={saving}
          submitLabel={initial ? "Save changes" : isResearch ? "Add research experience" : "Add project"}
          onCancel={onClose}
        />
      </form>
    </ProfileModal>
  );
}

// -------------------------------------------------------------------------
// Experience Form Modal
// -------------------------------------------------------------------------

export function ExperienceFormModal({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: StudentExperience | null;
  onClose: () => void;
  onSave: (payload: StudentExperienceInput) => Promise<void>;
}) {
  const [organization, setOrganization] = useState("");
  const [role, setRole] = useState("");
  const [location, setLocation] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [responsibilities, setResponsibilities] = useState("");
  const [achievements, setAchievements] = useState("");
  const [technologies, setTechnologies] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setOrganization(initial?.organization ?? "");
    setRole(initial?.role ?? "");
    setLocation(initial?.location ?? "");
    setStartDate(initial?.start_date ?? "");
    setEndDate(initial?.end_date ?? "");
    setResponsibilities(initial?.responsibilities ?? "");
    setAchievements(initial?.achievements ?? "");
    setTechnologies(initial?.technologies_used ?? "");
    setError(null);
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!organization.trim() || !role.trim()) {
      setError("Organization and job title / role are required.");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        organization: organization.trim(),
        role: role.trim(),
        location: location.trim() || null,
        start_date: startDate.trim() || null,
        end_date: endDate.trim() || null,
        responsibilities: responsibilities.trim() || null,
        achievements: achievements.trim() || null,
        technologies_used: technologies.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save experience.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal open={open} title={initial ? "Edit Experience" : "Add Internship / Work Experience"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Organization *</label>
            <input
              type="text"
              required
              value={organization}
              onChange={(e) => setOrganization(e.target.value)}
              placeholder="e.g. Microsoft Research India"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Job Title / Role *</label>
            <input
              type="text"
              required
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="e.g. Research Intern"
              className={inputClass}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className={labelClass}>Location</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Bengaluru / Remote"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Start Date</label>
            <input
              type="text"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="e.g. May 2025"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>End Date</label>
            <input
              type="text"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="e.g. Jul 2025"
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>Responsibilities</label>
          <textarea
            rows={3}
            value={responsibilities}
            onChange={(e) => setResponsibilities(e.target.value)}
            placeholder="Core duties and contributions"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Achievements / Impact</label>
          <textarea
            rows={2}
            value={achievements}
            onChange={(e) => setAchievements(e.target.value)}
            placeholder="Quantifiable results or deliverables"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Technologies Used (optional)</label>
          <input
            type="text"
            value={technologies}
            onChange={(e) => setTechnologies(e.target.value)}
            placeholder="e.g. Python, FastAPI, React"
            className={inputClass}
          />
        </div>
        <ModalFooter saving={saving} submitLabel={initial ? "Save changes" : "Add experience"} onCancel={onClose} />
      </form>
    </ProfileModal>
  );
}

// -------------------------------------------------------------------------
// Achievement / Certification Form Modal
// -------------------------------------------------------------------------

export function AchievementFormModal({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: StudentAchievement | null;
  onClose: () => void;
  onSave: (payload: StudentAchievementInput) => Promise<void>;
}) {
  const [entryType, setEntryType] = useState<StudentAchievementEntryType>("achievement");
  const [title, setTitle] = useState("");
  const [issuer, setIssuer] = useState("");
  const [dateAwarded, setDateAwarded] = useState("");
  const [description, setDescription] = useState("");
  const [credentialUrl, setCredentialUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEntryType((initial?.entry_type as StudentAchievementEntryType | undefined) ?? "achievement");
    setTitle(initial?.title ?? "");
    setIssuer(initial?.issuing_organization ?? "");
    setDateAwarded(initial?.date_awarded ?? "");
    setDescription(initial?.description ?? "");
    setCredentialUrl(initial?.credential_url ?? "");
    setError(null);
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        entry_type: entryType,
        title: title.trim(),
        issuing_organization: issuer.trim() || null,
        date_awarded: dateAwarded.trim() || null,
        description: description.trim() || null,
        credential_url: credentialUrl.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save record.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal
      open={open}
      title={initial ? "Edit Achievement / Certification" : "Add Achievement / Certification"}
      onClose={onClose}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className={labelClass}>Type *</label>
            <select
              value={entryType}
              onChange={(e) => setEntryType(e.target.value as StudentAchievementEntryType)}
              className={inputClass}
            >
              <option value="achievement">Achievement / Award</option>
              <option value="certification">Certification</option>
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass}>Title *</label>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Institute Silver Medal / Deep Learning Specialization"
              className={inputClass}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={labelClass}>Issuer / Organization</label>
            <input
              type="text"
              value={issuer}
              onChange={(e) => setIssuer(e.target.value)}
              placeholder="e.g. IIT Kharagpur, Coursera"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Date</label>
            <input
              type="text"
              value={dateAwarded}
              onChange={(e) => setDateAwarded(e.target.value)}
              placeholder="e.g. Apr 2025"
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>Description</label>
          <textarea
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Context, rank, or scope of the recognition"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Credential URL</label>
          <input
            type="url"
            value={credentialUrl}
            onChange={(e) => setCredentialUrl(e.target.value)}
            placeholder="https://..."
            className={inputClass}
          />
        </div>
        <ModalFooter saving={saving} submitLabel={initial ? "Save changes" : "Add record"} onCancel={onClose} />
      </form>
    </ProfileModal>
  );
}

// -------------------------------------------------------------------------
// Publication Form Modal
// -------------------------------------------------------------------------

export function PublicationFormModal({
  open,
  initial,
  onClose,
  onSave,
}: {
  open: boolean;
  initial: StudentPublication | null;
  onClose: () => void;
  onSave: (payload: StudentPublicationInput) => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [authors, setAuthors] = useState("");
  const [venue, setVenue] = useState("");
  const [publicationDate, setPublicationDate] = useState("");
  const [doiOrUrl, setDoiOrUrl] = useState("");
  const [summary, setSummary] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTitle(initial?.title ?? "");
    setAuthors(initial?.authors ?? "");
    setVenue(initial?.journal_or_conference ?? "");
    setPublicationDate(initial?.publication_date ?? "");
    setDoiOrUrl(initial?.doi_or_url ?? "");
    setSummary(initial?.abstract ?? "");
    setError(null);
  }, [open, initial]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!title.trim()) {
      setError("Publication title is required.");
      return;
    }
    setSaving(true);
    try {
      await onSave({
        title: title.trim(),
        authors: authors.trim() || null,
        journal_or_conference: venue.trim() || null,
        publication_date: publicationDate.trim() || null,
        doi_or_url: doiOrUrl.trim() || null,
        abstract: summary.trim() || null,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save publication.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <ProfileModal open={open} title={initial ? "Edit Publication" : "Add Publication"} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </div>
        )}
        <div>
          <label className={labelClass}>Title *</label>
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Full paper title"
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Authors</label>
          <input
            type="text"
            value={authors}
            onChange={(e) => setAuthors(e.target.value)}
            placeholder="e.g. A. Sharma, P. Mitra"
            className={inputClass}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <label className={labelClass}>Journal / Conference / Venue</label>
            <input
              type="text"
              value={venue}
              onChange={(e) => setVenue(e.target.value)}
              placeholder="e.g. ACL 2025, IEEE TPAMI, arXiv"
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Publication Year / Date</label>
            <input
              type="text"
              value={publicationDate}
              onChange={(e) => setPublicationDate(e.target.value)}
              placeholder="e.g. 2025"
              className={inputClass}
            />
          </div>
        </div>
        <div>
          <label className={labelClass}>DOI or URL</label>
          <input
            type="text"
            value={doiOrUrl}
            onChange={(e) => setDoiOrUrl(e.target.value)}
            placeholder="https://doi.org/... or https://arxiv.org/abs/..."
            className={inputClass}
          />
        </div>
        <div>
          <label className={labelClass}>Summary / Abstract</label>
          <textarea
            rows={3}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Concise summary of the paper and your contribution"
            className={inputClass}
          />
        </div>
        <ModalFooter saving={saving} submitLabel={initial ? "Save changes" : "Add publication"} onCancel={onClose} />
      </form>
    </ProfileModal>
  );
}
