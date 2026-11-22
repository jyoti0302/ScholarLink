import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ResumeLength, ResumeTemplate, TailoredResumeContent } from "../types/api";
import { useAuth } from "./AuthContext";

export type ApplicationStatus =
  | "not_started"
  | "in_progress"
  | "ready_to_review"
  | "ready_to_send"
  | "sent";

export type DocumentKind = "resume" | "cover_letter" | "outreach_email";

export interface ApplicationStatusMeta {
  value: ApplicationStatus;
  label: string;
  description: string;
  badgeClassName: string;
}

export const APPLICATION_STATUSES: ApplicationStatusMeta[] = [
  {
    value: "not_started",
    label: "Not Started",
    description: "No application preparation yet.",
    badgeClassName: "bg-slate-100 text-slate-700 ring-slate-200",
  },
  {
    value: "in_progress",
    label: "In Progress",
    description: "Application materials or profile selections are being prepared.",
    badgeClassName: "bg-amber-50 text-amber-800 ring-amber-200",
  },
  {
    value: "ready_to_review",
    label: "Ready to Review",
    description: "Required documents have been generated and await student review.",
    badgeClassName: "bg-sky-50 text-sky-800 ring-sky-200",
  },
  {
    value: "ready_to_send",
    label: "Ready to Send",
    description: "Student has explicitly reviewed and approved the application.",
    badgeClassName: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  },
  {
    value: "sent",
    label: "Sent",
    description: "Student has confirmed actual submission to the professor.",
    badgeClassName: "bg-navy-50 text-navy-800 ring-navy-200",
  },
];

export const APPLICATION_STATUS_MAP: Record<ApplicationStatus, ApplicationStatusMeta> = APPLICATION_STATUSES.reduce(
  (acc, item) => {
    acc[item.value] = item;
    return acc;
  },
  {} as Record<ApplicationStatus, ApplicationStatusMeta>,
);

export interface ApplicationDocumentVersion {
  id: string;
  kind: DocumentKind;
  title: string;
  version: number;
  status: "draft" | "ready" | "approved";
  updatedAt: string;
  // Stage 6.2 rich version metadata (optional for backward compatibility with existing drafts)
  professorId?: number;
  studentId?: number | null;
  targetPosition?: string | null;
  template?: ResumeTemplate;
  preferredLength?: ResumeLength;
  generationMode?: "gemini" | "grounded_fallback";
  providerNotice?: string | null;
  selectedSourceIds?: ApplicationProfileSelections;
  content?: TailoredResumeContent;
  createdAt?: string;
}

export interface NewResumeVersionInput {
  title: string;
  targetPosition?: string | null;
  template: ResumeTemplate;
  preferredLength: ResumeLength;
  generationMode: "gemini" | "grounded_fallback";
  providerNotice?: string | null;
  selectedSourceIds: ApplicationProfileSelections;
  content: TailoredResumeContent;
  studentId?: number | null;
}

export interface UpdateResumeVersionInput {
  title?: string;
  targetPosition?: string | null;
  template?: ResumeTemplate;
  preferredLength?: ResumeLength;
  status?: "draft" | "approved";
  content?: TailoredResumeContent;
}

export interface ApplicationProfileSelections {
  projectIds: number[];
  researchExperienceIds: number[];
  technicalSkillIds: number[];
  researchSkillIds: number[];
  includeResearchInterests: boolean;
  experienceIds: number[];
  achievementIds: number[];
  publicationIds: number[];
}

export function createEmptySelections(): ApplicationProfileSelections {
  return {
    projectIds: [],
    researchExperienceIds: [],
    technicalSkillIds: [],
    researchSkillIds: [],
    includeResearchInterests: false,
    experienceIds: [],
    achievementIds: [],
    publicationIds: [],
  };
}

export function countSelectedItems(selections: ApplicationProfileSelections): number {
  return (
    selections.projectIds.length +
    selections.researchExperienceIds.length +
    selections.technicalSkillIds.length +
    selections.researchSkillIds.length +
    (selections.includeResearchInterests ? 1 : 0) +
    selections.experienceIds.length +
    selections.achievementIds.length +
    selections.publicationIds.length
  );
}

