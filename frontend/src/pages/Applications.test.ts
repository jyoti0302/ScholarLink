import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import SelectedProfileItemsPanel from "../components/applications/SelectedProfileItemsPanel";
import Navbar from "../components/Navbar";
import {
  APPLICATION_STATUSES,
  ApplicationsProvider,
  applySelectionsToList,
  applyStatusToList,
  countSelectedItems,
  createEmptySelections,
  readStoredApplications,
  storageKeyForStudent,
  toggleSelectedId,
  validateStatusTransition,
  writeStoredApplications,
  type ProfessorApplication,
} from "../context/ApplicationsContext";
import { AuthProvider } from "../context/AuthContext";
import type { StudentCompleteProfile } from "../types/api";
import ApplicationWorkspacePage from "./ApplicationWorkspacePage";
import MyApplicationsPage from "./MyApplicationsPage";

function makeApplication(overrides: Partial<ProfessorApplication> = {}): ProfessorApplication {
  const now = "2026-11-22T17:00:00.000Z";
  return {
    professorId: 101,
    professorName: "Prof. Pabitra Mitra",
    department: "Computer Science and Engineering",
    university: "IIT Kharagpur",
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
    ...overrides,
  };
}

function makeStudentProfile(overrides: Partial<StudentCompleteProfile> = {}): StudentCompleteProfile {
  const now = "2026-11-22T12:00:00Z";
  return {
    id: 7,
    email: "student@iitkgp.ac.in",
    full_name: "Aarav Sharma",
    phone: "+91 98765 43210",
    institution: "IIT Kharagpur",
    department: "CSE",
    degree_program: "B.Tech",
    graduation_year: 2027,
    current_year_or_semester: "6th Semester",
    research_interests_summary: "Transformer architectures, low-resource NLP, and information retrieval.",
    github_url: "https://github.com/aarav",
    linkedin_url: "https://linkedin.com/in/aarav",
    portfolio_url: null,
    created_at: now,
    updated_at: now,
    educations: [],
    skills: [
      {
        id: 11,
        name: "PyTorch",
        category: "technical",
        proficiency_level: "Advanced",
        experience_context: "Built transformer training pipelines",
        created_at: now,
        updated_at: now,
      },
      {
        id: 12,
        name: "Experimental Evaluation",
        category: "research",
        proficiency_level: "Intermediate",
        experience_context: "Ablation studies on retrieval benchmarks",
        created_at: now,
        updated_at: now,
      },
    ],
    projects: [
      {
        id: 21,
        entry_type: "project",
        title: "Hybrid BGE-M3 Academic Retriever",
        role: "Lead ML Engineer",
        organization: "KGP AI Group",
        description: "Dense + sparse hybrid search system for faculty discovery.",
        problem_statement: null,
        methodology: "Implemented RRF fusion and domain disambiguation.",
        technologies_tools: "Python, PyTorch, Qdrant, FastAPI",
        outcomes_results: "Improved Recall@10 by 24% across 7 research queries.",
        start_date: "Jan 2026",
        end_date: "Apr 2026",
        project_url: null,
        github_url: "https://github.com/aarav/retriever",
        associated_skills: null,
        created_at: now,
        updated_at: now,
      },
      {
        id: 22,
        entry_type: "research_experience",
        title: "Low-Resource Indian Language Summarization",
        role: "Undergraduate Research Assistant",
        organization: "CNeRG Lab",
        description: "Parameter-efficient fine-tuning for Bengali and Hindi news.",
        problem_statement: null,
        methodology: "LoRA adapters with cross-lingual retrieval augmentation.",
        technologies_tools: "Hugging Face, LoRA, PyTorch",
        outcomes_results: "Achieved +3.2 ROUGE-L over baseline mBART.",
        start_date: "May 2025",
        end_date: "Dec 2025",
        project_url: null,
        github_url: null,
        associated_skills: null,
        created_at: now,
        updated_at: now,
      },
    ],
    experiences: [
      {
        id: 31,
        organization: "Microsoft Research India",
        role: "Research Intern",
        location: "Bengaluru",
        start_date: "May 2025",
        end_date: "Jul 2025",
        responsibilities: "Designed evaluation harnesses for multilingual LLMs.",
        achievements: "Reduced inference latency by 18% via quantized KV-caching.",
        technologies_used: "Python, ONNX, PyTorch",
        created_at: now,
        updated_at: now,
      },
    ],
    achievements: [
      {
        id: 41,
        entry_type: "achievement",
        title: "Institute Academic Excellence Award",
        issuing_organization: "IIT Kharagpur",
        date_awarded: "2025",
        description: "Top 5% of Computer Science batch.",
        credential_url: null,
        created_at: now,
        updated_at: now,
      },
    ],
    publications: [
      {
        id: 51,
        title: "Cross-Lingual Retrieval for Academic Discovery",
        authors: "A. Sharma, P. Mitra",
        journal_or_conference: "ACL Findings",
        publication_date: "2026",
        doi_or_url: "https://doi.org/10.1000/xyz",
        abstract: "Evaluates hybrid sparse-dense retrieval for faculty expertise matching.",
        verification_or_source: null,
        created_at: now,
        updated_at: now,
      },
    ],
    completion: {
      percentage: 100,
      completed_count: 7,
      total_count: 7,
      items: [],
    },
    ...overrides,
  };
}

