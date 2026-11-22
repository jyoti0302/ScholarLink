from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    Department,
    EvidenceType,
    Professor,
    ProfessorProject,
    ProfessorPublication,
    Publication,
    ResearchProject,
    University,
)
from backend.search.document_builder import CANDIDATE_DISCLOSURE_LABEL, DocumentBuilder
from backend.search.embedding import DeterministicHashEmbeddingProvider
from backend.search.index_sync import IndexSyncService
from backend.search.qdrant_index import QdrantIndexManager
from backend.search.query_understanding import QueryExpansionService, QueryUnderstandingService
from backend.search.ranking import SearchService
from backend.search.retrieval import HybridRetrievalService, QueryEmbeddingService


def test_query_understanding_and_rules_fallback_without_llm():
    u_svc = QueryUnderstandingService()
    u = u_svc.understand("I want to work on Generative AI for healthcare.")
    assert u.main_field == "Generative Ai"
    assert u.application_domain == "Healthcare"
    assert u.provider_used == "rules"

    # Failing LLM must fall back cleanly to deterministic taxonomy/alias expansion
    def _broken_llm(q, u_res, k):
        raise TimeoutError("LLM timed out")

    exp_svc = QueryExpansionService(understanding_service=u_svc, max_expansions=5, llm_expander=_broken_llm)
    res = exp_svc.expand("I want to work on Generative AI for healthcare.")
    assert res.understanding.provider_used == "rules"
    assert res.queries[0].query_kind == "original"
    assert 2 <= len(res.queries) <= 6  # original + up to 5 expanded


def test_different_queries_are_encoded_from_own_text_and_aggregated_per_professor():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    univ = University(id=1, name="IIT Kharagpur", country="India", city="Kharagpur")
    dept = Department(id=1, university_id=1, name="Computer Science and Engineering", code="CS")
    # Professor 1 has NO verified publications, only interests + project + candidate publication
    p1 = Professor(
        id=1,
        department_id=1,
        name="Prof No Verified Pubs",
        research_interests="Generative AI, Medical Imaging, Clinical Decision Support",
        biography="Works on multimodal learning for healthcare diagnosis.",
        verification_status="verified",
        has_publications=False,
    )
    # Professor 2 has only a candidate publication (must never become a 'strong' match alone)
    p2 = Professor(
        id=2,
        department_id=1,
        name="Prof Candidate Only",
        verification_status="verified",
        has_publications=False,
    )
    proj = ResearchProject(
        id=10,
        title="Generative AI for Clinical Decision Support",
        project_category="sponsored_research",
        sponsor="ICMR",
        status="current",
    )
    pp1 = ProfessorProject(id=10, professor_id=1, project_id=10, role="Principal Investigator")

    pub_cand = Publication(
        id=20,
        title="Generative AI in Healthcare Surveys",
        abstract="Survey of generative AI for medical imaging.",
        verification_status="pending",
    )
    link_cand = ProfessorPublication(id=20, professor_id=2, publication_id=20, confidence_score=0.85, verification_status="pending")

    db.add_all([univ, dept, p1, p2, proj, pp1, pub_cand, link_cand])
    db.commit()

    DocumentBuilder().rebuild_and_sync_documents(db)
    provider = DeterministicHashEmbeddingProvider()
    q_mgr = QdrantIndexManager(vector_dim=provider.vector_dim)
    IndexSyncService(index_manager=q_mgr, embedding_provider=provider).sync_documents(db)

    q_emb_svc = QueryEmbeddingService(provider=provider)
    emb_res = q_emb_svc.embed_queries(QueryExpansionService().expand("Generative AI for healthcare").queries)
    vecs = list(emb_res.values())
    # Distinct queries must produce distinct vectors encoded from their own text
    assert vecs[0].dense != vecs[1].dense

    search_svc = SearchService(
        expansion_service=QueryExpansionService(max_expansions=4),
        retrieval_service=HybridRetrievalService(index_manager=q_mgr, query_embedding_service=q_emb_svc),
    )
    out = search_svc.search(db, "Generative AI for healthcare", top_k=5)
    assert out["status"] == "ok"
    results = out["results"]
    # Each professor appears once (aggregated, not duplicated per expanded query)
    prof_ids = [r.professor_id for r in results]
    assert len(prof_ids) == len(set(prof_ids))

    # Professor 1 (no verified publications, but interests + project + bio) ranks first
    assert results[0].professor_id == 1
    assert results[0].match_category in ("strong", "related")

    # Professor 2 (candidate publication only) cannot be a 'strong' match and carries disclosure label
    p2_res = [r for r in results if r.professor_id == 2]
    if p2_res:
        assert p2_res[0].match_category != "strong"
        assert p2_res[0].supporting_evidence[0]["authorship_note"] == CANDIDATE_DISCLOSURE_LABEL

    db.close()
    engine.dispose()
