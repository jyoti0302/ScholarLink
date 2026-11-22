from contextlib import asynccontextmanager
import inspect
import logging
import os
import time
from typing import List, Optional
import uuid
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.database.connection import engine, get_db, init_db
from backend.database.models import (
    University,
    Department,
    Professor,
    ProfessorProject,
    Publication,
    ProfessorPublication
)
from backend.api.schemas import (
    UniversitySchema,
    DepartmentSchema,
    ProfessorBriefSchema,
    ProfessorDetailSchema,
    PublicationBriefSchema,
    PublicationDetailSchema,
    ProfessorPublicationSchema,
    SearchRequestSchema,
    SearchResponseSchema,
    SearchProfessorResultSchema,
    SupportingEvidenceSchema,
    CancelSearchResponseSchema,
    ResearchTopicSchema,
    ProfessorProfileProjectSchema,
    ProfessorProfilePublicationSchema,
    ProfessorProfileSchema,
)
from backend.api.auth import router as auth_router
from backend.api.professor_contact import build_professor_contact_info
from backend.api.resume_generation import router as resume_generation_router
from backend.api.student_profile import router as student_profile_router
from backend.search.cancellation import CancellationRegistry, SearchCancelledError
from backend.search.document_builder import (
    CANDIDATE_DISCLOSURE_LABEL,
    normalize_known_research_typos,
    resolve_project_source_url,
)
from backend.search.embedding import BGEM3FlagEmbeddingProvider
from backend.search.qdrant_index import QdrantIndexManager
from backend.search.query_understanding import QueryExpansionService
from backend.search.ranking import SearchService
from backend.search.relevance_validation import RelevanceValidationService
from backend.search.retrieval import HybridRetrievalService, QueryEmbeddingService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    qdrant_path = os.getenv("QDRANT_PATH", "data/qdrant_full")
    app.state.qdrant_client = None
    app.state.search_service = None
    app.state.search_init_error = None
    app.state.cancellation_registry = CancellationRegistry()
    try:
        if qdrant_url:
            qdrant_client = QdrantClient(url=qdrant_url, prefer_grpc=True)
            qdrant_client.get_collections()
        else:
            qdrant_client = QdrantClient(path=qdrant_path)
        index_manager = QdrantIndexManager(client=qdrant_client)
        embedding_provider = BGEM3FlagEmbeddingProvider()
        query_embedding_service = QueryEmbeddingService(provider=embedding_provider)
        expansion_service = QueryExpansionService()
        retrieval_service = HybridRetrievalService(
            index_manager=index_manager,
            query_embedding_service=query_embedding_service,
        )
        relevance_validator = RelevanceValidationService()
        app.state.qdrant_client = qdrant_client
        app.state.search_service = SearchService(
            expansion_service=expansion_service,
            retrieval_service=retrieval_service,
            relevance_validator=relevance_validator,
        )
    except Exception as exc:
        logger.warning("Failed to initialize SearchService during lifespan: %s", exc)
        app.state.search_init_error = str(exc)

    try:
        yield
    finally:
        if getattr(app.state, "qdrant_client", None) is not None:
            try:
                app.state.qdrant_client.close()
            except Exception:
                pass
        try:
            engine.dispose()
        except Exception:
            pass


def get_search_service(request: Request) -> SearchService:
    svc = getattr(request.app.state, "search_service", None)
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="Search service is currently unavailable.",
        )
    return svc


async def get_cancellation_registry(request: Request) -> CancellationRegistry:
    reg = getattr(request.app.state, "cancellation_registry", None)
    if reg is None:
        reg = CancellationRegistry()
        request.app.state.cancellation_registry = reg
    return reg


app = FastAPI(
    title="AI-Powered Academic Professor Discovery Platform",
    description="Data foundation API for university professors, departments, publications, and verification review.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(student_profile_router)
app.include_router(resume_generation_router)


@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "online",
        "platform": "AI-Powered Professor Discovery Platform",
        "phase": 2,
        "institution": "Indian Institute of Technology Kharagpur"
    }


@app.post("/search/cancel/{request_id}", response_model=CancelSearchResponseSchema, tags=["Search"])
async def cancel_search_request(
    request_id: str,
    registry: CancellationRegistry = Depends(get_cancellation_registry),
):
    cancelled = registry.cancel(request_id)
    return CancelSearchResponseSchema(
        request_id=request_id,
        cancelled=cancelled,
        status="cancelled" if cancelled else "not_found",
    )


