"""
Tests for public vs administrative publication visibility and the
verified-only meaning of Professor.has_publications.
"""
import tempfile
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.main import (
    get_professor_publications,
    get_professor_publications_for_review,
    get_professor,
)
from backend.api.schemas import ProfessorDetailSchema
from backend.database.models import (
    Base,
    Department,
    Professor,
    ProfessorPublication,
    Publication,
    University,
)
from verification.csv_import import CSVImporter


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    univ = University(name="IIT Kharagpur", country="India", city="Kharagpur")
    session.add(univ)
    session.commit()
    dept = Department(university_id=univ.id, name="Computer Science and Engineering", code="CS")
    session.add(dept)
    session.commit()

    prof = Professor(department_id=dept.id, name="Mixed Status Prof", verification_status="verified",
                     has_publications=True)
    candidate_only = Professor(department_id=dept.id, name="Candidate Only Prof", verification_status="verified",
                               has_publications=False)
    session.add_all([prof, candidate_only])
    session.commit()

    for i, status in enumerate(["verified", "pending", "needs_review", "rejected"], start=1):
        pub = Publication(openalex_id=f"W{i}", doi=f"10.1/{i}", title=f"Paper {status}",
                          verification_status=status, citation_count=0)
        session.add(pub)
        session.flush()
        session.add(ProfessorPublication(professor_id=prof.id, publication_id=pub.id,
                                         confidence_score=0.9, verification_status=status))

    pub_c = Publication(openalex_id="W99", doi="10.1/99", title="Candidate paper",
                        verification_status="pending", citation_count=0)
    session.add(pub_c)
    session.flush()
    session.add(ProfessorPublication(professor_id=candidate_only.id, publication_id=pub_c.id,
                                     confidence_score=0.9, verification_status="pending"))
    session.commit()
    yield session
    session.close()


def _statuses(links):
    return sorted(l.verification_status for l in links)


def test_default_returns_verified_only(db):
    links = get_professor_publications(professor_id=1, status=None, db=db)
    assert _statuses(links) == ["verified"]
    links_default = get_professor_publications(professor_id=1, status="verified", db=db)
    assert _statuses(links_default) == ["verified"]


def test_candidates_require_explicit_filter(db):
    assert _statuses(get_professor_publications(professor_id=1, status="pending", db=db)) == ["pending"]
    assert _statuses(get_professor_publications(professor_id=1, status="needs_review", db=db)) == ["needs_review"]
    # A professor with only candidate links has no publications by default
    assert get_professor_publications(professor_id=2, status=None, db=db) == []
    assert len(get_professor_publications(professor_id=2, status="pending", db=db)) == 1


def test_rejected_restricted_to_admin(db):
    with pytest.raises(HTTPException) as exc:
        get_professor_publications(professor_id=1, status="rejected", db=db)
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        get_professor_publications(professor_id=1, status="bogus", db=db)
    assert exc.value.status_code == 422

    admin_rejected = get_professor_publications_for_review(professor_id=1, status="rejected", db=db)
    assert _statuses(admin_rejected) == ["rejected"]
    admin_all = get_professor_publications_for_review(professor_id=1, status=None, db=db)
    assert len(admin_all) == 4


def test_has_publications_means_verified_only(db):
    prof = get_professor(professor_id=1, db=db)
    detail = ProfessorDetailSchema.model_validate(prof)
    assert detail.has_publications is True
    assert detail.verified_publication_count == 1
    assert detail.pending_publication_count == 1
    assert detail.needs_review_publication_count == 1
    assert detail.candidate_publication_count == 2

    cand = ProfessorDetailSchema.model_validate(get_professor(professor_id=2, db=db))
    assert cand.has_publications is False
    assert cand.verified_publication_count == 0
    assert cand.candidate_publication_count == 1


def test_csv_review_recomputes_has_publications(db):
    # Rejecting the only verified link must clear has_publications
    verified_link = db.query(ProfessorPublication).filter_by(professor_id=1, verification_status="verified").one()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "review.csv"
        pd.DataFrame([{"link_id": verified_link.id, "new_status": "rejected", "review_notes": "test"}]).to_csv(path, index=False)
        CSVImporter.import_reviewed_publications(db, path)
    assert db.get(Professor, 1).has_publications is False

    # Verifying a pending link sets it again
    pending_link = db.query(ProfessorPublication).filter_by(professor_id=2, verification_status="pending").one()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "review.csv"
        pd.DataFrame([{"link_id": pending_link.id, "new_status": "verified", "review_notes": "test"}]).to_csv(path, index=False)
        CSVImporter.import_reviewed_publications(db, path)
    assert db.get(Professor, 2).has_publications is True