export function toggleSelectedId(ids: number[], targetId: number): number[] {
  return ids.includes(targetId) ? ids.filter((id) => id !== targetId) : [...ids, targetId];
}

export interface ProfessorApplication {
  professorId: number;
  professorName: string;
  department: string;
  university: string;
  status: ApplicationStatus;
  studentApproved: boolean;
  approvedAt: string | null;
  sentAt: string | null;
  notes: string;
  selections: ApplicationProfileSelections;
  resumeVersions: ApplicationDocumentVersion[];
  coverLetterVersions: ApplicationDocumentVersion[];
  outreachEmailDrafts: ApplicationDocumentVersion[];
  createdAt: string;
  updatedAt: string;
}

export interface ProfessorApplicationSeed {
  professorId: number;
  professorName: string;
  department?: string;
  university?: string;
}

export interface StatusTransitionOptions {
  explicitApproval?: boolean;
  confirmSubmission?: boolean;
}

export interface StatusTransitionResult {
  allowed: boolean;
  reason?: string;
}

export function countApplicationDocuments(app: ProfessorApplication): number {
  return app.resumeVersions.length + app.coverLetterVersions.length + app.outreachEmailDrafts.length;
}

export function validateStatusTransition(
  app: ProfessorApplication,
  nextStatus: ApplicationStatus,
  opts: StatusTransitionOptions = {},
): StatusTransitionResult {
  if (nextStatus === app.status) {
    return { allowed: true };
  }

  const totalDocs = countApplicationDocuments(app);

  if (nextStatus === "not_started") {
    if (totalDocs > 0) {
      return {
        allowed: false,
        reason: "Cannot mark as Not Started after documents have been generated. Use In Progress instead.",
      };
    }
    return { allowed: true };
  }

  if (nextStatus === "in_progress") {
    return { allowed: true };
  }

  if (nextStatus === "ready_to_review") {
    if (totalDocs === 0) {
      return {
        allowed: false,
        reason: "Generate at least one application document before marking as Ready to Review.",
      };
    }
    return { allowed: true };
  }

  if (nextStatus === "ready_to_send") {
    if (totalDocs === 0) {
      return {
        allowed: false,
        reason: "Cannot mark as Ready to Send until at least one application document has been generated.",
      };
    }
    if (!opts.explicitApproval && !app.studentApproved) {
      return {
        allowed: false,
        reason: "Explicit student review and approval is required before marking as Ready to Send.",
      };
    }
    return { allowed: true };
  }

  if (nextStatus === "sent") {
    if (totalDocs === 0) {
      return {
        allowed: false,
        reason: "Cannot mark as Sent without generated application documents.",
      };
    }
    if (app.status !== "ready_to_send" && !app.studentApproved) {
      return {
        allowed: false,
        reason: "Approve the application as Ready to Send before confirming submission.",
      };
    }
    if (!opts.confirmSubmission) {
      return {
        allowed: false,
        reason: "Explicit student submission confirmation is required to mark an application as Sent.",
      };
    }
    return { allowed: true };
  }

  return { allowed: false, reason: "Unsupported application status." };
}

function normalizeStatus(raw: unknown): ApplicationStatus {
  if (raw === "ready") return "ready_to_send";
  if (
    raw === "not_started" ||
    raw === "in_progress" ||
    raw === "ready_to_review" ||
    raw === "ready_to_send" ||
    raw === "sent"
  ) {
    return raw;
  }
  return "not_started";
}

function normalizeNumberArray(raw: unknown): number[] {
  if (!Array.isArray(raw)) return [];
  return Array.from(new Set(raw.filter((v): v is number => typeof v === "number" && Number.isInteger(v))));
}

