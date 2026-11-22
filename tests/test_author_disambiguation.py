import pytest
from data_collection.author_disambiguation import AuthorDisambiguator


@pytest.fixture
def disambiguator():
    return AuthorDisambiguator(high_confidence_threshold=0.80, ambiguous_threshold=0.45)


def test_name_similarity(disambiguator):
    assert disambiguator.calculate_name_similarity("Niloy Ganguly", "Niloy Ganguly") == 1.0
    assert disambiguator.calculate_name_similarity("Prof. Niloy Ganguly", "Niloy Ganguly") == 1.0
    assert disambiguator.calculate_name_similarity("N. Ganguly", "Niloy Ganguly") >= 0.50
    assert disambiguator.calculate_name_similarity("Somdyuti Paul", "John Doe") == 0.0


def test_high_confidence_match(disambiguator):
    candidate = {
        "openalex_id": "https://openalex.org/A5073812421",
        "display_name": "Niloy Ganguly",
        "institutions": ["Indian Institute of Technology Kharagpur"],
        "orcid": "https://orcid.org/0000-0002-3967-186X",
        "summary_stats": {"top_concepts": ["Computer science", "Machine learning", "Social network"]}
    }

    score, status, evidence = disambiguator.match_author_candidate(
        professor_name="Niloy Ganguly",
        professor_topics=["Machine Learning", "Natural Language Processing"],
        candidate=candidate,
        known_orcid="0000-0002-3967-186X"
    )

    assert score >= 0.85
    assert status == "pending"
    assert "IIT Kharagpur" in evidence
    assert "Exact name match" in evidence


def test_ambiguous_author_flagged_needs_review(disambiguator):
    # Candidate with matching name but ambiguous/different institution
    candidate = {
        "openalex_id": "https://openalex.org/A1111111111",
        "display_name": "Abhishek Kumar",
        "institutions": ["University of Delhi"],
        "summary_stats": {"top_concepts": ["Mathematics", "Physics"]}
    }

    score, status, evidence = disambiguator.match_author_candidate(
        professor_name="Abhishek Kumar",
        professor_topics=["Computer Science"],
        candidate=candidate
    )

    # Lacks IIT Kharagpur affiliation so must not be auto-verified
    assert status in ["needs_review", "rejected"]
    assert score < 0.80


def test_rejected_author(disambiguator):
    candidate = {
        "openalex_id": "https://openalex.org/A2222222222",
        "display_name": "Alexander Hamilton",
        "institutions": ["Harvard University"]
    }

    score, status, evidence = disambiguator.match_author_candidate(
        professor_name="Pawan Goyal",
        professor_topics=["NLP"],
        candidate=candidate
    )

    assert score == 0.0
    assert status == "rejected"
