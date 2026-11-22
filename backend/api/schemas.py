from datetime import datetime
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class ResearchTopicSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_name: str
    canonical_topic_name: Optional[str] = None
    domain_name: Optional[str] = None
    area_name: Optional[str] = None
    parent_topic_id: Optional[int] = None
    is_generic_root: bool = False
    is_noisy_artifact: bool = False
    description: Optional[str] = None


class UniversitySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str
    region: Optional[str] = None
    city: str
    website: Optional[str] = None
    created_at: datetime


class DepartmentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    university_id: int
    name: str
    code: Optional[str] = None
    academic_unit: Optional[str] = None
    official_url: Optional[str] = None
    collection_status: Optional[str] = None
    created_at: datetime


class ProfessorBriefSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    name: str
    designation: Optional[str] = None
    academic_unit: Optional[str] = None
    appointment_category: Optional[str] = None
    educational_background: Optional[str] = None
    email: Optional[str] = None
    verification_status: str
    has_publications: bool = False
    verified_publication_count: int = 0
    pending_publication_count: int = 0
    needs_review_publication_count: int = 0
    candidate_publication_count: int = 0
    has_research_interests: bool = False
    has_biography: bool = False
    has_projects: bool = False
    profile_url: Optional[str] = None


class ProfessorDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    name: str
    designation: Optional[str] = None
    academic_unit: Optional[str] = None
    appointment_category: Optional[str] = None
    educational_background: Optional[str] = None
    email: Optional[str] = None
    biography: Optional[str] = None
    research_interests: Optional[str] = None
    research_group: Optional[str] = None
    profile_url: Optional[str] = None
    source_url: Optional[str] = None
    verification_status: str
    has_publications: bool = False
    verified_publication_count: int = 0
    pending_publication_count: int = 0
    needs_review_publication_count: int = 0
    candidate_publication_count: int = 0
    has_research_interests: bool = False
    has_biography: bool = False
    has_projects: bool = False
    openalex_author_id: Optional[str] = None
    orcid: Optional[str] = None
    irins_id: Optional[str] = None
    last_updated: datetime
    topics: List[ResearchTopicSchema] = []


class PublicationBriefSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    openalex_id: Optional[str] = None
    doi: Optional[str] = None
    title: str
    publication_year: Optional[int] = None
    journal_or_conference: Optional[str] = None
    authors_list: Optional[str] = None
    citation_count: int
    verification_status: str


class PublicationDetailSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    openalex_id: Optional[str] = None
    doi: Optional[str] = None
    title: str
    abstract: Optional[str] = None
    publication_year: Optional[int] = None
    journal_or_conference: Optional[str] = None
    authors_list: Optional[str] = None
    paper_url: Optional[str] = None
    source_url: Optional[str] = None
    source_name: str
    verification_status: str
    citation_count: int
    created_at: datetime
    topics: List[ResearchTopicSchema] = []


class ProfessorPublicationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    professor_id: int
    publication_id: int
    author_position: Optional[str] = None
    openalex_author_id: Optional[str] = None
    affiliation_evidence: Optional[str] = None
    confidence_score: float
    verification_status: str
    publication: PublicationBriefSchema


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list


class SearchRequestSchema(BaseModel):
    query: str = Field(..., min_length=1, description="Non-empty research search query")
    limit: Optional[int] = Field(20, ge=1, description="Page size (omit or pass null for all qualifying professors)")
    offset: int = Field(0, ge=0, description="Pagination offset into qualifying professors")
    use_expansion: bool = Field(True, description="Enable multi-query expansion")
    university_id: Optional[int] = Field(None, ge=1, description="Optional university ID filter")
    department_ids: Optional[List[int]] = Field(None, description="Optional department ID filter")
    include_candidate_publications: bool = Field(True, description="Include unverified candidate publications")
    request_id: Optional[str] = Field(None, max_length=128, description="Optional client request ID for cancellation")

    @field_validator("query")
    @classmethod
    def query_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query must not be empty or whitespace-only")
        return cleaned


class SupportingEvidenceSchema(BaseModel):
    evidence_id: Optional[str] = None
    evidence_type: str
    relevance_group: Optional[str] = None
    topic_relevance_note: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    source_url: Optional[str] = None
    verification_status: Optional[str] = None
    matched_by_query: Optional[str] = None
    score: float
    authorship_note: Optional[str] = None
    role: Optional[str] = None
    sponsor: Optional[str] = None
    project_category: Optional[str] = None


