import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ApiError,
  createAchievement,
  createEducation,
  createExperience,
  createProject,
  createPublication,
  createSkill,
  deleteAchievement,
  deleteEducation,
  deleteExperience,
  deleteProject,
  deletePublication,
  deleteSkill,
  getStudentProfile,
  updateAchievement,
  updateEducation,
  updateExperience,
  updateProject,
  updatePublication,
  updateSkill,
  updateStudentPersonalInfo,
} from "../api/client";
import { ConfirmDeleteModal } from "../components/profile/ProfileModal";
import {
  AchievementFormModal,
  EducationFormModal,
  ExperienceFormModal,
  ProjectFormModal,
  PublicationFormModal,
  SkillFormModal,
} from "../components/profile/ProfileSectionForms";
import { useAuth } from "../context/AuthContext";
import type {
  StudentAchievement,
  StudentAchievementInput,
  StudentCompleteProfile,
  StudentEducation,
  StudentEducationInput,
  StudentExperience,
  StudentExperienceInput,
  StudentProject,
  StudentProjectInput,
  StudentPublication,
  StudentPublicationInput,
  StudentSkill,
  StudentSkillInput,
} from "../types/api";

type SectionId =
  | "personal"
  | "education"
  | "technical_skills"
  | "research"
  | "projects"
  | "research_experience"
  | "experiences"
  | "achievements"
  | "publications";

type DeleteTarget =
  | { kind: "education"; id: number; label: string }
  | { kind: "skill"; id: number; label: string }
  | { kind: "project"; id: number; label: string }
  | { kind: "experience"; id: number; label: string }
  | { kind: "achievement"; id: number; label: string }
  | { kind: "publication"; id: number; label: string };

const SKILL_CATEGORY_LABELS: Record<string, string> = {
  technical: "Technical",
  tool: "Tool / Framework",
  language: "Language",
  research: "Research",
};

const inputClass =
  "mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-navy-700 focus:outline-none focus:ring-1 focus:ring-navy-700";

function safeUrl(raw: string | null | undefined): string | null {
  if (!raw || !raw.trim()) return null;
  const trimmed = raw.trim();
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  if (trimmed.startsWith("10.")) return `https://doi.org/${trimmed}`;
  return `https://${trimmed}`;
}

function EmptyState({
  title,
  description,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/70 px-6 py-10 text-center">
      <p className="font-medium text-slate-800">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{description}</p>
      <button
        type="button"
        onClick={onAction}
        className="mt-4 inline-flex items-center rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
      >
        + {actionLabel}
      </button>
    </div>
  );
}

function SectionHeader({
  title,
  subtitle,
  actionLabel,
  onAction,
}: {
  title: string;
  subtitle: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
      <div>
        <h2 className="font-serif text-xl text-navy-900">{title}</h2>
        <p className="mt-0.5 text-sm text-slate-600">{subtitle}</p>
      </div>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="rounded-md bg-navy-800 px-3.5 py-2 text-sm font-medium text-white hover:bg-navy-900"
        >
          + {actionLabel}
        </button>
      )}
    </div>
  );
}

function ProfileSkeleton() {
  return (
    <div className="mx-auto max-w-6xl animate-pulse space-y-6 px-6 py-10">
      <div className="h-8 w-64 rounded bg-slate-200" />
      <div className="h-28 rounded-lg border border-slate-200 bg-white p-6" />
      <div className="grid gap-6 lg:grid-cols-4">
        <div className="h-80 rounded-lg border border-slate-200 bg-white p-4" />
        <div className="h-96 rounded-lg border border-slate-200 bg-white p-6 lg:col-span-3" />
      </div>
    </div>
  );
}