function normalizeApplication(raw: Record<string, unknown>): ProfessorApplication | null {
  const professorId = Number(raw.professorId);
  if (!Number.isInteger(professorId) || professorId <= 0) return null;

  const rawSelections = (raw.selections as Record<string, unknown> | undefined) ?? {};
  const selections: ApplicationProfileSelections = {
    projectIds: normalizeNumberArray(rawSelections.projectIds ?? raw.selectedProjectIds),
    researchExperienceIds: normalizeNumberArray(rawSelections.researchExperienceIds),
    technicalSkillIds: normalizeNumberArray(rawSelections.technicalSkillIds ?? raw.selectedSkillIds),
    researchSkillIds: normalizeNumberArray(rawSelections.researchSkillIds),
    includeResearchInterests: Boolean(rawSelections.includeResearchInterests),
    experienceIds: normalizeNumberArray(rawSelections.experienceIds ?? raw.selectedExperienceIds),
    achievementIds: normalizeNumberArray(rawSelections.achievementIds),
    publicationIds: normalizeNumberArray(rawSelections.publicationIds),
  };

  const now = new Date().toISOString();
  const status = normalizeStatus(raw.status);

  return {
    professorId,
    professorName: typeof raw.professorName === "string" && raw.professorName ? raw.professorName : `Professor #${professorId}`,
    department: typeof raw.department === "string" ? raw.department : "",
    university: typeof raw.university === "string" ? raw.university : "",
    status,
    studentApproved: Boolean(raw.studentApproved) || status === "ready_to_send" || status === "sent",
    approvedAt: typeof raw.approvedAt === "string" ? raw.approvedAt : null,
    sentAt: typeof raw.sentAt === "string" ? raw.sentAt : null,
    notes: typeof raw.notes === "string" ? raw.notes : "",
    selections,
    resumeVersions: Array.isArray(raw.resumeVersions) ? (raw.resumeVersions as ApplicationDocumentVersion[]) : [],
    coverLetterVersions: Array.isArray(raw.coverLetterVersions)
      ? (raw.coverLetterVersions as ApplicationDocumentVersion[])
      : [],
    outreachEmailDrafts: Array.isArray(raw.outreachEmailDrafts)
      ? (raw.outreachEmailDrafts as ApplicationDocumentVersion[])
      : [],
    createdAt: typeof raw.createdAt === "string" ? raw.createdAt : now,
    updatedAt: typeof raw.updatedAt === "string" ? raw.updatedAt : now,
  };
}

export function storageKeyForStudent(studentId: number | null | undefined): string {
  return `scholarlink_applications_${studentId ?? "guest"}`;
}

export function readStoredApplications(key: string): ProfessorApplication[] {
  try {
    if (typeof localStorage === "undefined") return [];
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .map((item) => (item && typeof item === "object" ? normalizeApplication(item as Record<string, unknown>) : null))
      .filter((item): item is ProfessorApplication => item !== null);
  } catch {
    return [];
  }
}

export function writeStoredApplications(key: string, items: ProfessorApplication[]): void {
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(key, JSON.stringify(items));
    }
  } catch {
    /* ignore storage quota errors */
  }
}

export function applySelectionsToList(
  applications: ProfessorApplication[],
  professorId: number,
  selections: ApplicationProfileSelections,
  now: string = new Date().toISOString(),
): ProfessorApplication[] {
  const cloned: ApplicationProfileSelections = {
    projectIds: [...selections.projectIds],
    researchExperienceIds: [...selections.researchExperienceIds],
    technicalSkillIds: [...selections.technicalSkillIds],
    researchSkillIds: [...selections.researchSkillIds],
    includeResearchInterests: Boolean(selections.includeResearchInterests),
    experienceIds: [...selections.experienceIds],
    achievementIds: [...selections.achievementIds],
    publicationIds: [...selections.publicationIds],
  };

  return applications.map((app) => {
    if (app.professorId !== professorId) return app;
    const hasSelections = countSelectedItems(cloned) > 0;
    // Never automatically promote to ready_to_review, ready_to_send, or sent.
    const nextStatus: ApplicationStatus =
      app.status === "not_started" && hasSelections ? "in_progress" : app.status;
    return {
      ...app,
      selections: cloned,
      status: nextStatus,
      updatedAt: now,
    };
  });
}

