import pytest
import tempfile
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database.models import (
    Base,
    University,
    Department,
    Professor,
    Publication,
    ProfessorPublication,
    VerificationRecord,
    VerificationStatus
)
from verification.csv_export import CSVExporter
from verification.csv_import import CSVImporter
from data_collection.faculty_scraper import FacultyScraper
from backend.services.reporting_service import ReportingService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
    session.add(univ)
    session.commit()

    dept = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS", academic_unit="Engineering Divisions")
    session.add(dept)
    session.commit()

    prof = Professor(
        department_id=dept.id,
        name="Candidate One",
        email="cand1@iitkgp.ac.in",
        profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-cand1",
        verification_status="pending"
    )
    session.add(prof)
    session.commit()

    pub = Publication(
        openalex_id="https://openalex.org/W555",
        doi="10.1145/555",
        title="Test Publication",
        publication_year=2024,
        journal_or_conference="IEEE TKDE",
        authors_list="Candidate One, Coauthor Two",
        verification_status="pending"
    )
    session.add(pub)
    session.commit()

    link = ProfessorPublication(
        professor_id=prof.id,
        publication_id=pub.id,
        author_position="first",
        affiliation_evidence="Matched IIT Kharagpur",
        confidence_score=0.90,
        verification_status="pending"
    )
    session.add(link)
    session.commit()

    yield session
    session.close()


def test_csv_export_and_import_cycle_with_audit_records(db_session):
    with tempfile.TemporaryDirectory() as tmpdir:
        exporter = CSVExporter(export_dir=tmpdir)
        importer = CSVImporter()

        # 1. Faculty Export & Import
        export_file = exporter.export_faculty_candidates(db_session, filename="test_faculty.csv")
        assert export_file.exists()

        df = pd.read_csv(export_file)
        assert len(df) == 1
        assert df.iloc[0]["current_status"] == "pending"
        df.loc[0, "new_status"] = "verified"
        reviewed_csv = Path(tmpdir) / "test_faculty_reviewed.csv"
        df.to_csv(reviewed_csv, index=False)

        stats = importer.import_reviewed_faculty(db_session, reviewed_csv)
        assert stats["updated"] == 1

        prof = db_session.query(Professor).first()
        assert prof.verification_status == "verified"

        # 2. Publication Export & Import
        pub_export_file = exporter.export_publication_candidates(db_session, filename="test_pubs.csv")
        assert pub_export_file.exists()

        pub_df = pd.read_csv(pub_export_file)
        assert len(pub_df) == 1
        pub_df.loc[0, "new_status"] = "verified"
        reviewed_pub_csv = Path(tmpdir) / "test_pubs_reviewed.csv"
        pub_df.to_csv(reviewed_pub_csv, index=False)

        pub_stats = importer.import_reviewed_publications(db_session, reviewed_pub_csv)
        assert pub_stats["updated"] == 1

        link = db_session.query(ProfessorPublication).first()
        assert link.verification_status == "verified"
        assert prof.has_publications is True

        # Confirm VerificationRecord audit entries created
        audit_count = db_session.query(VerificationRecord).count()
        assert audit_count == 2


def test_idempotency_of_professor_upsert_and_reporting(db_session):
    dept = db_session.query(Department).first()
    scraper = FacultyScraper()

    cand = {
        "name": "Unique Professor",
        "designation": "Associate Professor",
        "appointment_category": "Regular Faculty",
        "educational_background": "Ph.D.",
        "email": "unique@cse.iitkgp.ac.in",
        "profile_url": "https://www.iitkgp.ac.in/department/CS/faculty/cs-unique",
        "source_url": "https://www.iitkgp.ac.in/department/CS",
        "topics": ["Machine Learning"],
        "projects": [{"title": "Sponsored Project A", "role": "Principal Investigator", "status": "current"}]
    }

    # First upsert -> newly added
    p1, is_new1 = scraper.upsert_professor_candidate(db_session, dept, cand)
    db_session.commit()
    assert is_new1 is True
    count_after_first = db_session.query(Professor).count()

    # Second upsert of same candidate -> updated in place, no duplicate created
    p2, is_new2 = scraper.upsert_professor_candidate(db_session, dept, cand)
    db_session.commit()
    assert is_new2 is False
    assert p1.id == p2.id
    assert db_session.query(Professor).count() == count_after_first

    with tempfile.TemporaryDirectory() as tmpdir:
        reporter = ReportingService(processed_dir=tmpdir)
        summary = reporter.generate_all_reports(db_session)
        assert summary["faculty"]["total_candidates_collected"] == count_after_first
        assert (Path(tmpdir) / "collection_summary_report.json").exists()
        assert (Path(tmpdir) / "department_coverage_report.csv").exists()
        assert (Path(tmpdir) / "faculty_coverage_report.csv").exists()
        assert (Path(tmpdir) / "publication_coverage_report.csv").exists()