class SearchProfessorResultSchema(BaseModel):
    professor_id: int
    professor_name: str
    department: str
    department_code: str
    department_name: str
    designation: Optional[str] = None
    email: Optional[str] = None
    profile_url: Optional[str] = None
    score: float
    match_category: str
    research_interests: Optional[str] = None
    biography: Optional[str] = None
    evidence_counts: Dict[str, int] = {}
    matched_topics: List[str] = []
    matched_queries: List[str] = []
    supporting_evidence: List[SupportingEvidenceSchema] = []
    explanation: str


class SearchResponseSchema(BaseModel):
    request_id: str
    query: str
    expanded_queries: List[str] = []
    status: str
    message: Optional[str] = None
    search_latency_ms: float
    total_results: int
    total_qualifying_results: int = 0
    offset: int = 0
    limit: Optional[int] = None
    has_more: bool = False
    results: List[SearchProfessorResultSchema]


class CancelSearchResponseSchema(BaseModel):
    request_id: str
    cancelled: bool
    status: str


class ProfessorProfileProjectSchema(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    category: str
    sponsor: Optional[str] = None
    status: Optional[str] = None
    role: Optional[str] = None
    source_url: Optional[str] = None
    is_administrative_or_grant: bool = False


class ProfessorProfilePublicationSchema(BaseModel):
    publication_id: int
    title: str
    abstract: Optional[str] = None
    doi: Optional[str] = None
    publication_year: Optional[int] = None
    journal_or_conference: Optional[str] = None
    paper_url: Optional[str] = None
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    citation_count: int = 0
    author_position: Optional[str] = None
    verification_status: str
    confidence_score: Optional[float] = None
    affiliation_evidence: Optional[str] = None
    is_unverified: bool = False
    authorship_note: Optional[str] = None


class ProfessorContactLinkSchema(BaseModel):
    label: str
    url: str
    source_url: Optional[str] = None


class ProfessorContactInfoSchema(BaseModel):
    email: Optional[str] = None
    office_phone: Optional[str] = None
    office_room: Optional[str] = None
    department_address: Optional[str] = None
    department_office_contact: Optional[str] = None
    department_url: Optional[str] = None
    research_group_website: Optional[str] = None
    personal_webpage: Optional[str] = None
    bio_sketch_url: Optional[str] = None
    profile_url: Optional[str] = None
    academic_links: List[ProfessorContactLinkSchema] = []
    source_url: Optional[str] = None


class ProfessorProfileSchema(BaseModel):
    professor_id: int
    name: str
    designation: Optional[str] = None
    email: Optional[str] = None
    academic_unit: Optional[str] = None
    department_id: int
    department_name: Optional[str] = None
    department_code: Optional[str] = None
    university_id: Optional[int] = None
    university_name: Optional[str] = None
    university_website: Optional[str] = None
    biography: Optional[str] = None
    educational_background: Optional[str] = None
    research_interests: Optional[str] = None
    research_group: Optional[str] = None
    profile_url: Optional[str] = None
    source_url: Optional[str] = None
    verification_status: str
    orcid: Optional[str] = None
    irins_id: Optional[str] = None
    openalex_author_id: Optional[str] = None
    last_updated: Optional[datetime] = None
    contact_info: Optional[ProfessorContactInfoSchema] = None
    research_topics: List[ResearchTopicSchema] = []
    research_projects: List[ProfessorProfileProjectSchema] = []
    verified_publications: List[ProfessorProfilePublicationSchema] = []
    candidate_publications: List[ProfessorProfilePublicationSchema] = []


class StudentRegisterRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class StudentLoginRequestSchema(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class StudentAuthSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None
    degree_program: Optional[str] = None
    graduation_year: Optional[int] = None
    current_year_or_semester: Optional[str] = None
    created_at: datetime

    @computed_field
    @property
    def profile_completed(self) -> bool:
        return bool(self.full_name and self.full_name.strip())


class AuthTokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    student: StudentAuthSummarySchema


# =========================================================================
# Stage 5.3: Student Academic Profile CRUD & Completion Schemas
# =========================================================================

def _clean_optional_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_required_str(value: str, label: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise ValueError(f"{label} must not be blank")
    return cleaned


class ProfileCompletionItemSchema(BaseModel):
    key: str
    label: str
    weight: int
    completed: bool
    section: str


class ProfileCompletionSchema(BaseModel):
    percentage: int
    completed_count: int
    total_count: int
    items: List[ProfileCompletionItemSchema]


class StudentPersonalInfoUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    institution: Optional[str] = Field(None, max_length=255)
    department: Optional[str] = Field(None, max_length=255)
    degree_program: Optional[str] = Field(None, max_length=150)
    graduation_year: Optional[int] = Field(None, ge=1950, le=2100)
    current_year_or_semester: Optional[str] = Field(None, max_length=100)
    research_interests_summary: Optional[str] = Field(None, max_length=4000)
    github_url: Optional[str] = Field(None, max_length=500)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    portfolio_url: Optional[str] = Field(None, max_length=500)

    @field_validator(
        "full_name",
        "phone",
        "institution",
        "department",
        "degree_program",
        "current_year_or_semester",
        "research_interests_summary",
        "github_url",
        "linkedin_url",
        "portfolio_url",
    )
    @classmethod
    def normalize_optional_strings(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentEducationInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = Field(..., min_length=1, max_length=255)
    degree: str = Field(..., min_length=1, max_length=150)
    department_major: Optional[str] = Field(None, max_length=255)
    start_year: Optional[int] = Field(None, ge=1950, le=2100)
    graduation_year: Optional[int] = Field(None, ge=1950, le=2100)
    cgpa_or_percentage: Optional[str] = Field(None, max_length=50)
    relevant_coursework: Optional[str] = Field(None, max_length=4000)

    @field_validator("institution")
    @classmethod
    def validate_institution(cls, value: str) -> str:
        return _clean_required_str(value, "Institution")

    @field_validator("degree")
    @classmethod
    def validate_degree(cls, value: str) -> str:
        return _clean_required_str(value, "Degree")

    @field_validator("department_major", "cgpa_or_percentage", "relevant_coursework")
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentEducationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution: str
    degree: str
    department_major: Optional[str] = None
    start_year: Optional[int] = None
    graduation_year: Optional[int] = None
    cgpa_or_percentage: Optional[str] = None
    relevant_coursework: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentSkillInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=150)
    category: Literal["technical", "research", "tool", "language"] = "technical"
    proficiency_level: Optional[str] = Field(None, max_length=50)
    experience_context: Optional[str] = Field(None, max_length=2000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _clean_required_str(value, "Skill name")

    @field_validator("proficiency_level", "experience_context")
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentSkillSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    proficiency_level: Optional[str] = None
    experience_context: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentProjectInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_type: Literal["project", "research_experience"] = "project"
    title: str = Field(..., min_length=1, max_length=300)
    role: Optional[str] = Field(None, max_length=150)
    organization: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=4000)
    problem_statement: Optional[str] = Field(None, max_length=4000)
    methodology: Optional[str] = Field(None, max_length=4000)
    technologies_tools: Optional[str] = Field(None, max_length=2000)
    outcomes_results: Optional[str] = Field(None, max_length=4000)
    start_date: Optional[str] = Field(None, max_length=50)
    end_date: Optional[str] = Field(None, max_length=50)
    project_url: Optional[str] = Field(None, max_length=500)
    github_url: Optional[str] = Field(None, max_length=500)
    associated_skills: Optional[str] = Field(None, max_length=2000)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _clean_required_str(value, "Title")

    @field_validator(
        "role",
        "organization",
        "description",
        "problem_statement",
        "methodology",
        "technologies_tools",
        "outcomes_results",
        "start_date",
        "end_date",
        "project_url",
        "github_url",
        "associated_skills",
    )
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentProjectSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_type: str
    title: str
    role: Optional[str] = None
    organization: Optional[str] = None
    description: Optional[str] = None
    problem_statement: Optional[str] = None
    methodology: Optional[str] = None
    technologies_tools: Optional[str] = None
    outcomes_results: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project_url: Optional[str] = None
    github_url: Optional[str] = None
    associated_skills: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentExperienceInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=150)
    location: Optional[str] = Field(None, max_length=150)
    start_date: Optional[str] = Field(None, max_length=50)
    end_date: Optional[str] = Field(None, max_length=50)
    responsibilities: Optional[str] = Field(None, max_length=4000)
    achievements: Optional[str] = Field(None, max_length=4000)
    technologies_used: Optional[str] = Field(None, max_length=2000)

    @field_validator("organization")
    @classmethod
    def validate_organization(cls, value: str) -> str:
        return _clean_required_str(value, "Organization")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        return _clean_required_str(value, "Role")

    @field_validator("location", "start_date", "end_date", "responsibilities", "achievements", "technologies_used")
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentExperienceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization: str
    role: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    responsibilities: Optional[str] = None
    achievements: Optional[str] = None
    technologies_used: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentAchievementInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_type: Literal["achievement", "certification"] = "achievement"
    title: str = Field(..., min_length=1, max_length=300)
    issuing_organization: Optional[str] = Field(None, max_length=255)
    date_awarded: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=4000)
    credential_url: Optional[str] = Field(None, max_length=500)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _clean_required_str(value, "Title")

    @field_validator("issuing_organization", "date_awarded", "description", "credential_url")
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentAchievementSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entry_type: str
    title: str
    issuing_organization: Optional[str] = None
    date_awarded: Optional[str] = None
    description: Optional[str] = None
    credential_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentPublicationInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=1000)
    authors: Optional[str] = Field(None, max_length=2000)
    journal_or_conference: Optional[str] = Field(None, max_length=500)
    publication_date: Optional[str] = Field(None, max_length=50)
    doi_or_url: Optional[str] = Field(None, max_length=500)
    abstract: Optional[str] = Field(None, max_length=5000)
    verification_or_source: Optional[str] = Field(None, max_length=255)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _clean_required_str(value, "Title")

    @field_validator(
        "authors",
        "journal_or_conference",
        "publication_date",
        "doi_or_url",
        "abstract",
        "verification_or_source",
    )
    @classmethod
    def normalize_opt(cls, value: Optional[str]) -> Optional[str]:
        return _clean_optional_str(value)


class StudentPublicationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    authors: Optional[str] = None
    journal_or_conference: Optional[str] = None
    publication_date: Optional[str] = None
    doi_or_url: Optional[str] = None
    abstract: Optional[str] = None
    verification_or_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StudentCompleteProfileSchema(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    phone: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None
    degree_program: Optional[str] = None
    graduation_year: Optional[int] = None
    current_year_or_semester: Optional[str] = None
    research_interests_summary: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    educations: List[StudentEducationSchema] = []
    skills: List[StudentSkillSchema] = []
    projects: List[StudentProjectSchema] = []
    experiences: List[StudentExperienceSchema] = []
    achievements: List[StudentAchievementSchema] = []
    publications: List[StudentPublicationSchema] = []
    completion: ProfileCompletionSchema


class StudentEducationMutationResponseSchema(BaseModel):
    item: StudentEducationSchema
    completion: ProfileCompletionSchema


class StudentSkillMutationResponseSchema(BaseModel):
    item: StudentSkillSchema
    completion: ProfileCompletionSchema


class StudentProjectMutationResponseSchema(BaseModel):
    item: StudentProjectSchema
    completion: ProfileCompletionSchema


class StudentExperienceMutationResponseSchema(BaseModel):
    item: StudentExperienceSchema
    completion: ProfileCompletionSchema


class StudentAchievementMutationResponseSchema(BaseModel):
    item: StudentAchievementSchema
    completion: ProfileCompletionSchema


class StudentPublicationMutationResponseSchema(BaseModel):
    item: StudentPublicationSchema
    completion: ProfileCompletionSchema


class StudentDeleteResponseSchema(BaseModel):
    deleted_id: int
    completion: ProfileCompletionSchema


# =========================================================================
# Stage 6.2: Professor-Specific AI Tailored Resume Generation & Export
# =========================================================================

ResumeTemplateLiteral = Literal["modern_professional", "academic_research", "technical_ai_ml"]
ResumeLengthLiteral = Literal["1_page", "2_pages"]
ResumeSectionKeyLiteral = Literal[
    "summary",
    "education",
    "research_interests",
    "skills",
    "projects",
    "research_experience",
    "experience",
    "publications",
    "achievements",
]


class ResumeSelectionIdsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_ids: List[int] = Field(default_factory=list)
    research_experience_ids: List[int] = Field(default_factory=list)
    technical_skill_ids: List[int] = Field(default_factory=list)
    research_skill_ids: List[int] = Field(default_factory=list)
    include_research_interests: bool = False
    experience_ids: List[int] = Field(default_factory=list)
    achievement_ids: List[int] = Field(default_factory=list)
    publication_ids: List[int] = Field(default_factory=list)


class ResumePreferencesSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field("Tailored Research Resume", min_length=1, max_length=200)
    target_position: Optional[str] = Field(None, max_length=200)
    template: ResumeTemplateLiteral = "academic_research"
    preferred_length: ResumeLengthLiteral = "1_page"
    included_sections: List[ResumeSectionKeyLiteral] = Field(
        default_factory=lambda: [
            "summary",
            "education",
            "research_interests",
            "skills",
            "projects",
            "research_experience",
            "experience",
            "publications",
            "achievements",
        ]
    )
    additional_instructions: Optional[str] = Field(None, max_length=1000)


class ResumeHeaderSchema(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None
    degree_program: Optional[str] = None
    graduation_year: Optional[int] = None
    current_year_or_semester: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None


class ResumeEducationItemSchema(BaseModel):
    source_id: Optional[int] = None
    institution: str
    degree: str
    department_major: Optional[str] = None
    duration: Optional[str] = None
    cgpa_or_percentage: Optional[str] = None
    relevant_coursework: Optional[str] = None


class ResumeSkillGroupSchema(BaseModel):
    category: str
    items: List[str] = Field(default_factory=list)


class ResumeProjectItemSchema(BaseModel):
    source_id: Optional[int] = None
    entry_type: Literal["project", "research_experience"] = "project"
    title: str
    role: Optional[str] = None
    organization: Optional[str] = None
    duration: Optional[str] = None
    technologies: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    url: Optional[str] = None
    relevance_score: float = 0.0


class ResumeExperienceItemSchema(BaseModel):
    source_id: Optional[int] = None
    organization: str
    role: str
    location: Optional[str] = None
    duration: Optional[str] = None
    technologies: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)
    relevance_score: float = 0.0


class ResumePublicationItemSchema(BaseModel):
    source_id: Optional[int] = None
    title: str
    authors: Optional[str] = None
    venue: Optional[str] = None
    date: Optional[str] = None
    doi_or_url: Optional[str] = None
    summary: Optional[str] = None


class ResumeAchievementItemSchema(BaseModel):
    source_id: Optional[int] = None
    entry_type: Literal["achievement", "certification"] = "achievement"
    title: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    credential_url: Optional[str] = None


class TailoredResumeContentSchema(BaseModel):
    title: str
    target_position: Optional[str] = None
    template: ResumeTemplateLiteral = "academic_research"
    preferred_length: ResumeLengthLiteral = "1_page"
    header: ResumeHeaderSchema
    summary: str
    research_interests: Optional[str] = None
    section_order: List[ResumeSectionKeyLiteral] = Field(
        default_factory=lambda: [
            "summary",
            "education",
            "research_interests",
            "skills",
            "projects",
            "research_experience",
            "experience",
            "publications",
            "achievements",
        ]
    )
    enabled_sections: List[ResumeSectionKeyLiteral] = Field(
        default_factory=lambda: [
            "summary",
            "education",
            "research_interests",
            "skills",
            "projects",
            "research_experience",
            "experience",
            "publications",
            "achievements",
        ]
    )
    education: List[ResumeEducationItemSchema] = Field(default_factory=list)
    skills: List[ResumeSkillGroupSchema] = Field(default_factory=list)
    projects: List[ResumeProjectItemSchema] = Field(default_factory=list)
    research_experience: List[ResumeProjectItemSchema] = Field(default_factory=list)
    experience: List[ResumeExperienceItemSchema] = Field(default_factory=list)
    publications: List[ResumePublicationItemSchema] = Field(default_factory=list)
    achievements: List[ResumeAchievementItemSchema] = Field(default_factory=list)
    alignment_highlights: List[str] = Field(default_factory=list)


class TailoredResumeGenerateRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_items: ResumeSelectionIdsSchema = Field(default_factory=ResumeSelectionIdsSchema)
    preferences: ResumePreferencesSchema = Field(default_factory=ResumePreferencesSchema)


class TailoredResumeGenerateResponseSchema(BaseModel):
    professor_id: int
    professor_name: str
    department_name: Optional[str] = None
    generation_mode: Literal["gemini", "grounded_fallback"]
    provider_notice: Optional[str] = None
    professor_focus_terms: List[str] = Field(default_factory=list)
    content: TailoredResumeContentSchema


class TailoredResumeExportRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["pdf", "docx"]
    template: ResumeTemplateLiteral = "academic_research"
    filename: Optional[str] = Field(None, max_length=120)
    content: TailoredResumeContentSchema
