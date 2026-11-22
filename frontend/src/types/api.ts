// Mirrors backend/api/schemas.py (SearchRequestSchema / SearchResponseSchema) exactly.

export interface SearchRequest {
  query: string;
  limit?: number | null; // page size (default 20; null returns all qualifying)
  offset?: number;
  use_expansion?: boolean;
  university_id?: number | null;
  department_ids?: number[] | null;
  include_candidate_publications?: boolean;
  request_id?: string;
}

export interface SupportingEvidence {
  evidence_id: string | null;
  evidence_type: string;
  relevance_group?: string | null;
  topic_relevance_note?: string | null;
  title: string | null;
  snippet: string | null;
  source_url: string | null;
  verification_status: string | null;
  matched_by_query: string | null;
  score: number;
  authorship_note: string | null;
  role: string | null;
  sponsor: string | null;
  project_category: string | null;
}

export interface SearchProfessorResult {
  professor_id: number;
  professor_name: string;
  department: string;
  department_code: string;
  department_name: string;
  designation: string | null;
  email: string | null;
  profile_url: string | null;
  score: number;
  match_category: string;
  research_interests: string | null;
  biography?: string | null;
  evidence_counts: Record<string, number>;
  matched_topics: string[];
  matched_queries: string[];
  supporting_evidence: SupportingEvidence[];
  explanation: string;
}

export interface SearchResponse {
  request_id: string;
  query: string;
  expanded_queries: string[];
  status: string; // "ok" | "insufficient_evidence"
  message: string | null;
  search_latency_ms: number;
  total_results: number;
  total_qualifying_results?: number;
  offset?: number;
  limit?: number | null;
  has_more?: boolean;
  results: SearchProfessorResult[];
}

export interface ResearchTopic {
  id: number;
  topic_name: string;
  canonical_topic_name: string | null;
  domain_name: string | null;
  area_name: string | null;
  parent_topic_id: number | null;
  is_generic_root: boolean;
  is_noisy_artifact: boolean;
  description: string | null;
}

export interface ProfessorProfileProject {
  project_id: number;
  title: string;
  description: string | null;
  category: string;
  sponsor: string | null;
  status: string | null;
  role: string | null;
  source_url: string | null;
  is_administrative_or_grant: boolean;
}

export interface ProfessorProfilePublication {
  publication_id: number;
  title: string;
  abstract: string | null;
  doi: string | null;
  publication_year: number | null;
  journal_or_conference: string | null;
  paper_url: string | null;
  source_url: string | null;
  source_name: string | null;
  citation_count: number;
  author_position: string | null;
  verification_status: string;
  confidence_score: number | null;
  affiliation_evidence: string | null;
  is_unverified: boolean;
  authorship_note: string | null;
}

export interface ProfessorContactLink {
  label: string;
  url: string;
  source_url: string | null;
}

export interface ProfessorContactInfo {
  email: string | null;
  office_phone: string | null;
  office_room: string | null;
  department_address: string | null;
  department_office_contact: string | null;
  department_url: string | null;
  research_group_website: string | null;
  personal_webpage: string | null;
  bio_sketch_url: string | null;
  profile_url: string | null;
  academic_links: ProfessorContactLink[];
  source_url: string | null;
}

export interface ProfessorProfile {
  professor_id: number;
  name: string;
  designation: string | null;
  email: string | null;
  academic_unit: string | null;
  department_id: number;
  department_name: string | null;
  department_code: string | null;
  university_id: number | null;
  university_name: string | null;
  university_website: string | null;
  biography: string | null;
  educational_background: string | null;
  research_interests: string | null;
  research_group: string | null;
  profile_url: string | null;
  source_url: string | null;
  verification_status: string;
  orcid: string | null;
  irins_id: string | null;
  openalex_author_id: string | null;
  last_updated: string | null;
  contact_info?: ProfessorContactInfo | null;
  research_topics: ResearchTopic[];
  research_projects: ProfessorProfileProject[];
  verified_publications: ProfessorProfilePublication[];
  candidate_publications: ProfessorProfilePublication[];
}

