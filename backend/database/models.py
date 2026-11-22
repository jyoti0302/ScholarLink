import enum
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    Table,
    UniqueConstraint,
    Index,
    Enum as SQLEnum,
    func,
    text
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import expression

Base = declarative_base()


class VerificationStatus(str, enum.Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class EvidenceType(str, enum.Enum):
    VERIFIED_PUBLICATION = "verified_publication"
    CANDIDATE_PUBLICATION = "candidate_publication"
    RESEARCH_INTEREST = "research_interest"
    RESEARCH_INTEREST_PHRASE = "research_interest_phrase"
    RESEARCH_PROJECT = "research_project"
    BIOGRAPHY = "biography"
    DEPARTMENT_CONTEXT = "department_context"


# Association table for professor-topic M2M
professor_topics = Table(
    "professor_topics",
    Base.metadata,
    Column("professor_id", Integer, ForeignKey("professors.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", Integer, ForeignKey("research_topics.id", ondelete="CASCADE"), primary_key=True),
)

# Association table for publication-topic M2M
publication_topics = Table(
    "publication_topics",
    Base.metadata,
    Column("publication_id", Integer, ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True),
    Column("topic_id", Integer, ForeignKey("research_topics.id", ondelete="CASCADE"), primary_key=True),
)


class University(Base):
    __tablename__ = "universities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, unique=True, index=True)
    country = Column(String(100), nullable=False, default="India", index=True)
    region = Column(String(100), nullable=True)
    city = Column(String(100), nullable=False)
    website = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Relationships
    departments = relationship("Department", back_populates="university", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<University(id={self.id}, name='{self.name}')>"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    university_id = Column(Integer, ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=True, index=True)
    academic_unit = Column(String(150), nullable=True)
    official_url = Column(String(500), nullable=True)
    collection_status = Column(String(50), nullable=True, default="pending")
    source_access_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint("university_id", "name", name="uq_university_department_name"),
    )

    # Relationships
    university = relationship("University", back_populates="departments")
    professors = relationship("Professor", back_populates="department", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Department(id={self.id}, code='{self.code}', name='{self.name}')>"


class Professor(Base):
    __tablename__ = "professors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    designation = Column(String(150), nullable=True)
    academic_unit = Column(String(150), nullable=True)
    appointment_category = Column(String(100), nullable=True, default="Regular Faculty")
    email = Column(String(255), nullable=True, index=True)
    educational_background = Column(Text, nullable=True)
    biography = Column(Text, nullable=True)
    research_interests = Column(Text, nullable=True)
    research_group = Column(Text, nullable=True)
    profile_url = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True)
    verification_status = Column(
        String(50),
        nullable=False,
        default=VerificationStatus.PENDING.value,
        index=True
    )
    has_publications = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    has_research_interests = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    has_biography = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    has_projects = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    openalex_author_id = Column(String(100), nullable=True, index=True)
    orcid = Column(String(100), nullable=True, index=True)
    irins_id = Column(String(100), nullable=True, index=True)
    last_updated = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("department_id", "name", name="uq_department_professor_name"),
    )

    # Relationships
    department = relationship("Department", back_populates="professors")
    professor_publications = relationship("ProfessorPublication", back_populates="professor", cascade="all, delete-orphan")
    professor_projects = relationship("ProfessorProject", back_populates="professor", cascade="all, delete-orphan")
    topics = relationship("ResearchTopic", secondary=professor_topics, back_populates="professors")

    @property
    def verified_publication_count(self) -> int:
        return sum(1 for pp in self.professor_publications if pp.verification_status == "verified")

    @property
    def pending_publication_count(self) -> int:
        return sum(1 for pp in self.professor_publications if pp.verification_status == "pending")

    @property
    def needs_review_publication_count(self) -> int:
        return sum(1 for pp in self.professor_publications if pp.verification_status == "needs_review")

    @property
    def candidate_publication_count(self) -> int:
        return sum(
            1 for pp in self.professor_publications
            if pp.verification_status in ("pending", "needs_review")
        )

    def __repr__(self):
        return f"<Professor(id={self.id}, name='{self.name}', status='{self.verification_status}')>"


class Publication(Base):
    __tablename__ = "publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    openalex_id = Column(String(150), nullable=True, unique=True, index=True)
    doi = Column(String(255), nullable=True, unique=True, index=True)
    title = Column(Text, nullable=False, index=True)
    abstract = Column(Text, nullable=True)
    publication_year = Column(Integer, nullable=True, index=True)
    journal_or_conference = Column(String(500), nullable=True)
    authors_list = Column(Text, nullable=True)
    paper_url = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_name = Column(String(100), nullable=False, default="openalex")
    verification_status = Column(
        String(50),
        nullable=False,
        default=VerificationStatus.PENDING.value,
        index=True
    )
    citation_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Relationships
    professor_publications = relationship("ProfessorPublication", back_populates="publication", cascade="all, delete-orphan")
    topics = relationship("ResearchTopic", secondary=publication_topics, back_populates="publications")

    def __repr__(self):
        return f"<Publication(id={self.id}, year={self.publication_year}, title='{self.title[:30]}...')>"


class ProfessorPublication(Base):
    __tablename__ = "professor_publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    professor_id = Column(Integer, ForeignKey("professors.id", ondelete="CASCADE"), nullable=False, index=True)
    publication_id = Column(Integer, ForeignKey("publications.id", ondelete="CASCADE"), nullable=False, index=True)
    author_position = Column(String(50), nullable=True)
    openalex_author_id = Column(String(100), nullable=True)
    affiliation_evidence = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=False, default=1.0)
    verification_status = Column(
        String(50),
        nullable=False,
        default=VerificationStatus.PENDING.value,
        index=True
    )

    __table_args__ = (
        UniqueConstraint("professor_id", "publication_id", name="uq_professor_publication"),
    )

    # Relationships
    professor = relationship("Professor", back_populates="professor_publications")
    publication = relationship("Publication", back_populates="professor_publications")

    def __repr__(self):
        return f"<ProfessorPublication(prof_id={self.professor_id}, pub_id={self.publication_id}, score={self.confidence_score})>"


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(Text, nullable=False, index=True)
    original_title = Column(Text, nullable=True)
    project_category = Column(
        String(50),
        nullable=False,
        default="sponsored_research",
        server_default="sponsored_research",
        index=True
    )
    description = Column(Text, nullable=True)
    sponsor = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True, default="completed")
    source_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Relationships
    professor_projects = relationship("ProfessorProject", back_populates="project", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResearchProject(id={self.id}, title='{self.title[:30]}...')>"


class ProfessorProject(Base):
    __tablename__ = "professor_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    professor_id = Column(Integer, ForeignKey("professors.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(100), nullable=True, default="Principal Investigator")

    __table_args__ = (
        UniqueConstraint("professor_id", "project_id", "role", name="uq_professor_project_role"),
    )

    # Relationships
    professor = relationship("Professor", back_populates="professor_projects")
    project = relationship("ResearchProject", back_populates="professor_projects")

    def __repr__(self):
        return f"<ProfessorProject(prof_id={self.professor_id}, proj_id={self.project_id}, role='{self.role}')>"