export default function StudentProfilePage() {
  const navigate = useNavigate();
  const { logout, syncStudentFromProfile } = useAuth();

  const [profile, setProfile] = useState<StudentCompleteProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<SectionId>("personal");
  const [statusMessage, setStatusMessage] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  // Personal & Academic form state
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [institution, setInstitution] = useState("");
  const [department, setDepartment] = useState("");
  const [degreeProgram, setDegreeProgram] = useState("");
  const [graduationYear, setGraduationYear] = useState("");
  const [currentYearSem, setCurrentYearSem] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [portfolioUrl, setPortfolioUrl] = useState("");
  const [savingPersonal, setSavingPersonal] = useState(false);

  // Research interests summary state (stored on students.research_interests_summary)
  const [researchInterests, setResearchInterests] = useState("");
  const [savingResearchInterests, setSavingResearchInterests] = useState(false);

  // Modal states
  const [eduModal, setEduModal] = useState<{ open: boolean; item: StudentEducation | null }>({ open: false, item: null });
  const [skillModal, setSkillModal] = useState<{
    open: boolean;
    mode: "technical" | "research";
    item: StudentSkill | null;
  }>({ open: false, mode: "technical", item: null });
  const [projectModal, setProjectModal] = useState<{
    open: boolean;
    entryType: "project" | "research_experience";
    item: StudentProject | null;
  }>({ open: false, entryType: "project", item: null });
  const [expModal, setExpModal] = useState<{ open: boolean; item: StudentExperience | null }>({ open: false, item: null });
  const [achModal, setAchModal] = useState<{ open: boolean; item: StudentAchievement | null }>({ open: false, item: null });
  const [pubModal, setPubModal] = useState<{ open: boolean; item: StudentPublication | null }>({ open: false, item: null });

  // Delete confirmation modal
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const handleAuthError = useCallback(
    (err: unknown): boolean => {
      if (err instanceof ApiError && err.kind === "unauthorized") {
        logout();
        navigate("/login", { replace: true, state: { from: { pathname: "/profile" } } });
        return true;
      }
      return false;
    },
    [logout, navigate],
  );

  const hydratePersonalFields = useCallback((p: StudentCompleteProfile) => {
    setFullName(p.full_name ?? "");
    setPhone(p.phone ?? "");
    setInstitution(p.institution ?? "");
    setDepartment(p.department ?? "");
    setDegreeProgram(p.degree_program ?? "");
    setGraduationYear(p.graduation_year != null ? String(p.graduation_year) : "");
    setCurrentYearSem(p.current_year_or_semester ?? "");
    setLinkedinUrl(p.linkedin_url ?? "");
    setGithubUrl(p.github_url ?? "");
    setPortfolioUrl(p.portfolio_url ?? "");
    setResearchInterests(p.research_interests_summary ?? "");
  }, []);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await getStudentProfile();
      setProfile(data);
      hydratePersonalFields(data);
      syncStudentFromProfile(data);
    } catch (err) {
      if (handleAuthError(err)) return;
      setLoadError(err instanceof Error ? err.message : "Failed to load your academic profile.");
    } finally {
      setLoading(false);
    }
  }, [handleAuthError, hydratePersonalFields, syncStudentFromProfile]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  const showSuccess = useCallback((text: string) => {
    setStatusMessage({ kind: "success", text });
  }, []);

  const showError = useCallback((text: string) => {
    setStatusMessage({ kind: "error", text });
  }, []);

  const technicalSkills = useMemo(
    () => (profile?.skills ?? []).filter((s) => s.category !== "research"),
    [profile?.skills],
  );
  const researchSkills = useMemo(
    () => (profile?.skills ?? []).filter((s) => s.category === "research"),
    [profile?.skills],
  );
  const generalProjects = useMemo(
    () => (profile?.projects ?? []).filter((p) => p.entry_type === "project"),
    [profile?.projects],
  );
  const researchExperiences = useMemo(
    () => (profile?.projects ?? []).filter((p) => p.entry_type === "research_experience"),
    [profile?.projects],
  );

  const navItems: { id: SectionId; label: string; count?: number }[] = [
    { id: "personal", label: "Personal & Academic Info" },
    { id: "education", label: "Education", count: profile?.educations.length ?? 0 },
    { id: "technical_skills", label: "Technical Skills", count: technicalSkills.length },
    { id: "research", label: "Research Skills & Interests", count: researchSkills.length },
    { id: "projects", label: "Projects", count: generalProjects.length },
    { id: "research_experience", label: "Research Experience", count: researchExperiences.length },
    { id: "experiences", label: "Internships & Work", count: profile?.experiences.length ?? 0 },
    { id: "achievements", label: "Achievements & Certs", count: profile?.achievements.length ?? 0 },
    { id: "publications", label: "Publications", count: profile?.publications.length ?? 0 },
  ];

  // --- Save Personal & Academic Information ---
  async function handleSavePersonal(e: React.FormEvent) {
    e.preventDefault();
    setStatusMessage(null);
    let parsedGradYear: number | null = null;
    if (graduationYear.trim()) {
      const n = Number(graduationYear.trim());
      if (!Number.isInteger(n) || n < 1950 || n > 2100) {
        showError("Graduation year must be a valid 4-digit year (1950–2100).");
        return;
      }
      parsedGradYear = n;
    }

    setSavingPersonal(true);
    try {
      const updated = await updateStudentPersonalInfo({
        full_name: fullName.trim() || null,
        phone: phone.trim() || null,
        institution: institution.trim() || null,
        department: department.trim() || null,
        degree_program: degreeProgram.trim() || null,
        graduation_year: parsedGradYear,
        current_year_or_semester: currentYearSem.trim() || null,
        linkedin_url: linkedinUrl.trim() || null,
        github_url: githubUrl.trim() || null,
        portfolio_url: portfolioUrl.trim() || null,
      });
      setProfile(updated);
      hydratePersonalFields(updated);
      syncStudentFromProfile(updated);
      showSuccess("Personal and academic information saved.");
    } catch (err) {
      if (handleAuthError(err)) return;
      showError(err instanceof Error ? err.message : "Failed to save personal information.");
    } finally {
      setSavingPersonal(false);
    }
  }

  // --- Save Research Interests Summary ---
  async function handleSaveResearchInterests(e: React.FormEvent) {
    e.preventDefault();
    setStatusMessage(null);
    setSavingResearchInterests(true);
    try {
      const updated = await updateStudentPersonalInfo({
        research_interests_summary: researchInterests.trim() || null,
      });
      setProfile(updated);
      setResearchInterests(updated.research_interests_summary ?? "");
      syncStudentFromProfile(updated);
      showSuccess("Research interests saved.");
    } catch (err) {
      if (handleAuthError(err)) return;
      showError(err instanceof Error ? err.message : "Failed to save research interests.");
    } finally {
      setSavingResearchInterests(false);
    }
  }

  // --- Child CRUD Save Handlers ---
  async function handleSaveEducation(payload: StudentEducationInput) {
    try {
      if (eduModal.item) {
        const res = await updateEducation(eduModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                educations: prev.educations.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess("Education record updated.");
      } else {
        const res = await createEducation(payload);
        setProfile((prev) =>
          prev
            ? { ...prev, educations: [res.item, ...prev.educations], completion: res.completion }
            : prev,
        );
        showSuccess("Education record added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  async function handleSaveSkill(payload: StudentSkillInput) {
    try {
      if (skillModal.item) {
        const res = await updateSkill(skillModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                skills: prev.skills.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess("Skill updated.");
      } else {
        const res = await createSkill(payload);
        setProfile((prev) =>
          prev ? { ...prev, skills: [res.item, ...prev.skills], completion: res.completion } : prev,
        );
        showSuccess("Skill added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  async function handleSaveProject(payload: StudentProjectInput) {
    try {
      if (projectModal.item) {
        const res = await updateProject(projectModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                projects: prev.projects.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess(payload.entry_type === "research_experience" ? "Research experience updated." : "Project updated.");
      } else {
        const res = await createProject(payload);
        setProfile((prev) =>
          prev ? { ...prev, projects: [res.item, ...prev.projects], completion: res.completion } : prev,
        );
        showSuccess(payload.entry_type === "research_experience" ? "Research experience added." : "Project added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  async function handleSaveExperience(payload: StudentExperienceInput) {
    try {
      if (expModal.item) {
        const res = await updateExperience(expModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                experiences: prev.experiences.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess("Experience updated.");
      } else {
        const res = await createExperience(payload);
        setProfile((prev) =>
          prev ? { ...prev, experiences: [res.item, ...prev.experiences], completion: res.completion } : prev,
        );
        showSuccess("Experience added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  async function handleSaveAchievement(payload: StudentAchievementInput) {
    try {
      if (achModal.item) {
        const res = await updateAchievement(achModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                achievements: prev.achievements.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess("Record updated.");
      } else {
        const res = await createAchievement(payload);
        setProfile((prev) =>
          prev ? { ...prev, achievements: [res.item, ...prev.achievements], completion: res.completion } : prev,
        );
        showSuccess("Record added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  async function handleSavePublication(payload: StudentPublicationInput) {
    try {
      if (pubModal.item) {
        const res = await updatePublication(pubModal.item.id, payload);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                publications: prev.publications.map((x) => (x.id === res.item.id ? res.item : x)),
                completion: res.completion,
              }
            : prev,
        );
        showSuccess("Publication updated.");
      } else {
        const res = await createPublication(payload);
        setProfile((prev) =>
          prev ? { ...prev, publications: [res.item, ...prev.publications], completion: res.completion } : prev,
        );
        showSuccess("Publication added.");
      }
    } catch (err) {
      if (handleAuthError(err)) return;
      throw err;
    }
  }

  // --- Delete Confirmation Handler ---
  async function handleConfirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      if (deleteTarget.kind === "education") {
        const res = await deleteEducation(deleteTarget.id);
        setProfile((prev) =>
          prev
            ? { ...prev, educations: prev.educations.filter((x) => x.id !== res.deleted_id), completion: res.completion }
            : prev,
        );
      } else if (deleteTarget.kind === "skill") {
        const res = await deleteSkill(deleteTarget.id);
        setProfile((prev) =>
          prev ? { ...prev, skills: prev.skills.filter((x) => x.id !== res.deleted_id), completion: res.completion } : prev,
        );
      } else if (deleteTarget.kind === "project") {
        const res = await deleteProject(deleteTarget.id);
        setProfile((prev) =>
          prev
            ? { ...prev, projects: prev.projects.filter((x) => x.id !== res.deleted_id), completion: res.completion }
            : prev,
        );
      } else if (deleteTarget.kind === "experience") {
        const res = await deleteExperience(deleteTarget.id);
        setProfile((prev) =>
          prev
            ? { ...prev, experiences: prev.experiences.filter((x) => x.id !== res.deleted_id), completion: res.completion }
            : prev,
        );
      } else if (deleteTarget.kind === "achievement") {
        const res = await deleteAchievement(deleteTarget.id);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                achievements: prev.achievements.filter((x) => x.id !== res.deleted_id),
                completion: res.completion,
              }
            : prev,
        );
      } else if (deleteTarget.kind === "publication") {
        const res = await deletePublication(deleteTarget.id);
        setProfile((prev) =>
          prev
            ? {
                ...prev,
                publications: prev.publications.filter((x) => x.id !== res.deleted_id),
                completion: res.completion,
              }
            : prev,
        );
      }
      showSuccess(`Deleted "${deleteTarget.label}".`);
      setDeleteTarget(null);
    } catch (err) {
      if (handleAuthError(err)) return;
      setDeleteError(err instanceof Error ? err.message : "Failed to delete record.");
    } finally {
      setDeleting(false);
    }
  }

  if (loading) {
    return <ProfileSkeleton />;
  }

  if (loadError || !profile) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <div className="rounded-lg border border-red-200 bg-white p-8 text-center">
          <h1 className="font-serif text-2xl text-navy-900">Unable to load your profile</h1>
          <p className="mt-2 text-sm text-red-700">{loadError || "An unexpected error occurred."}</p>
          <button
            type="button"
            onClick={() => void loadProfile()}
            className="mt-5 rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const completion = profile.completion;

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      {/* Page Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-serif text-3xl text-navy-900">My Academic Profile</h1>
          <p className="mt-1 text-sm text-slate-600">
            Maintain your structured academic background to support professor-specific resumes and cover letters.
          </p>
        </div>
        <div className="text-right text-xs text-slate-500">
          Signed in as <span className="font-medium text-slate-800">{profile.email}</span>
        </div>
      </div>

      {/* Backend-driven Profile Completion Banner */}
      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-navy-900">Profile Completion</h2>
            <p className="text-xs text-slate-500">
              {completion.completed_count} of {completion.total_count} core academic sections completed
            </p>
          </div>
          <span className="rounded-full bg-navy-50 px-3 py-1 text-sm font-semibold text-navy-800">
            {completion.percentage}%
          </span>
        </div>
        <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-navy-800 transition-all duration-300"
            style={{ width: `${Math.min(100, Math.max(0, completion.percentage))}%` }}
          />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {completion.items.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActiveSection(item.section as SectionId)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition ${
                item.completed
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                  : "border-slate-200 bg-slate-50 text-slate-600 hover:border-navy-300 hover:text-navy-800"
              }`}
            >
              <span>{item.completed ? "✓" : "○"}</span>
              <span>{item.label}</span>
              <span className="text-[11px] opacity-75">({item.weight}%)</span>
            </button>
          ))}
        </div>
      </section>

      {/* Status Toast / Feedback Banner */}
      {statusMessage && (
        <div
          role={statusMessage.kind === "error" ? "alert" : "status"}
          className={`mt-5 flex items-center justify-between rounded-md border px-4 py-3 text-sm ${
            statusMessage.kind === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-red-200 bg-red-50 text-red-900"
          }`}
        >
          <span>{statusMessage.text}</span>
          <button
            type="button"
            onClick={() => setStatusMessage(null)}
            className="ml-4 text-xs font-medium opacity-70 hover:opacity-100"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Main Split Layout: Left Section Navigation + Main Content Panel */}
      <div className="mt-6 grid gap-6 lg:grid-cols-12">
        <aside className="lg:col-span-3">
          <nav
            aria-label="Academic profile sections"
            className="flex gap-1 overflow-x-auto rounded-lg border border-slate-200 bg-white p-2 lg:sticky lg:top-6 lg:flex-col lg:overflow-visible"
          >
            {navItems.map((item) => {
              const active = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setActiveSection(item.id);
                    setStatusMessage(null);
                  }}
                  className={`flex shrink-0 items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition ${
                    active
                      ? "bg-navy-800 font-medium text-white"
                      : "text-slate-700 hover:bg-slate-100 hover:text-navy-900"
                  }`}
                >
                  <span>{item.label}</span>
                  {item.count !== undefined && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        active ? "bg-white/20 text-white" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {item.count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </aside>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm lg:col-span-9">
          {/* A. Personal & Academic Information */}
          {activeSection === "personal" && (
            <div>
              <SectionHeader
                title="Personal & Academic Information"
                subtitle="Your core identity, institutional affiliation, and academic links. Account email is read-only."
              />
              <form onSubmit={handleSavePersonal} className="space-y-5">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Account Email (read-only)</label>
                    <input
                      type="email"
                      value={profile.email}
                      disabled
                      className={`${inputClass} cursor-not-allowed bg-slate-50 text-slate-500`}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Full Name</label>
                    <input
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="e.g. Aarav Sharma"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Phone Number</label>
                    <input
                      type="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="e.g. +91 98765 43210"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Institution</label>
                    <input
                      type="text"
                      value={institution}
                      onChange={(e) => setInstitution(e.target.value)}
                      placeholder="e.g. Indian Institute of Technology Kharagpur"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Department</label>
                    <input
                      type="text"
                      value={department}
                      onChange={(e) => setDepartment(e.target.value)}
                      placeholder="e.g. Computer Science and Engineering"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Degree / Program</label>
                    <input
                      type="text"
                      value={degreeProgram}
                      onChange={(e) => setDegreeProgram(e.target.value)}
                      placeholder="e.g. B.Tech / Dual Degree / M.Tech"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Graduation Year</label>
                    <input
                      type="number"
                      min={1950}
                      max={2100}
                      value={graduationYear}
                      onChange={(e) => setGraduationYear(e.target.value)}
                      placeholder="e.g. 2027"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700">Current Year / Semester</label>
                    <input
                      type="text"
                      value={currentYearSem}
                      onChange={(e) => setCurrentYearSem(e.target.value)}
                      placeholder="e.g. 3rd Year / 6th Semester"
                      className={inputClass}
                    />
                  </div>
                </div>

                <div className="border-t border-slate-100 pt-4">
                  <h3 className="text-sm font-semibold text-navy-900">Academic & Professional Links</h3>
                  <div className="mt-3 grid gap-4 sm:grid-cols-3">
                    <div>
                      <label className="block text-sm font-medium text-slate-700">LinkedIn URL</label>
                      <input
                        type="url"
                        value={linkedinUrl}
                        onChange={(e) => setLinkedinUrl(e.target.value)}
                        placeholder="https://linkedin.com/in/..."
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">GitHub URL</label>
                      <input
                        type="url"
                        value={githubUrl}
                        onChange={(e) => setGithubUrl(e.target.value)}
                        placeholder="https://github.com/..."
                        className={inputClass}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700">Personal Portfolio URL</label>
                      <input
                        type="url"
                        value={portfolioUrl}
                        onChange={(e) => setPortfolioUrl(e.target.value)}
                        placeholder="https://..."
                        className={inputClass}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex justify-end border-t border-slate-100 pt-4">
                  <button
                    type="submit"
                    disabled={savingPersonal}
                    className="rounded-md bg-navy-800 px-5 py-2 text-sm font-medium text-white hover:bg-navy-900 disabled:opacity-60"
                  >
                    {savingPersonal ? "Saving..." : "Save personal information"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* B. Education */}
          {activeSection === "education" && (
            <div>
              <SectionHeader
                title="Education"
                subtitle="Add degrees, institutions, graduation timelines, CGPA, and relevant coursework."
                actionLabel="Add Education"
                onAction={() => setEduModal({ open: true, item: null })}
              />
              {profile.educations.length === 0 ? (
                <EmptyState
                  title="No education records yet"
                  description="Add your current degree and previous academic qualifications."
                  actionLabel="Add Education"
                  onAction={() => setEduModal({ open: true, item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {profile.educations.map((edu) => (
                    <article key={edu.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">
                            {edu.degree}
                            {edu.department_major ? ` — ${edu.department_major}` : ""}
                          </h3>
                          <p className="text-sm text-slate-700">{edu.institution}</p>
                          <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-500">
                            {(edu.start_year || edu.graduation_year) && (
                              <span>
                                {edu.start_year ?? "—"} – {edu.graduation_year ?? "Present"}
                              </span>
                            )}
                            {edu.cgpa_or_percentage && <span>Grade / CGPA: {edu.cgpa_or_percentage}</span>}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setEduModal({ open: true, item: edu })}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setDeleteTarget({
                                kind: "education",
                                id: edu.id,
                                label: `${edu.degree} at ${edu.institution}`,
                              })
                            }
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {edu.relevant_coursework && (
                        <p className="mt-2.5 whitespace-pre-line text-sm text-slate-600">{edu.relevant_coursework}</p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* C. Technical Skills */}
          {activeSection === "technical_skills" && (
            <div>
              <SectionHeader
                title="Technical Skills"
                subtitle="Programming languages, frameworks, tools, and engineering capabilities."
                actionLabel="Add Skill"
                onAction={() => setSkillModal({ open: true, mode: "technical", item: null })}
              />
              {technicalSkills.length === 0 ? (
                <EmptyState
                  title="No technical skills added yet"
                  description="List languages, libraries, tools, and frameworks you use in coursework or projects."
                  actionLabel="Add Technical Skill"
                  onAction={() => setSkillModal({ open: true, mode: "technical", item: null })}
                />
              ) : (
                <div className="grid gap-3 sm:grid-cols-2">
                  {technicalSkills.map((skill) => (
                    <article key={skill.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">{skill.name}</h3>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            <span className="rounded bg-navy-50 px-2 py-0.5 text-[11px] font-medium text-navy-800">
                              {SKILL_CATEGORY_LABELS[skill.category] || skill.category}
                            </span>
                            {skill.proficiency_level && (
                              <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                                {skill.proficiency_level}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setSkillModal({ open: true, mode: "technical", item: skill })}
                            className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: "skill", id: skill.id, label: skill.name })}
                            className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {skill.experience_context && (
                        <p className="mt-2 text-xs text-slate-600">{skill.experience_context}</p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* D. Research Skills & Interests */}
          {activeSection === "research" && (
            <div className="space-y-8">
              <div>
                <SectionHeader
                  title="Research Skills & Interests"
                  subtitle="Describe your research areas and list research methods or domain capabilities."
                />
                <form onSubmit={handleSaveResearchInterests} className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/50 p-4">
                  <label className="block text-sm font-medium text-slate-800">Research Interests Summary</label>
                  <textarea
                    rows={4}
                    value={researchInterests}
                    onChange={(e) => setResearchInterests(e.target.value)}
                    placeholder="e.g. Transformer architectures, low-resource NLP for Indian languages, retrieval-augmented generation, graph neural networks..."
                    className={inputClass}
                  />
                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={savingResearchInterests}
                      className="rounded-md bg-navy-800 px-4 py-2 text-sm font-medium text-white hover:bg-navy-900 disabled:opacity-60"
                    >
                      {savingResearchInterests ? "Saving..." : "Save research interests"}
                    </button>
                  </div>
                </form>
              </div>

              <div>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <h3 className="font-serif text-lg text-navy-900">Research Methods & Capabilities</h3>
                    <p className="text-xs text-slate-500">
                      Stored as research-category skills in your profile (no duplicate skill records).
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSkillModal({ open: true, mode: "research", item: null })}
                    className="rounded-md bg-navy-800 px-3.5 py-2 text-sm font-medium text-white hover:bg-navy-900"
                  >
                    + Add Research Skill
                  </button>
                </div>

                {researchSkills.length === 0 ? (
                  <EmptyState
                    title="No research methods or capabilities listed yet"
                    description="Add experimental design, statistical modeling, simulation, or domain-specific research methods."
                    actionLabel="Add Research Skill"
                    onAction={() => setSkillModal({ open: true, mode: "research", item: null })}
                  />
                ) : (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {researchSkills.map((skill) => (
                      <article key={skill.id} className="rounded-lg border border-slate-200 p-4">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h4 className="font-medium text-navy-900">{skill.name}</h4>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800">
                                Research
                              </span>
                              {skill.proficiency_level && (
                                <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">
                                  {skill.proficiency_level}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => setSkillModal({ open: true, mode: "research", item: skill })}
                              className="rounded border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => setDeleteTarget({ kind: "skill", id: skill.id, label: skill.name })}
                              className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                            >
                              Delete
                            </button>
                          </div>
                        </div>
                        {skill.experience_context && (
                          <p className="mt-2 text-xs text-slate-600">{skill.experience_context}</p>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* E. Projects */}
          {activeSection === "projects" && (
            <div>
              <SectionHeader
                title="Projects"
                subtitle="Academic, technical, or personal projects with methodology, results, and repository links."
                actionLabel="Add Project"
                onAction={() => setProjectModal({ open: true, entryType: "project", item: null })}
              />
              {generalProjects.length === 0 ? (
                <EmptyState
                  title="No projects added yet"
                  description="Highlight technical or course projects that demonstrate your engineering and problem-solving skills."
                  actionLabel="Add Project"
                  onAction={() => setProjectModal({ open: true, entryType: "project", item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {generalProjects.map((proj) => (
                    <article key={proj.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">{proj.title}</h3>
                          <p className="text-xs text-slate-600">
                            {[proj.role, proj.organization, [proj.start_date, proj.end_date].filter(Boolean).join(" – ")]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setProjectModal({ open: true, entryType: "project", item: proj })}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: "project", id: proj.id, label: proj.title })}
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {proj.description && <p className="mt-2.5 text-sm text-slate-700">{proj.description}</p>}
                      {proj.methodology && (
                        <p className="mt-2 text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Methodology:</span> {proj.methodology}
                        </p>
                      )}
                      {proj.outcomes_results && (
                        <p className="mt-1 text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Results / Impact:</span> {proj.outcomes_results}
                        </p>
                      )}
                      {proj.technologies_tools && (
                        <p className="mt-1.5 text-xs text-slate-500">
                          <span className="font-medium text-slate-700">Tools:</span> {proj.technologies_tools}
                        </p>
                      )}
                      <div className="mt-2 flex flex-wrap gap-4 text-xs">
                        {safeUrl(proj.github_url) && (
                          <a
                            href={safeUrl(proj.github_url)!}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-navy-700 hover:underline"
                          >
                            Repository ↗
                          </a>
                        )}
                        {safeUrl(proj.project_url) && (
                          <a
                            href={safeUrl(proj.project_url)!}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-navy-700 hover:underline"
                          >
                            Project Link ↗
                          </a>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* F. Research Experience */}
          {activeSection === "research_experience" && (
            <div>
              <SectionHeader
                title="Research Experience"
                subtitle="Lab internships, BTP/MTP thesis work, and independent faculty-supervised research."
                actionLabel="Add Research Experience"
                onAction={() => setProjectModal({ open: true, entryType: "research_experience", item: null })}
              />
              {researchExperiences.length === 0 ? (
                <EmptyState
                  title="No research experience added yet"
                  description="Document research labs, thesis projects, methodologies, and findings."
                  actionLabel="Add Research Experience"
                  onAction={() => setProjectModal({ open: true, entryType: "research_experience", item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {researchExperiences.map((resItem) => (
                    <article key={resItem.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">{resItem.title}</h3>
                          <p className="text-xs text-slate-600">
                            {[
                              resItem.role,
                              resItem.organization,
                              [resItem.start_date, resItem.end_date].filter(Boolean).join(" – "),
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() =>
                              setProjectModal({ open: true, entryType: "research_experience", item: resItem })
                            }
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: "project", id: resItem.id, label: resItem.title })}
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {resItem.description && <p className="mt-2.5 text-sm text-slate-700">{resItem.description}</p>}
                      {resItem.methodology && (
                        <p className="mt-2 text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Methodology:</span> {resItem.methodology}
                        </p>
                      )}
                      {resItem.outcomes_results && (
                        <p className="mt-1 text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Findings / Results:</span>{" "}
                          {resItem.outcomes_results}
                        </p>
                      )}
                      {resItem.technologies_tools && (
                        <p className="mt-1.5 text-xs text-slate-500">
                          <span className="font-medium text-slate-700">Tools & Techniques:</span>{" "}
                          {resItem.technologies_tools}
                        </p>
                      )}
                      <div className="mt-2 flex flex-wrap gap-4 text-xs">
                        {safeUrl(resItem.project_url) && (
                          <a
                            href={safeUrl(resItem.project_url)!}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-navy-700 hover:underline"
                          >
                            Paper / Publication ↗
                          </a>
                        )}
                        {safeUrl(resItem.github_url) && (
                          <a
                            href={safeUrl(resItem.github_url)!}
                            target="_blank"
                            rel="noreferrer"
                            className="font-medium text-navy-700 hover:underline"
                          >
                            Repository ↗
                          </a>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* G. Internships & Work Experience */}
          {activeSection === "experiences" && (
            <div>
              <SectionHeader
                title="Internships & Work Experience"
                subtitle="Industry internships, teaching assistantships, and relevant professional roles."
                actionLabel="Add Experience"
                onAction={() => setExpModal({ open: true, item: null })}
              />
              {profile.experiences.length === 0 ? (
                <EmptyState
                  title="No internships or work experience added yet"
                  description="Add internships, teaching assistantships, or engineering roles."
                  actionLabel="Add Experience"
                  onAction={() => setExpModal({ open: true, item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {profile.experiences.map((exp) => (
                    <article key={exp.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">{exp.role}</h3>
                          <p className="text-sm text-slate-700">
                            {exp.organization}
                            {exp.location ? ` · ${exp.location}` : ""}
                          </p>
                          {(exp.start_date || exp.end_date) && (
                            <p className="mt-0.5 text-xs text-slate-500">
                              {[exp.start_date, exp.end_date].filter(Boolean).join(" – ")}
                            </p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setExpModal({ open: true, item: exp })}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              setDeleteTarget({
                                kind: "experience",
                                id: exp.id,
                                label: `${exp.role} at ${exp.organization}`,
                              })
                            }
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {exp.responsibilities && (
                        <p className="mt-2.5 whitespace-pre-line text-sm text-slate-700">{exp.responsibilities}</p>
                      )}
                      {exp.achievements && (
                        <p className="mt-2 text-xs text-slate-600">
                          <span className="font-semibold text-slate-700">Impact / Achievements:</span> {exp.achievements}
                        </p>
                      )}
                      {exp.technologies_used && (
                        <p className="mt-1.5 text-xs text-slate-500">
                          <span className="font-medium text-slate-700">Technologies:</span> {exp.technologies_used}
                        </p>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* H. Achievements & Certifications */}
          {activeSection === "achievements" && (
            <div>
              <SectionHeader
                title="Achievements & Certifications"
                subtitle="Scholarships, academic honors, competition ranks, and verified certifications."
                actionLabel="Add Record"
                onAction={() => setAchModal({ open: true, item: null })}
              />
              {profile.achievements.length === 0 ? (
                <EmptyState
                  title="No achievements or certifications yet"
                  description="Add scholarships, honors, awards, or technical certifications."
                  actionLabel="Add Achievement / Certification"
                  onAction={() => setAchModal({ open: true, item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {profile.achievements.map((ach) => (
                    <article key={ach.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded bg-navy-50 px-2 py-0.5 text-[11px] font-medium capitalize text-navy-800">
                              {ach.entry_type}
                            </span>
                            {ach.date_awarded && <span className="text-xs text-slate-500">{ach.date_awarded}</span>}
                          </div>
                          <h3 className="mt-1 font-medium text-navy-900">{ach.title}</h3>
                          {ach.issuing_organization && (
                            <p className="text-xs text-slate-600">Issued by {ach.issuing_organization}</p>
                          )}
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setAchModal({ open: true, item: ach })}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: "achievement", id: ach.id, label: ach.title })}
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {ach.description && <p className="mt-2 text-sm text-slate-700">{ach.description}</p>}
                      {safeUrl(ach.credential_url) && (
                        <a
                          href={safeUrl(ach.credential_url)!}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-xs font-medium text-navy-700 hover:underline"
                        >
                          View credential ↗
                        </a>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* I. Publications */}
          {activeSection === "publications" && (
            <div>
              <SectionHeader
                title="Publications"
                subtitle="Journal papers, conference proceedings, workshop papers, and preprints."
                actionLabel="Add Publication"
                onAction={() => setPubModal({ open: true, item: null })}
              />
              {profile.publications.length === 0 ? (
                <EmptyState
                  title="No publications added yet"
                  description="Add peer-reviewed articles, conference papers, or arXiv preprints you authored."
                  actionLabel="Add Publication"
                  onAction={() => setPubModal({ open: true, item: null })}
                />
              ) : (
                <div className="space-y-4">
                  {profile.publications.map((pub) => (
                    <article key={pub.id} className="rounded-lg border border-slate-200 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <h3 className="font-medium text-navy-900">{pub.title}</h3>
                          {pub.authors && <p className="mt-0.5 text-xs text-slate-600">{pub.authors}</p>}
                          <p className="mt-0.5 text-xs text-slate-500">
                            {[pub.journal_or_conference, pub.publication_date].filter(Boolean).join(" · ")}
                          </p>
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => setPubModal({ open: true, item: pub })}
                            className="rounded border border-slate-200 px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeleteTarget({ kind: "publication", id: pub.id, label: pub.title })}
                            className="rounded border border-red-200 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-50"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                      {pub.abstract && <p className="mt-2.5 text-sm text-slate-700">{pub.abstract}</p>}
                      {safeUrl(pub.doi_or_url) && (
                        <a
                          href={safeUrl(pub.doi_or_url)!}
                          target="_blank"
                          rel="noreferrer"
                          className="mt-2 inline-block text-xs font-medium text-navy-700 hover:underline"
                        >
                          DOI / Paper Link ↗
                        </a>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Add / Edit Modals */}
      <EducationFormModal
        open={eduModal.open}
        initial={eduModal.item}
        onClose={() => setEduModal({ open: false, item: null })}
        onSave={handleSaveEducation}
      />
      <SkillFormModal
        open={skillModal.open}
        mode={skillModal.mode}
        initial={skillModal.item}
        onClose={() => setSkillModal({ open: false, mode: "technical", item: null })}
        onSave={handleSaveSkill}
      />
      <ProjectFormModal
        open={projectModal.open}
        entryType={projectModal.entryType}
        initial={projectModal.item}
        onClose={() => setProjectModal({ open: false, entryType: "project", item: null })}
        onSave={handleSaveProject}
      />
      <ExperienceFormModal
        open={expModal.open}
        initial={expModal.item}
        onClose={() => setExpModal({ open: false, item: null })}
        onSave={handleSaveExperience}
      />
      <AchievementFormModal
        open={achModal.open}
        initial={achModal.item}
        onClose={() => setAchModal({ open: false, item: null })}
        onSave={handleSaveAchievement}
      />
      <PublicationFormModal
        open={pubModal.open}
        initial={pubModal.item}
        onClose={() => setPubModal({ open: false, item: null })}
        onSave={handleSavePublication}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmDeleteModal
        open={Boolean(deleteTarget)}
        itemLabel={deleteTarget?.label ?? ""}
        deleting={deleting}
        error={deleteError}
        onCancel={() => {
          if (!deleting) {
            setDeleteTarget(null);
            setDeleteError(null);
          }
        }}
        onConfirm={() => void handleConfirmDelete()}
      />
    </div>
  );
}