export function applyStatusToList(
  applications: ProfessorApplication[],
  professorId: number,
  nextStatus: ApplicationStatus,
  opts: StatusTransitionOptions = {},
  now: string = new Date().toISOString(),
): { next: ProfessorApplication[]; result: StatusTransitionResult } {
  const target = applications.find((a) => a.professorId === professorId);
  if (!target) {
    return { next: applications, result: { allowed: false, reason: "Application workspace not found." } };
  }
  const validation = validateStatusTransition(target, nextStatus, opts);
  if (!validation.allowed) {
    return { next: applications, result: validation };
  }

  const next = applications.map((app) => {
    if (app.professorId !== professorId) return app;
    const studentApproved =
      nextStatus === "ready_to_send" || nextStatus === "sent"
        ? true
        : nextStatus === "not_started" || nextStatus === "in_progress" || nextStatus === "ready_to_review"
          ? false
          : app.studentApproved;
    return {
      ...app,
      status: nextStatus,
      studentApproved,
      approvedAt:
        nextStatus === "ready_to_send" ? now : studentApproved ? app.approvedAt : null,
      sentAt: nextStatus === "sent" ? now : app.sentAt,
      updatedAt: now,
    };
  });

  return { next, result: { allowed: true } };
}

function makeVersionId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function addResumeVersionToList(
  applications: ProfessorApplication[],
  professorId: number,
  input: NewResumeVersionInput,
  now: string = new Date().toISOString(),
): { next: ProfessorApplication[]; created: ApplicationDocumentVersion | null } {
  let created: ApplicationDocumentVersion | null = null;
  const next = applications.map((app) => {
    if (app.professorId !== professorId) return app;
    const nextVersionNum =
      app.resumeVersions.reduce((max, v) => (v.version > max ? v.version : max), 0) + 1;
    created = {
      id: makeVersionId("res"),
      kind: "resume",
      professorId,
      studentId: input.studentId ?? null,
      version: nextVersionNum,
      title: input.title.trim() || `Tailored Resume v${nextVersionNum}`,
      targetPosition: input.targetPosition ?? null,
      template: input.template,
      preferredLength: input.preferredLength,
      status: "draft",
      generationMode: input.generationMode,
      providerNotice: input.providerNotice ?? null,
      selectedSourceIds: JSON.parse(JSON.stringify(input.selectedSourceIds)) as ApplicationProfileSelections,
      content: JSON.parse(JSON.stringify(input.content)) as TailoredResumeContent,
      createdAt: now,
      updatedAt: now,
    };
    // Advance not_started / in_progress -> ready_to_review when a resume is generated;
    // NEVER automatically mark ready_to_send or sent.
    const nextStatus: ApplicationStatus =
      app.status === "not_started" || app.status === "in_progress" ? "ready_to_review" : app.status;
    return {
      ...app,
      resumeVersions: [created, ...app.resumeVersions],
      status: nextStatus,
      updatedAt: now,
    };
  });
  return { next, created };
}

export function updateResumeVersionInList(
  applications: ProfessorApplication[],
  professorId: number,
  versionId: string,
  updates: UpdateResumeVersionInput,
  now: string = new Date().toISOString(),
): ProfessorApplication[] {
  return applications.map((app) => {
    if (app.professorId !== professorId) return app;
    let changed = false;
    const updatedVersions = app.resumeVersions.map((ver) => {
      if (ver.id !== versionId) return ver;
      changed = true;
      return {
        ...ver,
        ...(updates.title !== undefined ? { title: updates.title } : {}),
        ...(updates.targetPosition !== undefined ? { targetPosition: updates.targetPosition } : {}),
        ...(updates.template !== undefined ? { template: updates.template } : {}),
        ...(updates.preferredLength !== undefined ? { preferredLength: updates.preferredLength } : {}),
        ...(updates.status !== undefined ? { status: updates.status } : {}),
        ...(updates.content !== undefined
          ? { content: JSON.parse(JSON.stringify(updates.content)) as TailoredResumeContent }
          : {}),
        updatedAt: now,
      };
    });
    if (!changed) return app;
    return {
      ...app,
      resumeVersions: updatedVersions,
      updatedAt: now,
    };
  });
}