class ResearchTopic(Base):
    __tablename__ = "research_topics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic_name = Column(String(200), nullable=False, unique=True, index=True)
    canonical_topic_name = Column(String(255), nullable=True, index=True)
    domain_name = Column(String(150), nullable=True, index=True)
    area_name = Column(String(150), nullable=True, index=True)
    parent_topic_id = Column(Integer, ForeignKey("research_topics.id", ondelete="SET NULL"), nullable=True, index=True)
    is_generic_root = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    is_noisy_artifact = Column(Boolean, nullable=False, default=False, server_default=expression.false())
    description = Column(Text, nullable=True)

    # Relationships
    professors = relationship("Professor", secondary=professor_topics, back_populates="topics")
    publications = relationship("Publication", secondary=publication_topics, back_populates="topics")

    def __repr__(self):
        return f"<ResearchTopic(id={self.id}, name='{self.topic_name}')>"


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    source_name = Column(String(100), nullable=False)
    source_url = Column(Text, nullable=False)
    http_status = Column(Integer, nullable=True, default=200)
    error_message = Column(Text, nullable=True)
    retrieved_at = Column(DateTime, nullable=False, default=func.now())
    verification_status = Column(
        String(50),
        nullable=False,
        default=VerificationStatus.PENDING.value
    )

    def __repr__(self):
        return f"<DataSource(type='{self.entity_type}', id={self.entity_id}, source='{self.source_name}')>"


