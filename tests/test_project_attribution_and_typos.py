from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    Department,
    EvidenceType,
    Professor,
    ProfessorProject,
    ResearchProject,
    University,
)
from backend.search.document_builder import (
    DocumentBuilder,
    normalize_known_research_typos,
    resolve_project_source_url,
)
from backend.search.query_understanding import QueryUnderstandingService
from data_collection.faculty_scraper import (
    FacultyScraper,
    is_generic_project_title,
)


def _make_memory_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, Session()


def test_resolve_project_source_url_and_document_builder_attribution():
    assert (
        resolve_project_source_url(
            "https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy",
            "https://www.iitkgp.ac.in/department/CS/faculty/cs-saptarshi",
        )
        == "https://www.iitkgp.ac.in/department/CS/faculty/cs-saptarshi"
    )
    assert (
        resolve_project_source_url(
            "https://serb.gov.in/grants/dst-1234",
            "https://www.iitkgp.ac.in/department/CS/faculty/cs-saptarshi",
        )
        == "https://serb.gov.in/grants/dst-1234"
    )
    assert (
        resolve_project_source_url(
            None,
            "https://www.iitkgp.ac.in/department/AT/faculty/at-sdasmandal",
        )
        == "https://www.iitkgp.ac.in/department/AT/faculty/at-sdasmandal"
    )

    engine, db = _make_memory_session()
    try:
        univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
        db.add(univ)
        db.flush()
        dept_cs = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS")
        dept_at = Department(university_id=univ.id, name="Centre for Interdisciplinary", code="AT")
        db.add_all([dept_cs, dept_at])
        db.flush()

        p_niloy = Professor(
            department_id=dept_cs.id,
            name="Niloy Ganguly",
            profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy",
            verification_status="verified",
        )
        p_saptarshi = Professor(
            department_id=dept_cs.id,
            name="Saptarshi Ghosh",
            profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-saptarshi",
            verification_status="verified",
        )
        p_shyamal = Professor(
            department_id=dept_at.id,
            name="Shyamal Kumar Das Mandal",
            profile_url="https://www.iitkgp.ac.in/department/AT/faculty/at-sdasmandal",
            verification_status="verified",
        )
        db.add_all([p_niloy, p_saptarshi, p_shyamal])
        db.flush()

        shared_proj = ResearchProject(
            title="Responsible AI for Decentralized Online Platforms",
            source_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy",
        )
        external_url_proj = ResearchProject(
            title="DST National Speech Corpus Initiative",
            source_url="https://dst.gov.in/projects/speech-corpus",
        )
        missing_url_proj = ResearchProject(
            title="Bengali TTS Acoustic Modeling",
            source_url=None,
        )
        db.add_all([shared_proj, external_url_proj, missing_url_proj])
        db.flush()

        db.add_all([
            ProfessorProject(professor_id=p_niloy.id, project_id=shared_proj.id, role="Principal Investigator"),
            ProfessorProject(professor_id=p_saptarshi.id, project_id=shared_proj.id, role="Co-Principal Investigator"),
            ProfessorProject(professor_id=p_shyamal.id, project_id=external_url_proj.id, role="Principal Investigator"),
            ProfessorProject(professor_id=p_shyamal.id, project_id=missing_url_proj.id, role="Principal Investigator"),
        ])
        db.commit()

        docs = DocumentBuilder().build_candidate_documents(db)
        proj_docs = [d for d in docs if d["evidence_type"] == EvidenceType.RESEARCH_PROJECT.value]
        by_prof_title = {(d["professor_id"], d["title"]): d for d in proj_docs}

        # Collaboration preserved for both professors, each getting their own faculty profile URL
        assert by_prof_title[(p_niloy.id, "Responsible AI for Decentralized Online Platforms")]["source_url"] == p_niloy.profile_url
        assert by_prof_title[(p_saptarshi.id, "Responsible AI for Decentralized Online Platforms")]["source_url"] == p_saptarshi.profile_url
        # Valid project-specific URL preserved
        assert by_prof_title[(p_shyamal.id, "DST National Speech Corpus Initiative")]["source_url"] == "https://dst.gov.in/projects/speech-corpus"
        # Missing URL falls back to professor's own profile URL
        assert by_prof_title[(p_shyamal.id, "Bengali TTS Acoustic Modeling")]["source_url"] == p_shyamal.profile_url
    finally:
        db.close()
        engine.dispose()