// =========================================================================
// Stage 5.2 / 5.3: Student Authentication & Academic Profile Types
// =========================================================================

export interface StudentAuthSummary {
  id: number;
  email: string;
  full_name: string | null;
  institution: string | null;
  department: string | null;
  degree_program: string | null;
  graduation_year: number | null;
  current_year_or_semester: string | null;
  created_at: string;
  profile_completed: boolean;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  student: StudentAuthSummary;
}

export interface ProfileCompletionItem {
  key: string;
  label: string;
  weight: number;
  completed: boolean;
  section: string;
}

export interface ProfileCompletion {
  percentage: number;
  completed_count: number;
  total_count: number;
  items: ProfileCompletionItem[];
}

export interface StudentPersonalInfoUpdate {
  full_name?: string | null;
  phone?: string | null;
  institution?: string | null;
  department?: string | null;
  degree_program?: string | null;
  graduation_year?: number | null;
  current_year_or_semester?: string | null;
  research_interests_summary?: string | null;
  github_url?: string | null;
  linkedin_url?: string | null;
  portfolio_url?: string | null;
}

export interface StudentEducationInput {
  institution: string;
  degree: string;
  department_major?: string | null;
  start_year?: number | null;
  graduation_year?: number | null;
  cgpa_or_percentage?: string | null;
  relevant_coursework?: string | null;
}

export interface StudentEducation extends StudentEducationInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export type StudentSkillCategory = "technical" | "research" | "tool" | "language";

export interface StudentSkillInput {
  name: string;
  category: StudentSkillCategory;
  proficiency_level?: string | null;
  experience_context?: string | null;
}

export interface StudentSkill extends StudentSkillInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export type StudentProjectEntryType = "project" | "research_experience";

export interface StudentProjectInput {
  entry_type: StudentProjectEntryType;
  title: string;
  role?: string | null;
  organization?: string | null;
  description?: string | null;
  problem_statement?: string | null;
  methodology?: string | null;
  technologies_tools?: string | null;
  outcomes_results?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  project_url?: string | null;
  github_url?: string | null;
  associated_skills?: string | null;
}

export interface StudentProject extends StudentProjectInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface StudentExperienceInput {
  organization: string;
  role: string;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  responsibilities?: string | null;
  achievements?: string | null;
  technologies_used?: string | null;
}

export interface StudentExperience extends StudentExperienceInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export type StudentAchievementEntryType = "achievement" | "certification";

export interface StudentAchievementInput {
  entry_type: StudentAchievementEntryType;
  title: string;
  issuing_organization?: string | null;
  date_awarded?: string | null;
  description?: string | null;
  credential_url?: string | null;
}

export interface StudentAchievement extends StudentAchievementInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface StudentPublicationInput {
  title: string;
  authors?: string | null;
  journal_or_conference?: string | null;
  publication_date?: string | null;
  doi_or_url?: string | null;
  abstract?: string | null;
  verification_or_source?: string | null;
}

export interface StudentPublication extends StudentPublicationInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface StudentCompleteProfile {
  id: number;
  email: string;
  full_name: string | null;
  phone: string | null;
  institution: string | null;
  department: string | null;
  degree_program: string | null;
  graduation_year: number | null;
  current_year_or_semester: string | null;
  research_interests_summary: string | null;
  github_url: string | null;
  linkedin_url: string | null;
  portfolio_url: string | null;
  created_at: string;
  updated_at: string;
  educations: StudentEducation[];
  skills: StudentSkill[];
  projects: StudentProject[];
  experiences: StudentExperience[];
  achievements: StudentAchievement[];
  publications: StudentPublication[];
  completion: ProfileCompletion;
}