class VerificationRecord(Base):
    __tablename__ = "verification_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    previous_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    verified_by = Column(String(100), nullable=False, default="csv_review")
    evidence_or_notes = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return f"<VerificationRecord(type='{self.entity_type}', id={self.entity_id}, status='{self.new_status}')>"


class SearchDocument(Base):
    __tablename__ = "search_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(64), nullable=False, unique=True, index=True)
    professor_id = Column(Integer, ForeignKey("professors.id", ondelete="CASCADE"), nullable=True, index=True)
    university_id = Column(Integer, ForeignKey("universities.id", ondelete="CASCADE"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type = Column(String(50), nullable=False, index=True)
    source_table = Column(String(50), nullable=False)
    source_id = Column(Integer, nullable=False, index=True)
    link_id = Column(Integer, nullable=True, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=1)
    title = Column(Text, nullable=False)
    text_content = Column(Text, nullable=False)
    canonical_topics_json = Column(Text, nullable=False, default="[]")
    topic_domains_json = Column(Text, nullable=False, default="[]")
    topic_areas_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")
    source_url = Column(String(500), nullable=True)
    verification_status = Column(String(50), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False, default=1.0)
    content_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return (
            f"<SearchDocument(doc_id='{self.document_id}', type='{self.evidence_type}', "
            f"prof_id={self.professor_id}, status='{self.verification_status}')>"
        )


class IndexSyncState(Base):
    __tablename__ = "index_sync_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String(64), nullable=False, unique=True, index=True)
    collection_name = Column(String(100), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    payload_hash = Column(String(64), nullable=False)
    embedding_model = Column(String(100), nullable=False)
    qdrant_status = Column(String(50), nullable=False, default="synced", index=True)
    indexed_at = Column(DateTime, nullable=False, default=func.now())

    def __repr__(self):
        return f"<IndexSyncState(doc_id='{self.document_id}', status='{self.qdrant_status}')>"


class EmbeddingCache(Base):
    __tablename__ = "embedding_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_hash = Column(String(64), nullable=False, index=True)
    embedding_model = Column(String(100), nullable=False, index=True)
    dense_vector_json = Column(Text, nullable=False)
    sparse_indices_json = Column(Text, nullable=True)
    sparse_values_json = Column(Text, nullable=True)
    vector_dim = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())

    __table_args__ = (
        UniqueConstraint("content_hash", "embedding_model", name="uq_embedding_cache_hash_model"),
    )

    def __repr__(self):
        return f"<EmbeddingCache(hash='{self.content_hash[:12]}...', model='{self.embedding_model}')>"


# =========================================================================
# Stage 5.2: Dedicated Student Academic Profile Tables
# Strictly isolated from professor/faculty tables and Qdrant search corpus.
# =========================================================================

class StudentSkillCategory(str, enum.Enum):
    TECHNICAL = "technical"
    RESEARCH = "research"
    TOOL = "tool"
    LANGUAGE = "language"


class StudentProjectEntryType(str, enum.Enum):
    PROJECT = "project"
    RESEARCH_EXPERIENCE = "research_experience"


class StudentAchievementEntryType(str, enum.Enum):
    ACHIEVEMENT = "achievement"
    CERTIFICATION = "certification"


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    institution = Column(String(255), nullable=True)
    department = Column(String(255), nullable=True)
    degree_program = Column(String(150), nullable=True)
    graduation_year = Column(Integer, nullable=True)
    current_year_or_semester = Column(String(100), nullable=True)
    research_interests_summary = Column(Text, nullable=True)
    github_url = Column(String(500), nullable=True)
    linkedin_url = Column(String(500), nullable=True)
    portfolio_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    educations = relationship("StudentEducation", back_populates="student", cascade="all, delete-orphan")
    skills = relationship("StudentSkill", back_populates="student", cascade="all, delete-orphan")
    projects = relationship("StudentProject", back_populates="student", cascade="all, delete-orphan")
    experiences = relationship("StudentExperience", back_populates="student", cascade="all, delete-orphan")
    achievements = relationship("StudentAchievement", back_populates="student", cascade="all, delete-orphan")
    publications = relationship("StudentPublication", back_populates="student", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Student(id={self.id}, email='{self.email}')>"


class StudentEducation(Base):
    __tablename__ = "student_educations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    institution = Column(String(255), nullable=False)
    degree = Column(String(150), nullable=False)
    department_major = Column(String(255), nullable=True)
    start_year = Column(Integer, nullable=True)
    graduation_year = Column(Integer, nullable=True)
    cgpa_or_percentage = Column(String(50), nullable=True)
    relevant_coursework = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="educations")


class StudentSkill(Base):
    __tablename__ = "student_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    category = Column(String(50), nullable=False, default=StudentSkillCategory.TECHNICAL.value)
    proficiency_level = Column(String(50), nullable=True)
    experience_context = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "category IN ('technical', 'research', 'tool', 'language')",
            name="ck_student_skills_category",
        ),
    )

    student = relationship("Student", back_populates="skills")