@app.post("/search", response_model=SearchResponseSchema, tags=["Search"])
def search_professors(
    payload: SearchRequestSchema,
    db: Session = Depends(get_db),
    search_service: SearchService = Depends(get_search_service),
    registry: CancellationRegistry = Depends(get_cancellation_registry),
):
    request_id = (payload.request_id or "").strip() or str(uuid.uuid4())
    t0 = time.perf_counter()
    cancel_token = registry.register(request_id)
    try:
        search_kwargs = {
            "db": db,
            "query": payload.query,
            "top_k": payload.limit,
            "use_expansion": payload.use_expansion,
            "department_ids": payload.department_ids,
            "include_candidate_publications": payload.include_candidate_publications,
        }
        try:
            sig = inspect.signature(search_service.search)
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            if "cancel_token" in sig.parameters or has_var_kw:
                search_kwargs["cancel_token"] = cancel_token
            if "offset" in sig.parameters or has_var_kw:
                search_kwargs["offset"] = payload.offset
            if "university_id" in sig.parameters or has_var_kw:
                search_kwargs["university_id"] = payload.university_id
        except (TypeError, ValueError):
            pass

        raw_result = search_service.search(**search_kwargs)
        cancel_token.check("response_preparation")
    except SearchCancelledError as exc:
        logger.info("Search request cancelled cooperatively: %s", exc)
        return JSONResponse(
            status_code=499,
            content={
                "request_id": request_id,
                "status": "cancelled",
                "detail": "Search request was cancelled.",
            },
        )
    except SQLAlchemyError as exc:
        logger.exception("Database error during search (request_id=%s): %s", request_id, exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc
    except (UnexpectedResponse, ConnectionError, TimeoutError) as exc:
        logger.exception("Qdrant error during search (request_id=%s): %s", request_id, exc)
        raise HTTPException(status_code=503, detail="Search vector index is currently unavailable.") from exc
    except ValueError as exc:
        if "collection" in str(exc).lower() or "qdrant" in str(exc).lower():
            logger.exception("Qdrant collection error during search (request_id=%s): %s", request_id, exc)
            raise HTTPException(status_code=503, detail="Search vector index is currently unavailable.") from exc
        logger.exception("Value error during search (request_id=%s): %s", request_id, exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while executing search.") from exc
    except Exception as exc:
        logger.exception("Unexpected error during search (request_id=%s): %s", request_id, exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while executing search.") from exc
    finally:
        registry.unregister(request_id)

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    expansion = raw_result.get("expansion")
    expanded_queries = (
        [eq.query_text for eq in expansion.queries]
        if expansion is not None and getattr(expansion, "queries", None)
        else [payload.query]
    )

    mapped_results: List[SearchProfessorResultSchema] = []
    for item in raw_result.get("results", []):
        evidence_items = [
            SupportingEvidenceSchema(
                evidence_id=ev.get("evidence_id"),
                evidence_type=ev.get("evidence_type", ""),
                relevance_group=ev.get("relevance_group"),
                topic_relevance_note=ev.get("topic_relevance_note"),
                title=ev.get("title"),
                snippet=ev.get("snippet"),
                source_url=ev.get("source_url"),
                verification_status=ev.get("verification_status"),
                matched_by_query=ev.get("matched_by_query"),
                score=float(ev.get("score", 0.0)),
                authorship_note=ev.get("authorship_note"),
                role=ev.get("role"),
                sponsor=ev.get("sponsor"),
                project_category=ev.get("project_category"),
            )
            for ev in item.supporting_evidence
        ]
        mapped_results.append(
            SearchProfessorResultSchema(
                professor_id=item.professor_id,
                professor_name=item.professor_name,
                department=item.department_name or item.department_code,
                department_code=item.department_code,
                department_name=item.department_name,
                designation=item.designation,
                email=item.email,
                profile_url=item.profile_url,
                score=item.score,
                match_category=item.match_category,
                research_interests=item.research_interests,
                biography=getattr(item, "biography", None),
                evidence_counts=item.evidence_counts,
                matched_topics=item.matched_topics,
                matched_queries=item.matched_queries,
                supporting_evidence=evidence_items,
                explanation=item.explanation,
            )
        )

    total_qualifying = int(raw_result.get("total_qualifying_results", len(mapped_results)))
    resp_offset = int(raw_result.get("offset", payload.offset))
    has_more = bool(raw_result.get("has_more", (resp_offset + len(mapped_results)) < total_qualifying))

    return SearchResponseSchema(
        request_id=request_id,
        query=raw_result.get("query", payload.query),
        expanded_queries=expanded_queries,
        status=raw_result.get("status", "ok"),
        message=raw_result.get("message"),
        search_latency_ms=latency_ms,
        total_results=len(mapped_results),
        total_qualifying_results=total_qualifying,
        offset=resp_offset,
        limit=payload.limit,
        has_more=has_more,
        results=mapped_results,
    )


# -------------------------------------------------------------------------
# University Endpoints
# -------------------------------------------------------------------------

@app.get("/universities", response_model=List[UniversitySchema], tags=["Universities"])
def list_universities(
    country: Optional[str] = Query(None, description="Filter by country"),
    db: Session = Depends(get_db)
):
    query = db.query(University)
    if country is not None:
        query = query.filter(University.country.ilike(f"%{country}%"))
    return query.all()


@app.get("/universities/{university_id}/departments", response_model=List[DepartmentSchema], tags=["Departments"])
def list_university_departments(
    university_id: int,
    db: Session = Depends(get_db)
):
    univ = db.query(University).filter(University.id == university_id).first()
    if not univ:
        raise HTTPException(status_code=404, detail="University not found")
    return univ.departments


# -------------------------------------------------------------------------
# Department Endpoints
# -------------------------------------------------------------------------

@app.get("/departments/{department_id}/professors", response_model=List[ProfessorBriefSchema], tags=["Professors"])
def list_department_professors(
    department_id: int,
    status: Optional[str] = Query(None, description="Filter by verification_status: pending, verified, rejected, needs_review"),
    has_publications: Optional[bool] = Query(None, description="Filter by publication availability"),
    db: Session = Depends(get_db)
):
    dept = db.query(Department).filter(Department.id == department_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")

    query = db.query(Professor).filter(Professor.department_id == department_id)
    if status is not None:
        query = query.filter(Professor.verification_status == status)
    if has_publications is not None:
        query = query.filter(Professor.has_publications == has_publications)
    return query.order_by(Professor.name.asc()).all()


# -------------------------------------------------------------------------
# Professor Endpoints
# -------------------------------------------------------------------------

@app.get("/professors", response_model=List[ProfessorBriefSchema], tags=["Professors"])
def list_professors(
    department_id: Optional[int] = Query(None, description="Filter by department ID"),
    status: Optional[str] = Query(None, description="Filter by verification_status"),
    has_publications: Optional[bool] = Query(None, description="Filter by publication availability"),
    search: Optional[str] = Query(None, description="Search by professor name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(Professor)
    if department_id is not None:
        query = query.filter(Professor.department_id == department_id)
    if status is not None:
        query = query.filter(Professor.verification_status == status)
    if has_publications is not None:
        query = query.filter(Professor.has_publications == has_publications)
    if search is not None:
        query = query.filter(Professor.name.ilike(f"%{search}%"))

    offset = (page - 1) * page_size
    return query.order_by(Professor.id.asc()).offset(offset).limit(page_size).all()


@app.get("/professors/{professor_id}", response_model=ProfessorDetailSchema, tags=["Professors"])
def get_professor(
    professor_id: int,
    db: Session = Depends(get_db)
):
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor not found")
    return prof


@app.get("/professors/{professor_id}/profile", response_model=ProfessorProfileSchema, tags=["Professors"])
def get_professor_profile(
    professor_id: int,
    db: Session = Depends(get_db),
):
    """
    Returns a complete professor profile (institution, department, biography, normalized
    research interests, canonical topics, research projects with resolved source URLs,
    verified publications, and unverified candidate publications) in one eager-loaded query.
    """
    try:
        prof = (
            db.query(Professor)
            .options(
                joinedload(Professor.department).joinedload(Department.university),
                selectinload(Professor.topics),
                selectinload(Professor.professor_projects).joinedload(ProfessorProject.project),
                selectinload(Professor.professor_publications).joinedload(ProfessorPublication.publication),
            )
            .filter(Professor.id == professor_id)
            .first()
        )
    except SQLAlchemyError as exc:
        logger.exception("Database error loading professor profile (professor_id=%s): %s", professor_id, exc)
        raise HTTPException(status_code=503, detail="Database is currently unavailable.") from exc
    except Exception as exc:
        logger.exception("Unexpected error loading professor profile (professor_id=%s): %s", professor_id, exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred while loading the profile.") from exc

    if not prof:
        raise HTTPException(status_code=404, detail="Professor not found")

    dept = prof.department
    univ = dept.university if dept else None
    prof_source_url = prof.profile_url or prof.source_url

    # Normalize known scraped typo at serialization time without altering DB records
    normalized_interests = (
        normalize_known_research_typos(prof.research_interests)
        if prof.research_interests
        else None
    )

    # Canonical research topics (deduplicated, sorted deterministically)
    topics_list = [
        ResearchTopicSchema.model_validate(t)
        for t in sorted(prof.topics or [], key=lambda x: ((x.canonical_topic_name or x.topic_name or "").lower(), x.id))
        if not getattr(t, "is_noisy_artifact", False)
    ]

    # Research projects: preserve all projects, resolve source_url per professor,
    # and place primary research projects ahead of administrative/grant records.
    category_priority = {
        "sponsored_research": 0,
        "industrial_consultancy": 1,
        "routine_testing_vetting": 2,
        "administrative_or_grant": 3,
    }
    projects_list: List[ProfessorProfileProjectSchema] = []
    seen_project_pairs = set()
    for pproj in sorted(prof.professor_projects or [], key=lambda x: x.id):
        proj = pproj.project
        if not proj or not (proj.title or "").strip():
            continue
        pair_key = (proj.id, pproj.role or "")
        if pair_key in seen_project_pairs:
            continue
        seen_project_pairs.add(pair_key)
        cat = proj.project_category or "sponsored_research"
        projects_list.append(
            ProfessorProfileProjectSchema(
                project_id=proj.id,
                title=proj.title.strip(),
                description=proj.description,
                category=cat,
                sponsor=proj.sponsor,
                status=proj.status,
                role=pproj.role,
                source_url=resolve_project_source_url(proj.source_url, prof_source_url),
                is_administrative_or_grant=(cat == "administrative_or_grant"),
            )
        )
    projects_list.sort(
        key=lambda p: (
            category_priority.get(p.category, 2),
            (p.title or "").lower(),
            p.project_id,
        )
    )

    # Publications: strictly separate verified vs unverified candidate (`pending`/`needs_review`);
    # never include `rejected` links and never upgrade candidate authorship.
    verified_pubs: List[ProfessorProfilePublicationSchema] = []
    candidate_pubs: List[ProfessorProfilePublicationSchema] = []
    verified_pub_ids = {
        pp.publication_id
        for pp in (prof.professor_publications or [])
        if pp.verification_status == "verified"
    }

    for ppub in prof.professor_publications or []:
        link_status = ppub.verification_status
        if link_status == "rejected":
            continue
        pub = ppub.publication
        if not pub or not (pub.title or "").strip():
            continue

        if link_status == "verified":
            verified_pubs.append(
                ProfessorProfilePublicationSchema(
                    publication_id=pub.id,
                    title=pub.title.strip(),
                    abstract=pub.abstract,
                    doi=pub.doi,
                    publication_year=pub.publication_year,
                    journal_or_conference=pub.journal_or_conference,
                    paper_url=pub.paper_url,
                    source_url=pub.source_url,
                    source_name=pub.source_name,
                    citation_count=pub.citation_count or 0,
                    author_position=ppub.author_position,
                    verification_status=link_status,
                    is_unverified=False,
                    authorship_note=None,
                )
            )
        elif link_status in ("pending", "needs_review"):
            if pub.id in verified_pub_ids:
                continue
            candidate_pubs.append(
                ProfessorProfilePublicationSchema(
                    publication_id=pub.id,
                    title=pub.title.strip(),
                    abstract=pub.abstract,
                    doi=pub.doi,
                    publication_year=pub.publication_year,
                    journal_or_conference=pub.journal_or_conference,
                    paper_url=pub.paper_url,
                    source_url=pub.source_url,
                    source_name=pub.source_name,
                    citation_count=pub.citation_count or 0,
                    author_position=ppub.author_position,
                    verification_status=link_status,
                    confidence_score=ppub.confidence_score,
                    affiliation_evidence=ppub.affiliation_evidence,
                    is_unverified=True,
                    authorship_note=CANDIDATE_DISCLOSURE_LABEL,
                )
            )

    verified_pubs.sort(key=lambda p: (-(p.publication_year or 0), -p.citation_count, p.publication_id))
    candidate_pubs.sort(
        key=lambda p: (-(p.confidence_score or 0.0), -(p.publication_year or 0), p.publication_id)
    )

    return ProfessorProfileSchema(
        professor_id=prof.id,
        name=prof.name,
        designation=prof.designation,
        email=prof.email,
        academic_unit=prof.academic_unit or (dept.academic_unit if dept else None),
        department_id=prof.department_id,
        department_name=dept.name if dept else None,
        department_code=dept.code if dept else None,
        university_id=univ.id if univ else (dept.university_id if dept else None),
        university_name=univ.name if univ else None,
        university_website=univ.website if univ else None,
        biography=prof.biography,
        educational_background=prof.educational_background,
        research_interests=normalized_interests,
        research_group=prof.research_group,
        profile_url=prof.profile_url,
        source_url=prof.source_url,
        verification_status=prof.verification_status,
        orcid=prof.orcid,
        irins_id=prof.irins_id,
        openalex_author_id=prof.openalex_author_id,
        last_updated=prof.last_updated,
        contact_info=build_professor_contact_info(prof, dept, univ),
        research_topics=topics_list,
        research_projects=projects_list,
        verified_publications=verified_pubs,
        candidate_publications=candidate_pubs,
    )


PUBLIC_PUBLICATION_STATUSES = ("verified", "pending", "needs_review")
ALL_PUBLICATION_STATUSES = PUBLIC_PUBLICATION_STATUSES + ("rejected",)


@app.get("/professors/{professor_id}/publications", response_model=List[ProfessorPublicationSchema], tags=["Publications"])
def get_professor_publications(
    professor_id: int,
    status: Optional[str] = Query(
        "verified",
        description=(
            "Link verification status. Defaults to 'verified'. Candidate links require an explicit "
            "'pending' or 'needs_review' filter. Rejected links are only available via "
            "/admin/review/professors/{professor_id}/publications."
        )
    ),
    db: Session = Depends(get_db)
):
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor not found")

    # Direct (non-HTTP) calls may pass None; treat as the public default.
    effective_status = status if isinstance(status, str) and status else "verified"
    if effective_status == "rejected":
        raise HTTPException(
            status_code=403,
            detail="Rejected publication links are restricted to administrative review endpoints."
        )
    if effective_status not in PUBLIC_PUBLICATION_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{effective_status}'. Allowed: {', '.join(PUBLIC_PUBLICATION_STATUSES)}"
        )

    return (
        db.query(ProfessorPublication)
        .filter(
            ProfessorPublication.professor_id == professor_id,
            ProfessorPublication.verification_status == effective_status
        )
        .order_by(ProfessorPublication.confidence_score.desc(), ProfessorPublication.id.asc())
        .all()
    )


# -------------------------------------------------------------------------
# Publication Endpoints
# -------------------------------------------------------------------------

@app.get("/publications/{publication_id}", response_model=PublicationDetailSchema, tags=["Publications"])
def get_publication(
    publication_id: int,
    db: Session = Depends(get_db)
):
    pub = db.query(Publication).filter(Publication.id == publication_id).first()
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    return pub


# -------------------------------------------------------------------------
# Admin Review Endpoints
# -------------------------------------------------------------------------

@app.get("/admin/review/faculty", response_model=List[ProfessorBriefSchema], tags=["Admin Verification"])
def get_faculty_for_review(
    status: str = Query("pending", description="pending, needs_review, rejected, verified"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size
    return (
        db.query(Professor)
        .filter(Professor.verification_status == status)
        .order_by(Professor.id.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )


@app.get(
    "/admin/review/professors/{professor_id}/publications",
    response_model=List[ProfessorPublicationSchema],
    tags=["Admin Verification"]
)
def get_professor_publications_for_review(
    professor_id: int,
    status: Optional[str] = Query(None, description="verified, pending, needs_review, rejected; omit for all"),
    db: Session = Depends(get_db)
):
    prof = db.query(Professor).filter(Professor.id == professor_id).first()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor not found")
    query = db.query(ProfessorPublication).filter(ProfessorPublication.professor_id == professor_id)
    if isinstance(status, str) and status:
        if status not in ALL_PUBLICATION_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid status '{status}'")
        query = query.filter(ProfessorPublication.verification_status == status)
    return query.order_by(ProfessorPublication.id.asc()).all()


@app.get("/admin/review/publications", response_model=List[PublicationBriefSchema], tags=["Admin Verification"])
def get_publications_for_review(
    status: str = Query("pending", description="pending, needs_review, rejected, verified"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    offset = (page - 1) * page_size
    return (
        db.query(Publication)
        .filter(Publication.verification_status == status)
        .order_by(Publication.id.asc())
        .offset(offset)
        .limit(page_size)
        .all()
    )