export function duplicateResumeVersionInList(
  applications: ProfessorApplication[],
  professorId: number,
  versionId: string,
  now: string = new Date().toISOString(),
): { next: ProfessorApplication[]; duplicated: ApplicationDocumentVersion | null } {
  let duplicated: ApplicationDocumentVersion | null = null;
  const next = applications.map((app) => {
    if (app.professorId !== professorId) return app;
    const source = app.resumeVersions.find((v) => v.id === versionId);
    if (!source) return app;
    const nextVersionNum =
      app.resumeVersions.reduce((max, v) => (v.version > max ? v.version : max), 0) + 1;
    duplicated = {
      ...(JSON.parse(JSON.stringify(source)) as ApplicationDocumentVersion),
      id: makeVersionId("res"),
      version: nextVersionNum,
      title: `${source.title} (Copy)`,
      status: "draft",
      createdAt: now,
      updatedAt: now,
    };
    return {
      ...app,
      resumeVersions: [duplicated, ...app.resumeVersions],
      updatedAt: now,
    };
  });
  return { next, duplicated };
}

export function deleteResumeVersionFromList(
  applications: ProfessorApplication[],
  professorId: number,
  versionId: string,
  now: string = new Date().toISOString(),
): ProfessorApplication[] {
  return applications.map((app) => {
    if (app.professorId !== professorId) return app;
    const remaining = app.resumeVersions.filter((v) => v.id !== versionId);
    if (remaining.length === app.resumeVersions.length) return app;
    const remainingDocs = remaining.length + app.coverLetterVersions.length + app.outreachEmailDrafts.length;
    const nextStatus: ApplicationStatus =
      remainingDocs === 0 && (app.status === "ready_to_review" || app.status === "ready_to_send")
        ? "in_progress"
        : app.status;
    return {
      ...app,
      resumeVersions: remaining,
      status: nextStatus,
      studentApproved: remainingDocs === 0 ? false : app.studentApproved,
      updatedAt: now,
    };
  });
}

interface ApplicationsContextValue {
  applications: ProfessorApplication[];
  storageBackend: "localStorage";
  getApplication: (professorId: number) => ProfessorApplication | undefined;
  ensureApplication: (seed: ProfessorApplicationSeed) => ProfessorApplication;
  updateApplicationNotes: (professorId: number, notes: string) => void;
  updateApplicationSelections: (professorId: number, selections: ApplicationProfileSelections) => void;
  updateApplicationStatus: (
    professorId: number,
    status: ApplicationStatus,
    opts?: StatusTransitionOptions,
  ) => StatusTransitionResult;
  addResumeVersion: (professorId: number, input: NewResumeVersionInput) => ApplicationDocumentVersion | null;
  updateResumeVersion: (professorId: number, versionId: string, updates: UpdateResumeVersionInput) => void;
  duplicateResumeVersion: (professorId: number, versionId: string) => ApplicationDocumentVersion | null;
  deleteResumeVersion: (professorId: number, versionId: string) => void;
  removeApplication: (professorId: number) => void;
}

const ApplicationsContext = createContext<ApplicationsContextValue | null>(null);

