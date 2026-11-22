import json
import tempfile
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
import pytest
from sqlalchemy import create_engine, inspect
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
    ResearchTopic,
    SearchDocument,
    University,
)
from backend.search.document_builder import (
    CANDIDATE_DISCLOSURE_LABEL,
    DocumentBuilder,
    make_deterministic_document_id,
)
from backend.search.embedding import DeterministicHashEmbeddingProvider
from backend.search.index_sync import IndexSyncService
from backend.search.qdrant_index import QdrantIndexManager


def test_alembic_upgrade_preserves_existing_tables_and_matches_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "alembic_test.db"
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url)

        # Simulate existing 12 baseline tables with data BEFORE running alembic
        baseline_tables = [
            t for t in Base.metadata.sorted_tables
            if t.name not in ("search_documents", "index_sync_state", "embedding_cache")
        ]
        Base.metadata.create_all(engine, tables=baseline_tables)

        Session = sessionmaker(bind=engine)
        s = Session()
        s.add(University(id=1, name="IIT Kharagpur", country="India", city="Kharagpur"))
        s.add(Department(id=1, university_id=1, name="Computer Science and Engineering", code="CS"))
        s.commit()
        s.close()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(cfg, "head")

        insp = inspect(engine)
        table_names = set(insp.get_table_names())
        assert "search_documents" in table_names
        assert "index_sync_state" in table_names
        assert "embedding_cache" in table_names
        assert "alembic_version" in table_names

        # Verify existing data was preserved untouched
        s2 = Session()
        assert s2.query(University).count() == 1
        assert s2.query(Department).count() == 1
        s2.close()

        # Verify schema parity with Base.metadata
        with engine.connect() as conn:
            mc = MigrationContext.configure(conn)
            diff = compare_metadata(mc, Base.metadata)
            assert diff == []

        engine.dispose()


