from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.main import app, get_search_service
from backend.database.connection import get_db
from backend.database.models import Base, Department, EvidenceType, Professor, University
from backend.search.query_understanding import ExpandedQuery, QueryExpansionResult, QueryUnderstandingResult
from backend.search.ranking import RankedProfessorMatch


def _setup_in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = Session()

    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur", website="https://www.iitkgp.ac.in/")
    db.add(univ)
    db.commit()

    dept = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS")
    db.add(dept)
    db.commit()

    prof = Professor(
        department_id=dept.id,
        name="Pawan Goyal",
        designation="Associate Professor",
        email="pawang@cse.iitkgp.ac.in",
        profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang",
        research_interests="Natural Language Processing, Information Retrieval",
        verification_status="verified",
    )
    db.add(prof)
    db.commit()
    univ_id, dept_id, prof_id = int(univ.id), int(dept.id), int(prof.id)
    db.close()
    return engine, Session, univ_id, dept_id, prof_id


class _StubSearchService:
    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.calls = []

    def search(self, db, query, top_k=10, use_expansion=True, department_ids=None, include_candidate_publications=True):
        self.calls.append({"query": query, "top_k": top_k})
        if self.mode == "db_error":
            raise OperationalError("SELECT 1", {}, Exception("db down"))
        if self.mode == "qdrant_error":
            raise ValueError("Collection research_evidence_v1 not found")
        if self.mode == "unexpected_error":
            raise RuntimeError("sensitive internal detail")

        exp = QueryExpansionResult(
            understanding=QueryUnderstandingResult(
                raw_query=query,
                cleaned_query=query,
                main_field="Computer Science",
                application_domain="NLP",
                core_concepts=["nlp"],
            ),
            queries=[ExpandedQuery(query_text=query, query_kind="original", weight=1.0)],
        )

        if self.mode == "missing_optional":
            match = RankedProfessorMatch(
                professor_id=99,
                professor_name="Test Faculty",
                department_code="HS",
                department_name="Humanities and Social Sciences",
                profile_url=None,
                score=2.15,
                match_category="related",
                evidence_counts={EvidenceType.RESEARCH_INTEREST.value: 1},
                matched_topics=["Economics"],
                matched_queries=[query],
                supporting_evidence=[
                    {
                        "evidence_id": "doc_99_ri",
                        "evidence_type": EvidenceType.RESEARCH_INTEREST.value,
                        "title": "Research Interests",
                        "snippet": "Monetary policy",
                        "source_url": None,
                        "verification_status": "verified",
                        "matched_by_query": query,
                        "score": 0.59,
                    }
                ],
                explanation="Related match supported by: official profile research interests.",
                designation=None,
                email=None,
                research_interests=None,
            )
            return {"query": query, "expansion": exp, "status": "ok", "message": None, "results": [match]}

        match = RankedProfessorMatch(
            professor_id=1,
            professor_name="Pawan Goyal",
            department_code="CS",
            department_name="Computer Science and Engineering",
            profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang",
            score=3.2064,
            match_category="strong",
            evidence_counts={EvidenceType.RESEARCH_INTEREST.value: 1, EvidenceType.VERIFIED_PUBLICATION.value: 1},
            matched_topics=["Natural Language Processing"],
            matched_queries=[query],
            supporting_evidence=[
                {
                    "evidence_id": "doc_1_pub",
                    "evidence_type": EvidenceType.VERIFIED_PUBLICATION.value,
                    "title": "NLP for Indian Languages",
                    "snippet": "Cross-lingual representation learning",
                    "source_url": "https://doi.org/10.1000/test",
                    "verification_status": "verified",
                    "matched_by_query": query,
                    "score": 0.64,
                }
            ],
            explanation="Strong match supported by: 1 verified publication(s), official profile research interests.",
            designation="Associate Professor",
            email="pawang@cse.iitkgp.ac.in",
            research_interests="Natural Language Processing, Information Retrieval",
        )
        return {"query": query, "expansion": exp, "status": "ok", "message": None, "results": [match]}


def test_post_search_success_and_crud_endpoints():
    engine, Session, univ_id, dept_id, prof_id = _setup_in_memory_db()
    stub = _StubSearchService(mode="ok")

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = lambda: stub
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/search",
                json={"query": "Natural language processing for Indian languages", "limit": 10},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["request_id"]
            assert data["query"] == "Natural language processing for Indian languages"
            assert data["status"] == "ok"
            assert data["search_latency_ms"] >= 0.0
            assert data["total_results"] == 1
            res = data["results"][0]
            assert res["professor_id"] == 1
            assert res["professor_name"] == "Pawan Goyal"
            assert res["department_code"] == "CS"
            assert res["designation"] == "Associate Professor"
            assert res["email"] == "pawang@cse.iitkgp.ac.in"
            assert res["profile_url"] == "https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang"
            assert res["match_category"] == "strong"
            assert res["research_interests"] == "Natural Language Processing, Information Retrieval"
            assert res["supporting_evidence"][0]["evidence_id"] == "doc_1_pub"
            assert res["supporting_evidence"][0]["evidence_type"] == "verified_publication"
            assert res["supporting_evidence"][0]["verification_status"] == "verified"

            # Existing CRUD endpoints still work
            assert client.get("/").status_code == 200
            assert client.get("/universities").status_code == 200
            assert client.get(f"/universities/{univ_id}/departments").status_code == 200
            assert client.get(f"/departments/{dept_id}/professors").status_code == 200
            assert client.get(f"/professors/{prof_id}").status_code == 200
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_post_search_validation_empty_and_invalid_limit():
    engine, Session, _, _, _ = _setup_in_memory_db()
    stub = _StubSearchService(mode="ok")

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_search_service] = lambda: stub
    try:
        with TestClient(app) as client:
            assert client.post("/search", json={"query": "", "limit": 10}).status_code == 422
            assert client.post("/search", json={"query": "   \t\n ", "limit": 10}).status_code == 422
            assert client.post("/search", json={"query": "AI", "limit": 0}).status_code == 422
            assert client.post("/search", json={"query": "AI", "limit": -1}).status_code == 422
            assert client.post("/search", json={"query": "AI", "limit": 51}).status_code == 422
            assert client.post("/search", json={"query": "AI", "limit": "invalid"}).status_code == 422
            assert stub.calls == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_post_search_error_handling_and_missing_optional_fields():
    engine, Session, _, _, _ = _setup_in_memory_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        app.dependency_overrides[get_search_service] = lambda: _StubSearchService(mode="missing_optional")
        with TestClient(app) as client:
            r_opt = client.post("/search", json={"query": "Monetary policy", "limit": 5})
            assert r_opt.status_code == 200
            item = r_opt.json()["results"][0]
            assert item["designation"] is None
            assert item["email"] is None
            assert item["profile_url"] is None
            assert item["research_interests"] is None
            assert item["supporting_evidence"][0]["source_url"] is None

        app.dependency_overrides[get_search_service] = lambda: _StubSearchService(mode="db_error")
        with TestClient(app) as client:
            assert client.post("/search", json={"query": "Monetary policy", "limit": 5}).status_code == 503

        app.dependency_overrides[get_search_service] = lambda: _StubSearchService(mode="qdrant_error")
        with TestClient(app) as client:
            assert client.post("/search", json={"query": "Monetary policy", "limit": 5}).status_code == 503

        app.dependency_overrides[get_search_service] = lambda: _StubSearchService(mode="unexpected_error")
        with TestClient(app) as client:
            r_500 = client.post("/search", json={"query": "Monetary policy", "limit": 5})
            assert r_500.status_code == 500
            assert "sensitive internal detail" not in r_500.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