export interface StudentMutationResponse<T> {
  item: T;
  completion: ProfileCompletion;
}

export interface StudentDeleteResponse {
  deleted_id: number;
  completion: ProfileCompletion;
}

// =========================================================================
// Stage 6.2: Professor-Specific AI Tailored Resume Generation & Export
// =========================================================================

export type ResumeTemplate = "modern_professional" | "academic_research" | "technical_ai_ml";
export type ResumeLength = "1_page" | "2_pages";
export type ResumeSectionKey =
  | "summary"
  | "education"
  | "research_interests"
  | "skills"
  | "projects"
  | "research_experience"
  | "experience"
  | "publications"
  | "achievements";

export interface ResumeSelectionIdsPayload {
  project_ids: number[];
  research_experience_ids: number[];
  technical_skill_ids: number[];
  research_skill_ids: number[];
  include_research_interests: boolean;
  experience_ids: number[];
  achievement_ids: number[];
  publication_ids: number[];
}

export interface ResumePreferencesPayload {
  title: string;
  target_position?: string | null;
  template: ResumeTemplate;
  preferred_length: ResumeLength;
  included_sections: ResumeSectionKey[];
  additional_instructions?: string | null;
}

export interface ResumeHeader {
  full_name: string;
  email: string;
  phone: string | null;
  institution: string | null;
  department: string | null;
  degree_program: string | null;
  graduation_year: number | null;
  current_year_or_semester: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
}

export interface ResumeEducationItem {
  source_id: number | null;
  institution: string;
  degree: string;
  department_major: string | null;
  duration: string | null;
  cgpa_or_percentage: string | null;
  relevant_coursework: string | null;
}

export interface ResumeSkillGroup {
  category: string;
  items: string[];
}

export interface ResumeProjectItem {
  source_id: number | null;
  entry_type: "project" | "research_experience";
  title: string;
  role: string | null;
  organization: string | null;
  duration: string | null;
  technologies: string | null;
  bullets: string[];
  url: string | null;
  relevance_score: number;
}

export interface ResumeExperienceItem {
  source_id: number | null;
  organization: string;
  role: string;
  location: string | null;
  duration: string | null;
  technologies: string | null;
  bullets: string[];
  relevance_score: number;
}

export interface ResumePublicationItem {
  source_id: number | null;
  title: string;
  authors: string | null;
  venue: string | null;
  date: string | null;
  doi_or_url: string | null;
  summary: string | null;
}

export interface ResumeAchievementItem {
  source_id: number | null;
  entry_type: "achievement" | "certification";
  title: string;
  issuer: string | null;
  date: string | null;
  description: string | null;
  credential_url: string | null;
}

export interface TailoredResumeContent {
  title: string;
  target_position: string | null;
  template: ResumeTemplate;
  preferred_length: ResumeLength;
  header: ResumeHeader;
  summary: string;
  research_interests: string | null;
  section_order: ResumeSectionKey[];
  enabled_sections: ResumeSectionKey[];
  education: ResumeEducationItem[];
  skills: ResumeSkillGroup[];
  projects: ResumeProjectItem[];
  research_experience: ResumeProjectItem[];
  experience: ResumeExperienceItem[];
  publications: ResumePublicationItem[];
  achievements: ResumeAchievementItem[];
  alignment_highlights: string[];
}

export interface TailoredResumeGenerateRequest {
  selected_items: ResumeSelectionIdsPayload;
  preferences: ResumePreferencesPayload;
}

export interface TailoredResumeGenerateResponse {
  professor_id: number;
  professor_name: string;
  department_name: string | null;
  generation_mode: "gemini" | "grounded_fallback";
  provider_notice: string | null;
  professor_focus_terms: string[];
  content: TailoredResumeContent;
}

export interface TailoredResumeExportRequest {
  format: "pdf" | "docx";
  template: ResumeTemplate;
  filename?: string | null;
  content: TailoredResumeContent;
}