describe("My Applications navigation & architecture", () => {
  it("replaces Resume Builder with My Applications in Navbar", () => {
    const html = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/"] },
        React.createElement(AuthProvider, null, React.createElement(Navbar)),
      ),
    );
    expect(html).toContain("Discover Professors");
    expect(html).toContain("My Academic Profile");
    expect(html).toContain("My Applications");
    expect(html).toContain("About");
    expect(html).not.toContain("Resume Builder");
  });

  it("renders honest empty state on My Applications when no professor applications exist", () => {
    const html = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/applications"] },
        React.createElement(
          AuthProvider,
          null,
          React.createElement(ApplicationsProvider, null, React.createElement(MyApplicationsPage)),
        ),
      ),
    );
    expect(html).toContain("My Applications");
    expect(html).toContain("No professor applications yet");
    expect(html).toContain("Create Tailored Resume");
    expect(html).toContain("Create Cover Letter");
    expect(html).toContain("Generate Outreach Email");
  });

  it("renders a graceful not-found prompt for an uninitiated application workspace", () => {
    const html = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        { initialEntries: ["/applications/42"] },
        React.createElement(
          AuthProvider,
          null,
          React.createElement(
            ApplicationsProvider,
            null,
            React.createElement(
              Routes,
              null,
              React.createElement(Route, {
                path: "/applications/:professorId",
                element: React.createElement(ApplicationWorkspacePage),
              }),
            ),
          ),
        ),
      ),
    );
    expect(html).toContain("Application workspace not found");
    expect(html).toContain("/professors/42");
  });
});

