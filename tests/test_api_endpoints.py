import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    University,
    Department,
    Professor,
    Publication,
    ProfessorPublication,
    ResearchTopic
)
from backend.api.main import (
    list_universities,
    list_university_departments,
    list_department_professors,
    list_professors,
    get_professor,
    get_professor_publications,
    get_publication,
    get_faculty_for_review,
    get_publications_for_review,
    health_check
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
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
        name="Niloy Ganguly",
        designation="Professor",
        email="niloy@cse.iitkgp.ac.in",
        has_publications=True,
        verification_status="verified"
    )
    db.add(prof)

    prof_no_pubs = Professor(
        department_id=dept.id,
        name="Candidate Prof No Pubs",
        designation="Assistant Professor",
        email="candidate@cse.iitkgp.ac.in",
        has_publications=False,
        verification_status="pending"
    )
    db.add(prof_no_pubs)
    db.commit()

    pub = Publication(
        openalex_id="W100",
        doi="10.1145/999",
        title="Graph Neural Networks Overview",
        publication_year=2023,
        journal_or_conference="ACM Computing Surveys",
        authors_list="Niloy Ganguly",
        citation_count=50,
        verification_status="verified"
    )
    db.add(pub)
    db.commit()

    link = ProfessorPublication(
        professor_id=prof.id,
        publication_id=pub.id,
        author_position="last",
        affiliation_evidence="IIT Kharagpur verified affiliation",
        confidence_score=0.95,
        verification_status="verified"
    )
    db.add(link)
    db.commit()

    yield db

    db.close()
    Base.metadata.drop_all(bind=engine)


def test_health_check():
    res = health_check()
    assert res["status"] == "online"
    assert "Kharagpur" in res["institution"]


def test_list_universities(test_db):
    univs = list_universities(country=None, db=test_db)
    assert len(univs) == 1
    assert univs[0].name == "IIT Kharagpur"

    india_univs = list_universities(country="India", db=test_db)
    assert len(india_univs) == 1
    none_univs = list_universities(country="USA", db=test_db)
    assert len(none_univs) == 0


def test_list_university_departments(test_db):
    depts = list_university_departments(university_id=1, db=test_db)
    assert len(depts) == 1
    assert depts[0].code == "CS"

    with pytest.raises(HTTPException) as exc:
        list_university_departments(university_id=999, db=test_db)
    assert exc.value.status_code == 404


def test_list_department_professors(test_db):
    profs = list_department_professors(department_id=1, status=None, has_publications=None, db=test_db)
    assert len(profs) == 2

    verified_only = list_department_professors(department_id=1, status="verified", has_publications=None, db=test_db)
    assert len(verified_only) == 1
    assert verified_only[0].name == "Niloy Ganguly"

    zero_pubs_only = list_department_professors(department_id=1, status=None, has_publications=False, db=test_db)
    assert len(zero_pubs_only) == 1
    assert zero_pubs_only[0].name == "Candidate Prof No Pubs"


def test_list_and_get_professors(test_db):
    all_profs = list_professors(department_id=None, status=None, has_publications=None, search=None, page=1, page_size=10, db=test_db)
    assert len(all_profs) == 2

    with_pubs = list_professors(department_id=None, status=None, has_publications=True, search=None, page=1, page_size=10, db=test_db)
    assert len(with_pubs) == 1
    assert with_pubs[0].name == "Niloy Ganguly"

    without_pubs = list_professors(department_id=None, status=None, has_publications=False, search=None, page=1, page_size=10, db=test_db)
    assert len(without_pubs) == 1
    assert without_pubs[0].name == "Candidate Prof No Pubs"

    search_profs = list_professors(department_id=None, status=None, has_publications=None, search="Niloy", page=1, page_size=10, db=test_db)
    assert len(search_profs) == 1
    assert search_profs[0].name == "Niloy Ganguly"

    prof_detail = get_professor(professor_id=1, db=test_db)
    assert prof_detail.name == "Niloy Ganguly"
    assert prof_detail.email == "niloy@cse.iitkgp.ac.in"

    with pytest.raises(HTTPException) as exc:
        get_professor(professor_id=999, db=test_db)
    assert exc.value.status_code == 404


def test_get_professor_publications_with_and_without_pubs(test_db):
    pubs = get_professor_publications(professor_id=1, status=None, db=test_db)
    assert len(pubs) == 1
    assert pubs[0].publication.title == "Graph Neural Networks Overview"

    # Professor with zero publications returns empty list [] cleanly
    empty_pubs = get_professor_publications(professor_id=2, status=None, db=test_db)
    assert empty_pubs == []

    with pytest.raises(HTTPException) as exc:
        get_professor_publications(professor_id=999, status=None, db=test_db)
    assert exc.value.status_code == 404


def test_get_publication(test_db):
    pub = get_publication(publication_id=1, db=test_db)
    assert pub.doi == "10.1145/999"
    assert pub.publication_year == 2023
    assert pub.journal_or_conference == "ACM Computing Surveys"

    with pytest.raises(HTTPException) as exc:
        get_publication(publication_id=999, db=test_db)
    assert exc.value.status_code == 404


def test_admin_review_endpoints(test_db):
    pending_fac = get_faculty_for_review(status="pending", page=1, page_size=50, db=test_db)
    assert len(pending_fac) == 1
    assert pending_fac[0].name == "Candidate Prof No Pubs"

    verified_fac = get_faculty_for_review(status="verified", page=1, page_size=50, db=test_db)
    assert len(verified_fac) == 1
    assert verified_fac[0].name == "Niloy Ganguly"

    pending_pubs = get_publications_for_review(status="pending", page=1, page_size=50, db=test_db)
    assert len(pending_pubs) == 0

    verified_pubs = get_publications_for_review(status="verified", page=1, page_size=50, db=test_db)
    assert len(verified_pubs) == 1
