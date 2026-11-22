from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine

from backend.database.models import (
    Base,
    Department,
    Professor,
    ProfessorProject,
    ProfessorPublication,
    Publication,
    ResearchProject,
    ResearchTopic,
    University,
    VerificationRecord,
)
from scripts.migrate_sqlite_to_postgres import collect_db_fingerprint, migrate_database


def test_sqlite_to_target_migration_preserves_all_records_and_relationships():
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "src.db"
        tgt_path = Path(tmpdir) / "tgt.db"
        src_url = f"sqlite:///{src_path}"
        tgt_url = f"sqlite:///{tgt_path}"

        src_engine = create_engine(src_url)
        Base.metadata.create_all(src_engine)

        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=src_engine)
        db = Session()

        u = University(id=1, name="IIT Kharagpur", country="India", city="Kharagpur")
        d = Department(id=10, university_id=1, name="Computer Science and Engineering", code="CS")
        p = Professor(
            id=27,
            department_id=10,
            name="Abhijit Das",
            verification_status="verified",
            has_publications=True,
            has_projects=True,
        )
        pub = Publication(id=323, openalex_id="W323", doi="10.1000/323", title="Cryptography Paper", verification_status="verified")
        link = ProfessorPublication(id=500, professor_id=27, publication_id=323, confidence_score=0.95, verification_status="verified")
        proj = ResearchProject(
            id=1254,
            title="Clean Title",
            original_title="Original Title",
            project_category="sponsored_research",
            sponsor="SERB",
        )
        pproj = ProfessorProject(id=900, professor_id=27, project_id=1254, role="Principal Investigator")

        # Self-referential topics where child has lower id than parent to test two-pass parent_topic_id migration
        child_topic = ResearchTopic(
            id=5,
            topic_name="NLP",
            canonical_topic_name="Natural Language Processing",
            domain_name="Computer Science & Artificial Intelligence",
            area_name="Natural Language Processing & Information Retrieval",
            parent_topic_id=50,
            is_generic_root=False,
            is_noisy_artifact=False,
        )
        parent_topic = ResearchTopic(
            id=50,
            topic_name="Natural language processing",
            canonical_topic_name="Natural Language Processing",
            domain_name="Computer Science & Artificial Intelligence",
            area_name="Natural Language Processing & Information Retrieval",
            parent_topic_id=None,
            is_generic_root=False,
            is_noisy_artifact=False,
        )
        p.topics.append(child_topic)
        pub.topics.append(parent_topic)
        vr = VerificationRecord(id=77, entity_type="professor_publication", entity_id=500, previous_status="pending", new_status="verified")

        db.add_all([u, d, p, pub, link, proj, pproj, parent_topic, child_topic, vr])
        db.commit()
        db.close()
        src_engine.dispose()

        result = migrate_database(src_url, tgt_url)
        assert result["status"] == "verified_identical"
        assert result["fingerprint"]["table_counts"]["professors"] == 1
        assert result["fingerprint"]["table_counts"]["research_topics"] == 2
        assert result["fingerprint"]["topics_with_parent_id"] == 1
        assert result["fingerprint"]["joined_professor_publications"] == 1
        assert result["fingerprint"]["joined_professor_projects"] == 1

        # Refuses to overwrite non-empty target
        with pytest.raises(RuntimeError):
            migrate_database(src_url, tgt_url)
