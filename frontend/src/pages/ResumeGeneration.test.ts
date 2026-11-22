import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import ResumePreview from "../components/applications/ResumePreview";
import {
  addResumeVersionToList,
  createEmptySelections,
  deleteResumeVersionFromList,
  duplicateResumeVersionInList,
  storageKeyForStudent,
  updateResumeVersionInList,
  type ProfessorApplication,
} from "../context/ApplicationsContext";
import type { TailoredResumeContent } from "../types/api";

function makeResumeContent(overrides: Partial<TailoredResumeContent> = {}): TailoredResumeContent {
  return {
    title: "Tailored NLP Resume",
    target_position: "Research Intern",
    template: "academic_research",
    preferred_length: "1_page",
    header: {
      full_name: "Aarav Sharma",
      email: "aarav@iitkgp.ac.in",
      phone: "+91-9876543210",
      institution: "IIT Kharagpur",
      department: "CSE",
      degree_program: "B.Tech",
      graduation_year: 2027,
      current_year_or_semester: "6th Semester",
      linkedin_url: "https://linkedin.com/in/aarav",
      github_url: "https://github.com/aarav",
      portfolio_url: null,
    },
    summary: "B.Tech CSE student focused on NLP and information retrieval.",
    research_interests: "Transformers, RAG, multilingual NLP",
    section_order: [
      "summary",
      "education",
      "research_interests",
      "skills",
      "projects",
      "research_experience",
      "experience",
      "publications",
      "achievements",
    ],
    enabled_sections: [
      "summary",
      "education",
      "research_interests",
      "skills",
      "projects",
      "research_experience",
      "experience",
      "publications",
      "achievements",
    ],
    education: [
      {
        source_id: 1,
        institution: "IIT Kharagpur",
        degree: "B.Tech",
        department_major: "CSE",
        duration: "2023 – 2027",
        cgpa_or_percentage: "9.1",
        relevant_coursework: "NLP, Deep Learning",
      },
    ],
    skills: [{ category: "Technical Skills", items: ["PyTorch", "BERT", "FastAPI"] }],
    projects: [
      {
        source_id: 101,
        entry_type: "project",
        title: "RAG Pipeline with BERT",
        role: "Lead",
        organization: "KGP AI",
        duration: "2026",
        technologies: "PyTorch, FAISS",
        bullets: ["Improved MRR@10 by 19%."],
        url: "https://github.com/aarav/rag",
        relevance_score: 6,
      },
    ],
    research_experience: [],
    experience: [],
    publications: [],
    achievements: [],
    alignment_highlights: [],
    ...overrides,
  };
}

function makeApp(professorId: number, professorName: string): ProfessorApplication {
  const now = "2026-11-22T18:00:00.000Z";
  return {
    professorId,
    professorName,
    department: "CSE",
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
  };
}

describe("Stage 6.2: Resume version management, isolation & live preview", () => {
  it("supports multiple versions per professor, editing, duplication, and safe deletion without affecting other professors", () => {
    const profA = makeApp(101, "Prof. A (NLP)");
    const profB = makeApp(202, "Prof. B (Vision)");
    const contentA = makeResumeContent({ title: "NLP Resume" });

    // Create v1 for Professor A
    const { next: afterV1, created: v1 } = addResumeVersionToList([profA, profB], 101, {
      title: "NLP Resume",
      template: "academic_research",
      preferredLength: "1_page",
      generationMode: "grounded_fallback",
      selectedSourceIds: { ...createEmptySelections(), projectIds: [101] },
      content: contentA,
      studentId: 7,
    });
    expect(v1).not.toBeNull();
    expect(v1?.version).toBe(1);
    expect(v1?.professorId).toBe(101);
    expect(v1?.studentId).toBe(7);
    // Advances status to ready_to_review, NEVER ready_to_send or sent
    expect(afterV1[0].status).toBe("ready_to_review");
    expect(afterV1[0].studentApproved).toBe(false);
    // Professor B remains completely isolated
    expect(afterV1[1].resumeVersions).toHaveLength(0);
    expect(afterV1[1].status).toBe("not_started");

    // Duplicate v1 -> creates v2 as draft
    const { next: afterDup, duplicated: v2 } = duplicateResumeVersionInList(afterV1, 101, v1!.id);
    expect(v2?.version).toBe(2);
    expect(v2?.status).toBe("draft");
    expect(afterDup[0].resumeVersions).toHaveLength(2);

    // Edit v2 without modifying v1 or Professor B
    const editedContent = makeResumeContent({
      title: "NLP Resume Final",
      summary: "Updated summary for Prof. A.",
    });
    const afterEdit = updateResumeVersionInList(afterDup, 101, v2!.id, {
      title: "NLP Resume Final",
      status: "approved",
      content: editedContent,
    });
    const savedV2 = afterEdit[0].resumeVersions.find((v) => v.id === v2!.id);
    const savedV1 = afterEdit[0].resumeVersions.find((v) => v.id === v1!.id);
    expect(savedV2?.status).toBe("approved");
    expect(savedV2?.content?.summary).toBe("Updated summary for Prof. A.");
    expect(savedV1?.content?.summary).toBe("B.Tech CSE student focused on NLP and information retrieval.");

    // Delete v1 -> v2 remains intact
    const afterDelete = deleteResumeVersionFromList(afterEdit, 101, v1!.id);
    expect(afterDelete[0].resumeVersions).toHaveLength(1);
    expect(afterDelete[0].resumeVersions[0].id).toBe(v2!.id);
  });

  it("isolates student storage keys so Student A cannot access Student B workspaces", () => {
    expect(storageKeyForStudent(1)).not.toBe(storageKeyForStudent(2));
    expect(storageKeyForStudent(1)).toBe("scholarlink_applications_1");
    expect(storageKeyForStudent(2)).toBe("scholarlink_applications_2");
  });

  it("renders ResumePreview across templates and respects enabled_sections", () => {
    const content = makeResumeContent({
      template: "technical_ai_ml",
      enabled_sections: ["summary", "skills", "projects"],
    });
    const html = renderToStaticMarkup(React.createElement(ResumePreview, { content }));
    expect(html).toContain("Aarav Sharma");
    expect(html).toContain('data-template="technical_ai_ml"');
    expect(html).toContain("Professional Summary");
    expect(html).toContain("RAG Pipeline with BERT");
    expect(html).toContain('href="mailto:aarav@iitkgp.ac.in"');
    expect(html).toContain('href="https://github.com/aarav"');
    // Disabled section is omitted
    expect(html).not.toContain("Education");
  });
});