describe("Stage 6.0: Five-state application status workflow & validation", () => {
  it("defines all five required application statuses in order", () => {
    expect(APPLICATION_STATUSES.map((s) => s.value)).toEqual([
      "not_started",
      "in_progress",
      "ready_to_review",
      "ready_to_send",
      "sent",
    ]);
    expect(APPLICATION_STATUSES.map((s) => s.label)).toEqual([
      "Not Started",
      "In Progress",
      "Ready to Review",
      "Ready to Send",
      "Sent",
    ]);
  });

  it("blocks ready_to_review, ready_to_send, and sent when no documents exist", () => {
    const app = makeApplication({ status: "in_progress" });
    expect(validateStatusTransition(app, "ready_to_review").allowed).toBe(false);
    expect(validateStatusTransition(app, "ready_to_send", { explicitApproval: true }).allowed).toBe(false);
    expect(validateStatusTransition(app, "sent", { confirmSubmission: true }).allowed).toBe(false);
  });

  it("enforces explicit student approval for ready_to_send and confirmation for sent", () => {
    const withDoc = makeApplication({
      status: "in_progress",
      resumeVersions: [
        {
          id: "r1",
          kind: "resume",
          title: "Tailored Resume v1",
          version: 1,
          status: "draft",
          updatedAt: "2026-11-22T17:10:00.000Z",
        },
      ],
    });

    // Cannot revert to not_started once documents exist
    expect(validateStatusTransition(withDoc, "not_started").allowed).toBe(false);

    // Can transition to ready_to_review
    const step1 = applyStatusToList([withDoc], 101, "ready_to_review");
    expect(step1.result.allowed).toBe(true);
    expect(step1.next[0].status).toBe("ready_to_review");

    // Cannot mark ready_to_send without explicitApproval
    expect(validateStatusTransition(step1.next[0], "ready_to_send").allowed).toBe(false);

    // Can mark ready_to_send with explicitApproval
    const step2 = applyStatusToList(step1.next, 101, "ready_to_send", { explicitApproval: true });
    expect(step2.result.allowed).toBe(true);
    expect(step2.next[0].status).toBe("ready_to_send");
    expect(step2.next[0].studentApproved).toBe(true);

    // Cannot mark sent without confirmSubmission
    expect(validateStatusTransition(step2.next[0], "sent").allowed).toBe(false);

    // Can mark sent with confirmSubmission
    const step3 = applyStatusToList(step2.next, 101, "sent", { confirmSubmission: true });
    expect(step3.result.allowed).toBe(true);
    expect(step3.next[0].status).toBe("sent");
    expect(step3.next[0].sentAt).not.toBeNull();
  });

  it("never automatically promotes status to ready_to_send or sent when saving selections", () => {
    const app = makeApplication({ status: "not_started" });
    const next = applySelectionsToList([app], 101, {
      ...createEmptySelections(),
      projectIds: [21],
    });
    expect(next[0].status).toBe("in_progress");
    expect(next[0].studentApproved).toBe(false);
    expect(next[0].sentAt).toBeNull();
  });
});