export function ApplicationsProvider({ children }: { children: React.ReactNode }) {
  const { student } = useAuth();
  const storageKey = storageKeyForStudent(student?.id);
  const [applications, setApplications] = useState<ProfessorApplication[]>(() =>
    readStoredApplications(storageKey),
  );

  useEffect(() => {
    setApplications(readStoredApplications(storageKey));
  }, [storageKey]);

  const persist = useCallback(
    (updater: (prev: ProfessorApplication[]) => ProfessorApplication[]) => {
      setApplications((prev) => {
        const next = updater(prev);
        writeStoredApplications(storageKey, next);
        return next;
      });
    },
    [storageKey],
  );

  const getApplication = useCallback(
    (professorId: number) => applications.find((a) => a.professorId === professorId),
    [applications],
  );

  const ensureApplication = useCallback(
    (seed: ProfessorApplicationSeed): ProfessorApplication => {
      const existing = applications.find((a) => a.professorId === seed.professorId);
      const now = new Date().toISOString();
      if (existing) {
        const updated: ProfessorApplication = {
          ...existing,
          professorName: seed.professorName || existing.professorName,
          department: seed.department || existing.department,
          university: seed.university || existing.university,
        };
        if (
          updated.professorName !== existing.professorName ||
          updated.department !== existing.department ||
          updated.university !== existing.university
        ) {
          persist((prev) => prev.map((a) => (a.professorId === seed.professorId ? updated : a)));
        }
        return updated;
      }

      const created: ProfessorApplication = {
        professorId: seed.professorId,
        professorName: seed.professorName || `Professor #${seed.professorId}`,
        department: seed.department || "",
        university: seed.university || "",
        status: "not_started",
        studentApproved: false,
        approvedAt: null,
        sentAt: null,
        notes: "",
        selections: createEmptySelections(),
        resumeVersions: [],
        coverLetterVersions: [],
        outreachEmailDrafts: [],
        createdAt: now,
        updatedAt: now,
      };
      persist((prev) => [created, ...prev.filter((a) => a.professorId !== seed.professorId)]);
      return created;
    },
    [applications, persist],
  );

  const updateApplicationNotes = useCallback(
    (professorId: number, notes: string) => {
      const now = new Date().toISOString();
      persist((prev) =>
        prev.map((a) =>
          a.professorId === professorId
            ? {
                ...a,
                notes,
                status: a.status === "not_started" && notes.trim() ? "in_progress" : a.status,
                updatedAt: now,
              }
            : a,
        ),
      );
    },
    [persist],
  );

  const updateApplicationSelections = useCallback(
    (professorId: number, selections: ApplicationProfileSelections) => {
      persist((prev) => applySelectionsToList(prev, professorId, selections));
    },
    [persist],
  );

  const updateApplicationStatus = useCallback(
    (
      professorId: number,
      status: ApplicationStatus,
      opts: StatusTransitionOptions = {},
    ): StatusTransitionResult => {
      const current = applications.find((a) => a.professorId === professorId);
      if (!current) {
        return { allowed: false, reason: "Application workspace not found." };
      }
      const validation = validateStatusTransition(current, status, opts);
      if (!validation.allowed) {
        return validation;
      }
      persist((prev) => applyStatusToList(prev, professorId, status, opts).next);
      return { allowed: true };
    },
    [applications, persist],
  );

  const addResumeVersion = useCallback(
    (professorId: number, input: NewResumeVersionInput): ApplicationDocumentVersion | null => {
      let createdRef: ApplicationDocumentVersion | null = null;
      persist((prev) => {
        const { next, created } = addResumeVersionToList(prev, professorId, {
          ...input,
          studentId: input.studentId ?? student?.id ?? null,
        });
        createdRef = created;
        return next;
      });
      return createdRef;
    },
    [persist, student?.id],
  );

  const updateResumeVersion = useCallback(
    (professorId: number, versionId: string, updates: UpdateResumeVersionInput) => {
      persist((prev) => updateResumeVersionInList(prev, professorId, versionId, updates));
    },
    [persist],
  );

  const duplicateResumeVersion = useCallback(
    (professorId: number, versionId: string): ApplicationDocumentVersion | null => {
      let dupRef: ApplicationDocumentVersion | null = null;
      persist((prev) => {
        const { next, duplicated } = duplicateResumeVersionInList(prev, professorId, versionId);
        dupRef = duplicated;
        return next;
      });
      return dupRef;
    },
    [persist],
  );

  const deleteResumeVersion = useCallback(
    (professorId: number, versionId: string) => {
      persist((prev) => deleteResumeVersionFromList(prev, professorId, versionId));
    },
    [persist],
  );

  const removeApplication = useCallback(
    (professorId: number) => {
      persist((prev) => prev.filter((a) => a.professorId !== professorId));
    },
    [persist],
  );

  const value = useMemo<ApplicationsContextValue>(
    () => ({
      applications,
      storageBackend: "localStorage",
      getApplication,
      ensureApplication,
      updateApplicationNotes,
      updateApplicationSelections,
      updateApplicationStatus,
      addResumeVersion,
      updateResumeVersion,
      duplicateResumeVersion,
      deleteResumeVersion,
      removeApplication,
    }),
    [
      applications,
      getApplication,
      ensureApplication,
      updateApplicationNotes,
      updateApplicationSelections,
      updateApplicationStatus,
      addResumeVersion,
      updateResumeVersion,
      duplicateResumeVersion,
      deleteResumeVersion,
      removeApplication,
    ],
  );

  return <ApplicationsContext.Provider value={value}>{children}</ApplicationsContext.Provider>;
}

export function useApplications(): ApplicationsContextValue {
  const ctx = useContext(ApplicationsContext);
  if (!ctx) throw new Error("useApplications must be used inside ApplicationsProvider");
  return ctx;
}
