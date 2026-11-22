import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    University,
    Department,
    Professor,
    Publication,
    ProfessorPublication,
    ResearchTopic,
    ResearchProject,
    ProfessorProject,
    DataSource,
    VerificationRecord,
    VerificationStatus
)
from data_processing.deduplication import (
    find_existing_professor,
    find_existing_publication
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_university_and_department_creation(db_session):
    univ = University(
        name="IIT Kharagpur",
        country="India",
        city="Kharagpur",
        website="https://www.iitkgp.ac.in/"
    )
    db_session.add(univ)
    db_session.commit()
    assert univ.id is not None

    dept = Department(
        university_id=univ.id,
        name="Computer Science and Engineering",
        code="CS",
        academic_unit="Engineering Divisions",
        official_url="https://www.iitkgp.ac.in/department/CS",
        collection_status="completed"
    )
    db_session.add(dept)
    db_session.commit()
    assert dept.id is not None
    assert dept.university.name == "IIT Kharagpur"
    assert dept.academic_unit == "Engineering Divisions"


def test_professor_insertion_missing_fields_and_zero_publications(db_session):
    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
    db_session.add(univ)
    db_session.commit()

    dept = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS")
    db_session.add(dept)
    db_session.commit()

    # Insert professor with missing optional fields and zero publications
    prof = Professor(
        department_id=dept.id,
        name="Niloy Ganguly",
        designation="Professor",
        appointment_category="Regular Faculty",
        email=None,
        biography=None,
        research_interests=None,
        educational_background=None,
        research_group=None,
        has_publications=False,
        has_research_interests=False,
        has_biography=False,
        has_projects=False,
        verification_status=VerificationStatus.PENDING.value
    )
    db_session.add(prof)
    db_session.commit()

    assert prof.id is not None
    assert prof.verification_status == "pending"
    assert prof.email is None
    assert prof.biography is None
    assert prof.research_interests is None
    assert prof.has_publications is False
    assert len(prof.professor_publications) == 0


def test_publication_author_project_and_verification_models(db_session):
    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
    db_session.add(univ)
    db_session.commit()

    dept = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS")
    db_session.add(dept)
    db_session.commit()

    prof = Professor(department_id=dept.id, name="Niloy Ganguly", has_publications=True, has_projects=True)
    db_session.add(prof)
    db_session.commit()

    pub = Publication(
        openalex_id="https://openalex.org/W12345",
        doi="10.1145/1234567.89",
        title="Scalable Graph Neural Networks for Recommender Systems",
        publication_year=2023,
        journal_or_conference="ACM KDD",
        authors_list="A. Author, Niloy Ganguly",
        citation_count=15,
        source_url="https://openalex.org/W12345"
    )
    db_session.add(pub)
    db_session.commit()

    link = ProfessorPublication(
        professor_id=prof.id,
        publication_id=pub.id,
        author_position="last",
        affiliation_evidence="IIT Kharagpur author affiliation confirmed",
        confidence_score=0.95,
        verification_status="verified"
    )
    db_session.add(link)

    project = ResearchProject(
        title="Trustworthy AI Systems",
        status="current",
        source_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy"
    )
    db_session.add(project)
    db_session.flush()

    prof_proj = ProfessorProject(
        professor_id=prof.id,
        project_id=project.id,
        role="Principal Investigator"
    )
    db_session.add(prof_proj)

    ver_rec = VerificationRecord(
        entity_type="professor",
        entity_id=prof.id,
        previous_status="pending",
        new_status="verified",
        verified_by="unit_test",
        evidence_or_notes="Confirmed institutional profile",
        source_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy"
    )
    db_session.add(ver_rec)
    db_session.commit()

    assert len(prof.professor_publications) == 1
    assert prof.professor_publications[0].publication.journal_or_conference == "ACM KDD"
    assert len(prof.professor_projects) == 1
    assert prof.professor_projects[0].project.title == "Trustworthy AI Systems"
    assert db_session.query(VerificationRecord).count() == 1


def test_duplicate_detection(db_session):
    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
    db_session.add(univ)
    db_session.commit()

    dept = Department(university_id=univ.id, name="Electrical Engineering", code="EE")
    db_session.add(dept)
    db_session.commit()

    prof1 = Professor(
        department_id=dept.id,
        name="A. Routray",
        email="aroutray@ee.iitkgp.ac.in",
        profile_url="https://www.iitkgp.ac.in/department/EE/faculty/ee-aroutray"
    )
    db_session.add(prof1)
    db_session.commit()

    # Find existing by profile_url
    found_url = find_existing_professor(
        db_session,
        department_id=dept.id,
        name="Aurobinda Routray",
        profile_url="http://www.iitkgp.ac.in/department/EE/faculty/ee-aroutray/"
    )
    assert found_url is not None
    assert found_url.id == prof1.id

    # Find existing by email
    found_email = find_existing_professor(
        db_session,
        department_id=dept.id,
        name="Prof A Routray",
        email="aroutray@ee.iitkgp.ac.in"
    )
    assert found_email is not None
    assert found_email.id == prof1.id

    # Find existing by department and clean name
    found_name = find_existing_professor(db_session, department_id=dept.id, name="A. Routray")
    assert found_name is not None

    pub1 = Publication(openalex_id="W999", doi="10.1016/j.test.2023.01", title="Sample Paper")
    db_session.add(pub1)
    db_session.commit()

    # Deduplicate publication by DOI
    found_pub = find_existing_publication(db_session, doi="https://doi.org/10.1016/j.test.2023.01")
    assert found_pub is not None
    assert found_pub.id == pub1.id

    # Deduplicate publication by OpenAlex ID
    found_by_oa = find_existing_publication(db_session, openalex_id="W999")
    assert found_by_oa is not None