describe("Stage 6.1: Professor-specific profile selection, isolation & empty sections", () => {
  it("loads and renders all real student profile fields for projects, internships, skills, research, achievements, and publications", () => {
    const profile = makeStudentProfile();
    const html = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(SelectedProfileItemsPanel, {
          professorName: "Prof. Pabitra Mitra",
          profile,
          savedSelections: {
            ...createEmptySelections(),
            projectIds: [21],
            technicalSkillIds: [11],
            includeResearchInterests: true,
          },
          onSaveSelections: () => {},
        }),
      ),
    );

    // Project required details
    expect(html).toContain("Hybrid BGE-M3 Academic Retriever");
    expect(html).toContain("Dense + sparse hybrid search system for faculty discovery.");
    expect(html).toContain("Python, PyTorch, Qdrant, FastAPI");
    expect(html).toContain("Lead ML Engineer");
    expect(html).toContain("Improved Recall@10 by 24% across 7 research queries.");

    // Internship required details
    expect(html).toContain("Microsoft Research India");
    expect(html).toContain("Research Intern");
    expect(html).toContain("May 2025 – Jul 2025");
    expect(html).toContain("Designed evaluation harnesses for multilingual LLMs.");
    expect(html).toContain("Reduced inference latency by 18% via quantized KV-caching.");

    // Skills, Research Experience, Achievements, Publications
    expect(html).toContain("PyTorch");
    expect(html).toContain("Experimental Evaluation");
    expect(html).toContain("Low-Resource Indian Language Summarization");
    expect(html).toContain("Institute Academic Excellence Award");
    expect(html).toContain("Cross-Lingual Retrieval for Academic Discovery");
    expect(html).toContain("Save Selections");
  });

  it("selects and deselects items and calculates live counts accurately", () => {
    let projectIds: number[] = [];
    projectIds = toggleSelectedId(projectIds, 21);
    projectIds = toggleSelectedId(projectIds, 22);
    expect(projectIds).toEqual([21, 22]);

    projectIds = toggleSelectedId(projectIds, 21);
    expect(projectIds).toEqual([22]);

    const selections = {
      ...createEmptySelections(),
      projectIds,
      technicalSkillIds: [11],
      researchSkillIds: [12],
      includeResearchInterests: true,
      experienceIds: [31],
      achievementIds: [41],
      publicationIds: [51],
    };
    expect(countSelectedItems(selections)).toBe(7);
  });

  it("saves and restores selections via localStorage round-trip", () => {
    const store = new Map<string, string>();
    const mockLocalStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => {
        store.set(k, v);
      },
      removeItem: (k: string) => {
        store.delete(k);
      },
    };
    Object.defineProperty(globalThis, "localStorage", { value: mockLocalStorage, configurable: true });

    const key = storageKeyForStudent(7);
    const app = makeApplication({ professorId: 101 });
    const updated = applySelectionsToList([app], 101, {
      ...createEmptySelections(),
      projectIds: [21],
      experienceIds: [31],
      includeResearchInterests: true,
    });
    writeStoredApplications(key, updated);

    const restored = readStoredApplications(key);
    expect(restored).toHaveLength(1);
    expect(restored[0].selections.projectIds).toEqual([21]);
    expect(restored[0].selections.experienceIds).toEqual([31]);
    expect(restored[0].selections.includeResearchInterests).toBe(true);
    expect(restored[0].status).toBe("in_progress");
  });

  it("maintains strict isolation between two professor workspaces and keeps master profile unchanged", () => {
    const masterProfile = makeStudentProfile();
    const masterSnapshot = JSON.stringify(masterProfile);

    const profA = makeApplication({ professorId: 101, professorName: "Prof. A (NLP)" });
    const profB = makeApplication({ professorId: 202, professorName: "Prof. B (Vision)" });

    // Update selections for Professor A only
    const afterProfA = applySelectionsToList([profA, profB], 101, {
      ...createEmptySelections(),
      projectIds: [21],
      technicalSkillIds: [11],
      includeResearchInterests: true,
    });

    // Professor A has NLP selections; Professor B remains completely untouched
    expect(afterProfA[0].selections.projectIds).toEqual([21]);
    expect(afterProfA[0].selections.technicalSkillIds).toEqual([11]);
    expect(afterProfA[1].selections.projectIds).toEqual([]);
    expect(afterProfA[1].selections.technicalSkillIds).toEqual([]);
    expect(afterProfA[1].status).toBe("not_started");

    // Update selections for Professor B independently
    const afterProfB = applySelectionsToList(afterProfA, 202, {
      ...createEmptySelections(),
      experienceIds: [31],
      publicationIds: [51],
    });
    expect(afterProfB[0].selections.projectIds).toEqual([21]);
    expect(afterProfB[0].selections.publicationIds).toEqual([]);
    expect(afterProfB[1].selections.experienceIds).toEqual([31]);
    expect(afterProfB[1].selections.publicationIds).toEqual([51]);

    // Master profile remains completely untouched
    expect(JSON.stringify(masterProfile)).toBe(masterSnapshot);
  });

  it("handles empty optional profile sections gracefully without fabricated data", () => {
    const minimalProfile = makeStudentProfile({
      research_interests_summary: null,
      projects: [],
      skills: [],
      experiences: [],
      achievements: [],
      publications: [],
    });

    const html = renderToStaticMarkup(
      React.createElement(
        MemoryRouter,
        null,
        React.createElement(SelectedProfileItemsPanel, {
          professorName: "Prof. Pabitra Mitra",
          profile: minimalProfile,
          savedSelections: createEmptySelections(),
          onSaveSelections: () => {},
        }),
      ),
    );

    expect(html).toContain("No projects in your Academic Profile yet.");
    expect(html).toContain("No research experience entries in your Academic Profile yet.");
    expect(html).toContain("No technical skills in your Academic Profile yet.");
    expect(html).toContain("No research interests or research skills listed in your Academic Profile yet.");
    expect(html).toContain("No internships or work experience records in your Academic Profile yet.");
    expect(html).toContain("No achievements or certifications in your Academic Profile yet.");
    expect(html).toContain("No publications in your Academic Profile yet (optional).");
  });
});