def test_document_builder_determinism_idempotency_and_qdrant_sync():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    u = University(id=1, name="IIT Kharagpur", country="India", city="Kharagpur")
    d = Department(id=1, university_id=1, name="Computer Science and Engineering", code="CS", academic_unit="Engineering Divisions")
    prof1 = Professor(
        id=10,
        department_id=1,
        name="Prof Verified",
        biography="Dr. Verified works on deep graph neural networks and natural language processing for low-resource Indian languages.",
        research_interests="Graph Neural Networks, Natural Language Processing",
        research_group="Complex Networks Research Group",
        profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-v",
        verification_status="verified",
        has_publications=True,
        has_projects=True,
    )
    prof2 = Professor(
        id=20,
        department_id=1,
        name="Prof Coauthor",
        research_interests="Machine Learning",
        verification_status="verified",
        has_publications=False,
    )
    prof_rejected = Professor(
        id=30,
        department_id=1,
        name="Prof Rejected",
        research_interests="Should Not Be Indexed",
        verification_status="rejected",
    )

    t1 = ResearchTopic(
        id=1,
        topic_name="NLP",
        canonical_topic_name="Natural Language Processing",
        domain_name="Computer Science & Artificial Intelligence",
        area_name="Natural Language Processing & Information Retrieval",
        is_generic_root=False,
        is_noisy_artifact=False,
    )
    t_noisy = ResearchTopic(
        id=2,
        topic_name="Object (grammar)",
        canonical_topic_name="Object (grammar)",
        domain_name="Humanities, Social Sciences, Management & Law",
        area_name="Humanities, Psychology & Social Sciences",
        is_generic_root=False,
        is_noisy_artifact=True,
    )
    prof1.topics.extend([t1, t_noisy])

    proj = ResearchProject(
        id=100,
        title="Federated Graph Learning at Scale",
        original_title="FEDERATED GRAPH LEARNING AT SCALE",
        project_category="sponsored_research",
        sponsor="MeitY",
        status="current",
    )
    pproj = ProfessorProject(id=500, professor_id=10, project_id=100, role="Principal Investigator")

    pub_ver = Publication(
        id=200,
        openalex_id="W200",
        doi="10.1145/200",
        title="Scalable Graph Neural Networks",
        abstract="We propose a scalable graph neural network architecture.",
        publication_year=2024,
        journal_or_conference="KDD",
        verification_status="verified",
        citation_count=12,
    )
    pub_cand = Publication(
        id=201,
        openalex_id="W201",
        doi="10.1145/201",
        title="Multilingual Low-Resource Translation",
        abstract="Neural machine translation for low-resource Indian languages.",
        publication_year=2025,
        journal_or_conference="ACL",
        verification_status="pending",
        citation_count=3,
    )
    pub_rej = Publication(
        id=202,
        openalex_id="W202",
        doi="10.1145/202",
        title="Unrelated Control Paper",
        verification_status="rejected",
        citation_count=0,
    )

    # Co-authored paper: verified on prof1, pending on prof2, plus rejected link
    link_ver = ProfessorPublication(id=1, professor_id=10, publication_id=200, confidence_score=0.95, verification_status="verified")
    link_coauth_pend = ProfessorPublication(id=2, professor_id=20, publication_id=200, confidence_score=0.88, verification_status="pending")
    link_cand = ProfessorPublication(id=3, professor_id=10, publication_id=201, confidence_score=0.60, verification_status="needs_review")
    link_rej = ProfessorPublication(id=4, professor_id=10, publication_id=202, confidence_score=0.0, verification_status="rejected")

    db.add_all([u, d, prof1, prof2, prof_rejected, t1, t_noisy, proj, pproj, pub_ver, pub_cand, pub_rej, link_ver, link_coauth_pend, link_cand, link_rej])
    db.commit()

    builder = DocumentBuilder()
    stats1 = builder.rebuild_and_sync_documents(db)
    assert stats1["inserted"] == stats1["total_documents"]
    assert stats1["updated"] == 0
    assert stats1["deleted"] == 0
    assert stats1["by_evidence_type"][EvidenceType.VERIFIED_PUBLICATION.value] == 1
    assert stats1["by_evidence_type"][EvidenceType.CANDIDATE_PUBLICATION.value] == 2
    assert stats1["by_evidence_type"][EvidenceType.RESEARCH_PROJECT.value] == 1
    assert stats1["by_evidence_type"][EvidenceType.RESEARCH_INTEREST.value] == 2
    assert stats1["by_evidence_type"][EvidenceType.BIOGRAPHY.value] == 1
    assert stats1["by_evidence_type"][EvidenceType.DEPARTMENT_CONTEXT.value] == 1

    # Rejected professor (id=30) and rejected publication (id=202) must never appear in search_documents
    assert db.query(SearchDocument).filter_by(professor_id=30).count() == 0
    assert db.query(SearchDocument).filter_by(source_table="publications", source_id=202).count() == 0

    # Candidate publications must carry the mandatory disclosure label and exact status ('pending' vs 'needs_review')
    cand_docs = db.query(SearchDocument).filter_by(evidence_type=EvidenceType.CANDIDATE_PUBLICATION.value).all()
    assert len(cand_docs) == 2
    for cdoc in cand_docs:
        meta = json.loads(cdoc.metadata_json)
        assert meta["candidate_disclosure_label"] == CANDIDATE_DISCLOSURE_LABEL
        assert cdoc.verification_status in ("pending", "needs_review")

    # Noisy topic 'Object (grammar)' must be excluded from canonical_topics_json
    prof1_int_doc = db.query(SearchDocument).filter_by(professor_id=10, evidence_type=EvidenceType.RESEARCH_INTEREST.value).one()
    assert json.loads(prof1_int_doc.canonical_topics_json) == ["Natural Language Processing"]

    # Second run with no changes must be 100% idempotent
    stats2 = builder.rebuild_and_sync_documents(db)
    assert stats2["inserted"] == 0
    assert stats2["updated"] == 0
    assert stats2["deleted"] == 0
    assert stats2["unchanged"] == stats1["total_documents"]

    # Synchronize into in-memory Qdrant via IndexSyncService
    provider = DeterministicHashEmbeddingProvider()
    qdrant_mgr = QdrantIndexManager(vector_dim=provider.vector_dim)
    sync_svc = IndexSyncService(index_manager=qdrant_mgr, embedding_provider=provider)

    sync1 = sync_svc.sync_documents(db)
    assert sync1["upserted"] == stats1["total_documents"]
    # Co-authored pub_id=200 is shared by prof1 (verified) and prof2 (pending) -> 1 less unique hash than total docs!
    assert sync1["unique_hashes_embedded"] == stats1["total_documents"] - 1
    assert qdrant_mgr.count_points() == stats1["total_documents"]

    # Second sync with no changes does zero upserts and zero embeddings
    sync2 = sync_svc.sync_documents(db)
    assert sync2["upserted"] == 0
    assert sync2["payload_updated_only"] == 0
    assert sync2["unchanged"] == stats1["total_documents"]
    assert sync2["unique_hashes_embedded"] == 0

    # Updating only confidence_score on link_cand triggers payload-only update without re-embedding
    link_cand.confidence_score = 0.72
    db.commit()
    builder.rebuild_and_sync_documents(db)
    sync3 = sync_svc.sync_documents(db)
    assert sync3["upserted"] == 0
    assert sync3["payload_updated_only"] == 1
    assert sync3["unique_hashes_embedded"] == 0

    # Rejecting link_cand deletes the candidate_publication document from both PostgreSQL/SQLite and Qdrant
    link_cand.verification_status = "rejected"
    db.commit()
    stats4 = builder.rebuild_and_sync_documents(db)
    assert stats4["deleted"] == 1
    sync4 = sync_svc.sync_documents(db)
    assert sync4["deleted"] == 1
    assert qdrant_mgr.count_points() == stats1["total_documents"] - 1

    # Hybrid search works per evidence_type
    q_emb = provider.encode(["graph neural networks natural language processing"])[0]
    hits = qdrant_mgr.hybrid_search(
        q_emb,
        evidence_types=[EvidenceType.VERIFIED_PUBLICATION.value, EvidenceType.RESEARCH_INTEREST.value],
        limit=5,
    )
    assert len(hits) >= 2
    assert all(h["payload"]["evidence_type"] in ("verified_publication", "research_interest") for h in hits)

    # Switching to a fresh Qdrant instance that lacks points must re-upsert missing points from embedding_cache
    qdrant_fresh = QdrantIndexManager(vector_dim=provider.vector_dim)
    sync_fresh = IndexSyncService(index_manager=qdrant_fresh, embedding_provider=provider)
    fresh_res = sync_fresh.sync_documents(db)
    assert fresh_res["upserted"] == stats1["total_documents"] - 1
    assert fresh_res["unique_hashes_embedded"] == 0
    assert qdrant_fresh.count_points() == stats1["total_documents"] - 1

    db.close()
    engine.dispose()