def test_generic_project_titles_not_globally_merged_while_collaborations_preserved():
    assert is_generic_project_title("FIST- PROJECT (Level-2)") is True
    assert is_generic_project_title("Travel Grant") is True
    assert is_generic_project_title("Responsible AI for Decentralized Online Platforms") is False

    engine, db = _make_memory_session()
    try:
        univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
        db.add(univ)
        db.flush()
        dept = Department(university_id=univ.id, name="CS", code="CS")
        db.add(dept)
        db.flush()

        scraper = FacultyScraper()
        scraper.upsert_professor_candidate(
            db,
            dept,
            {
                "name": "Prof A",
                "profile_url": "https://www.iitkgp.ac.in/department/CS/faculty/cs-a",
                "projects": [
                    {"title": "FIST- PROJECT (Level-2)", "role": "Principal Investigator", "description": "Sponsor: DST"},
                    {"title": "Responsible AI for Decentralized Online Platforms", "role": "Principal Investigator"},
                ],
            },
        )
        scraper.upsert_professor_candidate(
            db,
            dept,
            {
                "name": "Prof B",
                "profile_url": "https://www.iitkgp.ac.in/department/CS/faculty/cs-b",
                "projects": [
                    {"title": "FIST- PROJECT (Level-2)", "role": "Principal Investigator", "description": "Sponsor: DST"},
                    {"title": "Responsible AI for Decentralized Online Platforms", "role": "Co-Principal Investigator"},
                ],
            },
        )
        db.commit()

        fist_rows = db.query(ResearchProject).filter(ResearchProject.title == "FIST- PROJECT (Level-2)").all()
        collab_rows = db.query(ResearchProject).filter(
            ResearchProject.title == "Responsible AI for Decentralized Online Platforms"
        ).all()
        assert len(fist_rows) == 2
        assert len(collab_rows) == 1
        assert len(collab_rows[0].professor_projects) == 2

        stats = scraper.validate_and_clean_existing_projects(db)
        assert stats["duplicate_projects_merged"] == 0
        assert db.query(ResearchProject).filter(ResearchProject.title == "FIST- PROJECT (Level-2)").count() == 2
    finally:
        db.close()
        engine.dispose()


def test_known_research_interest_typo_normalization():
    assert (
        normalize_known_research_typos("Natural Language Pocessing, Information Retrieval")
        == "Natural Language Processing, Information Retrieval"
    )
    assert (
        normalize_known_research_typos("Computer Vision, Speech Processing")
        == "Computer Vision, Speech Processing"
    )

    qu = QueryUnderstandingService().understand("Natural Language Pocessing for Indian languages")
    assert qu.cleaned_query == "Natural Language Processing for Indian languages"

    engine, db = _make_memory_session()
    try:
        univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
        db.add(univ)
        db.flush()
        dept = Department(university_id=univ.id, name="CS", code="CS")
        db.add(dept)
        db.flush()
        prof = Professor(
            department_id=dept.id,
            name="Pawan Goyal",
            profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-pawang",
            research_interests="Natural Language Pocessing, Information Retrieval",
            verification_status="verified",
        )
        db.add(prof)
        db.commit()

        docs = DocumentBuilder().build_candidate_documents(db)
        ri_docs = [d for d in docs if d["evidence_type"] == EvidenceType.RESEARCH_INTEREST.value]
        assert len(ri_docs) == 1
        assert "Natural Language Processing" in ri_docs[0]["text_content"]
        assert "Pocessing" not in ri_docs[0]["text_content"]
        # Source PostgreSQL professor record remains unmodified
        db.refresh(prof)
        assert prof.research_interests == "Natural Language Pocessing, Information Retrieval"
    finally:
        db.close()
        engine.dispose()