class StudentProject(Base):
    __tablename__ = "student_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String(50), nullable=False, default=StudentProjectEntryType.PROJECT.value)
    title = Column(String(300), nullable=False)
    role = Column(String(150), nullable=True)
    organization = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    problem_statement = Column(Text, nullable=True)
    methodology = Column(Text, nullable=True)
    technologies_tools = Column(Text, nullable=True)
    outcomes_results = Column(Text, nullable=True)
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    project_url = Column(String(500), nullable=True)
    github_url = Column(String(500), nullable=True)
    associated_skills = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('project', 'research_experience')",
            name="ck_student_projects_entry_type",
        ),
    )

    student = relationship("Student", back_populates="projects")


class StudentExperience(Base):
    __tablename__ = "student_experiences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    organization = Column(String(255), nullable=False)
    role = Column(String(150), nullable=False)
    location = Column(String(150), nullable=True)
    start_date = Column(String(50), nullable=True)
    end_date = Column(String(50), nullable=True)
    responsibilities = Column(Text, nullable=True)
    achievements = Column(Text, nullable=True)
    technologies_used = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="experiences")


class StudentAchievement(Base):
    __tablename__ = "student_achievements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    entry_type = Column(String(50), nullable=False, default=StudentAchievementEntryType.ACHIEVEMENT.value)
    title = Column(String(300), nullable=False)
    issuing_organization = Column(String(255), nullable=True)
    date_awarded = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    credential_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "entry_type IN ('achievement', 'certification')",
            name="ck_student_achievements_entry_type",
        ),
    )

    student = relationship("Student", back_populates="achievements")


class StudentPublication(Base):
    __tablename__ = "student_publications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(Text, nullable=False)
    authors = Column(Text, nullable=True)
    journal_or_conference = Column(String(500), nullable=True)
    publication_date = Column(String(50), nullable=True)
    doi_or_url = Column(String(500), nullable=True)
    abstract = Column(Text, nullable=True)
    verification_or_source = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    student = relationship("Student", back_populates="publications")
