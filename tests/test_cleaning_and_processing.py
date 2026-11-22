import pytest
from data_processing.cleaning import (
    normalize_doi,
    clean_text,
    clean_author_name,
    normalize_email,
    normalize_url,
    normalize_department_name,
    clean_designation,
    infer_appointment_category,
    reconstruct_inverted_index
)
from data_processing.topic_extraction import (
    normalize_topic_name,
    extract_topics_from_text
)


def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1145/3340531.3412015") == "10.1145/3340531.3412015"
    assert normalize_doi("http://dx.doi.org/10.1016/j.patcog.2021.108253") == "10.1016/j.patcog.2021.108253"
    assert normalize_doi("  doi: 10.1109/TPAMI.2020.3001234  ") == "10.1109/tpami.2020.3001234"
    assert normalize_doi("10.1007/978-3-030-58580-8_1") == "10.1007/978-3-030-58580-8_1"
    assert normalize_doi("invalid_doi") is None
    assert normalize_doi(None) is None
    assert normalize_doi("") is None


def test_normalize_url_and_department():
    assert normalize_url("http://www.iitkgp.ac.in/department/CS/faculty/cs-niloy/") == "https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy"
    assert normalize_url("/department/AI/faculty/ai-somdyuti") == "https://www.iitkgp.ac.in/department/AI/faculty/ai-somdyuti"
    assert normalize_url("#") is None
    assert normalize_department_name("Computer Science & Engineering") == "Computer Science and Engineering"


def test_clean_text():
    assert clean_text("  Computer   Vision and   NLP \n") == "Computer Vision and NLP"
    assert clean_text("") is None
    assert clean_text(None) is None


def test_clean_author_name():
    assert clean_author_name("Prof. Niloy Ganguly") == "Niloy Ganguly"
    assert clean_author_name("Dr. Somdyuti Paul") == "Somdyuti Paul"
    assert clean_author_name("Prof. Dr. Cheruvu Siva Kumar") == "Cheruvu Siva Kumar"
    assert clean_author_name("Shri A. K. Banerjee") == "A. K. Banerjee"
    assert clean_author_name("  Pawan Goyal  ") == "Pawan Goyal"
    assert clean_author_name("") == ""
    assert clean_author_name(None) == ""


def test_normalize_email():
    assert normalize_email("Niloy@CSE.IITKGP.AC.IN") == "niloy@cse.iitkgp.ac.in"
    assert normalize_email("somdyuti [at] cai [dot] iitkgp.ac.in") == "somdyuti@cai.iitkgp.ac.in"
    assert normalize_email("invalid-email") is None
    assert normalize_email(None) is None


def test_clean_designation_and_appointment_category():
    assert clean_designation("Professor") == "Professor"
    assert clean_designation("Assistant Professor Grade-I") == "Assistant Professor Grade-I"
    assert clean_designation("Associate Professor in CSE") == "Associate Professor"
    assert clean_designation(None) is None
    assert infer_appointment_category("Professor") == "Regular Faculty"
    assert infer_appointment_category("Adjunct Professor", "adjunct_faculty") == "Adjunct Faculty"
    assert infer_appointment_category("Professor", "inspired_faculty") == "Inspire Faculty"


def test_reconstruct_inverted_index():
    inv_index = {
        "Deep": [0],
        "learning": [1],
        "models": [2],
        "for": [3],
        "code": [4],
        "generation.": [5]
    }
    reconstructed = reconstruct_inverted_index(inv_index)
    assert reconstructed == "Deep learning models for code generation."

    inv_scrambled = {
        "world": [1],
        "Hello": [0]
    }
    assert reconstruct_inverted_index(inv_scrambled) == "Hello world"
    assert reconstruct_inverted_index(None) is None
    assert reconstruct_inverted_index({}) is None
    assert reconstruct_inverted_index("not a dict") is None


def test_extract_topics_from_text():
    raw_topics = "Machine Learning, Computer Vision; Generative AI | Robotics\nNatural Language Processing"
    extracted = extract_topics_from_text(raw_topics)
    assert "Machine Learning" in extracted
    assert "Computer Vision" in extracted
    assert "Generative AI" in extracted
    assert "Robotics" in extracted
    assert "Natural Language Processing" in extracted
    assert extract_topics_from_text(None) == []
