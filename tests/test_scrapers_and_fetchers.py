import pytest
from unittest.mock import patch, MagicMock
from data_collection.department_scraper import DepartmentScraper
from data_collection.faculty_scraper import FacultyScraper
from data_collection.openalex_client import OpenAlexClient
from data_collection.crossref_client import CrossrefClient


MOCK_ACADEMICS_HTML = """
<html>
<body>
    <h3>Engineering Divisions</h3>
    <a href="/department/CS">Computer Science and Engineering</a>
    <a href="/department/AI">Artificial Intelligence</a>
    <a href="/department/EE">Electrical Engineering</a>
    <a href="/department/SH">Departmental Webpage</a>
</body>
</html>
"""

MOCK_AJAX_DIRECTORY_HTML = """
<div class="col-md-3">
    <a href="/department/CS/faculty/cs-abhij">
        <span class="hndg">Abhijit Das</span>
        <span class="tx22">Ph.D., IISc Bangalore</span>
        <span class="tx22"><i>Professor</i></span>
        <span class="tx22"><i class="fa fa-envelope"></i> abhij@cse.iitkgp.ac.in</span>
    </a>
</div>
"""

MOCK_FACULTY_HTML = """
<html>
<body>
    <h1>Computer Science and Engineering</h1>
    <h1>Niloy Ganguly</h1>
    <p>Professor</p>
    <p>Ph.D.</p>
    <p>niloy@cse.iitkgp.ac.in</p>
    <div id="research_statement">Research in Graph Neural Networks, NLP and Responsible AI.</div>
    <p>Bio Sketch: Dr. Niloy Ganguly is a Professor in Computer Science.</p>
    <h2>Research Areas</h2>
    <ul>
        <li>Machine Learning</li>
        <li>Natural Language Processing</li>
    </ul>
    <p>Area of Research: Privacy and Health Analytics, Social Computing</p>
    <div id="compleated_project">
        <h4>Principal Investigator</h4>
        <ul>
            <li>Trustworthy AI for Social Good</li>
        </ul>
    </div>
    <div id="current_projects">
        <h4>Co-Principal Investigator</h4>
        <ul>
            <li>Federated Graph Learning at Scale. <b>Ministry of Electronics and Information Technology</b></li>
        </ul>
    </div>
    <div id="group_members">
        <p>Area of Research: Student Only Topic Should Be Ignored</p>
    </div>
</body>
</html>
"""

MOCK_BROKEN_PROFILE_HTML = """
<html>
<body>
    <h1>Centre for Computational and Data Sciences</h1>
    <h2>Data not found.</h2>
</body>
</html>
"""


def test_department_scraper_parsing():
    scraper = DepartmentScraper()
    parsed = scraper.parse_departments(MOCK_ACADEMICS_HTML)
    assert len(parsed) == 3
    codes = [d["code"] for d in parsed]
    assert "CS" in codes
    assert "AI" in codes
    assert "EE" in codes
    assert "SH" not in codes


def test_directory_cards_parsing():
    scraper = FacultyScraper()
    cards = scraper.parse_directory_cards(MOCK_AJAX_DIRECTORY_HTML, dept_code="CS", category="faculty")
    assert len(cards) == 1
    assert cards[0]["name"] == "Abhijit Das"
    assert cards[0]["designation"] == "Professor"
    assert cards[0]["educational_background"] == "Ph.D., IISc Bangalore"
    assert cards[0]["email"] == "abhij@cse.iitkgp.ac.in"
    assert cards[0]["profile_url"] == "https://www.iitkgp.ac.in/department/CS/faculty/cs-abhij"


def test_faculty_profile_parsing_and_broken_page_rejection():
    scraper = FacultyScraper()
    parsed = scraper.parse_faculty_profile(
        url="https://www.iitkgp.ac.in/department/CS/faculty/cs-niloy",
        html=MOCK_FACULTY_HTML
    )

    assert parsed is not None
    assert parsed["name"] == "Niloy Ganguly"
    assert parsed["designation"] == "Professor"
    assert parsed["email"] == "niloy@cse.iitkgp.ac.in"
    assert "Machine Learning" in parsed["topics"]
    assert "Natural Language Processing" in parsed["topics"]
    assert "Social Computing" in parsed["topics"]
    assert "Student Only Topic Should Be Ignored" not in parsed["topics"]
    assert "Graph Neural Networks" in parsed["biography"]
    assert len(parsed["projects"]) == 2
    assert parsed["projects"][0]["title"] == "Federated Graph Learning at Scale"
    assert parsed["projects"][0]["description"] == "Sponsor: Ministry of Electronics and Information Technology"
    assert parsed["projects"][0]["role"] == "Co-Principal Investigator"
    assert parsed["projects"][1]["title"] == "Trustworthy AI for Social Good"
    assert parsed["projects"][1]["role"] == "Principal Investigator"

    # Broken profile returning "Data not found." must return None
    broken = scraper.parse_faculty_profile(
        url="https://www.iitkgp.ac.in/department/CD/faculty/cd-devraj",
        html=MOCK_BROKEN_PROFILE_HTML
    )
    assert broken is None


@patch("requests.get")
def test_openalex_client_search_and_works(mock_get):
    client = OpenAlexClient()

    mock_auth_resp = MagicMock()
    mock_auth_resp.status_code = 200
    mock_auth_resp.json.return_value = {
        "results": [
            {
                "id": "https://openalex.org/A5073812421",
                "display_name": "Niloy Ganguly",
                "works_count": 400,
                "cited_by_count": 5000,
                "orcid": "https://orcid.org/0000-0002-3967-186X",
                "last_known_institutions": [
                    {"display_name": "Indian Institute of Technology Kharagpur"}
                ]
            }
        ]
    }

    mock_get.return_value = mock_auth_resp
    authors = client.search_authors_by_name("Niloy Ganguly")
    assert len(authors) == 1
    assert authors[0]["display_name"] == "Niloy Ganguly"
    assert "Indian Institute of Technology Kharagpur" in authors[0]["institutions"]

    mock_works_resp = MagicMock()
    mock_works_resp.status_code = 200
    mock_works_resp.json.return_value = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "doi": "https://doi.org/10.1145/123",
                "title": "Causal Graph Reasoning",
                "publication_year": 2024,
                "cited_by_count": 10,
                "primary_location": {
                    "landing_page_url": "https://doi.org/10.1145/123",
                    "source": {"display_name": "Proceedings of ACM KDD"}
                },
                "abstract_inverted_index": {"Causal": [0], "reasoning": [1], "graph": [2]},
                "concepts": [{"display_name": "Computer science"}],
                "authorships": [
                    {
                        "author": {"id": "https://openalex.org/A5073812421", "display_name": "Niloy Ganguly"},
                        "author_position": "last"
                    }
                ]
            }
        ]
    }
    mock_get.return_value = mock_works_resp
    works = client.get_works_by_author("A5073812421")
    assert len(works) == 1
    assert works[0]["title"] == "Causal Graph Reasoning"
    assert works[0]["abstract"] == "Causal reasoning graph"
    assert works[0]["author_position"] == "last"
    assert works[0]["journal_or_conference"] == "Proceedings of ACM KDD"
    assert works[0]["authors_list"] == "Niloy Ganguly"


@patch("requests.get")
def test_crossref_client_lookup(mock_get):
    client = CrossrefClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "title": ["Causal Models in AI"],
            "created": {"date-parts": [[2023, 5, 12]]},
            "author": [
                {"given": "Niloy", "family": "Ganguly", "affiliation": [{"name": "IIT Kharagpur"}]}
            ]
        }
    }
    mock_get.return_value = mock_resp

    data = client.get_work_by_doi("10.1145/1234567")
    assert data is not None
    assert data["title"] == "Causal Models in AI"
    assert data["publication_year"] == 2023
    assert len(data["authors"]) == 1
    assert data["authors"][0]["name"] == "Niloy Ganguly"


@patch("requests.get")
def test_crossref_search_works_by_author(mock_get):
    client = CrossrefClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "message": {
            "items": [
                {
                    "DOI": "10.1109/TKDE.2025.9999",
                    "title": ["Deep Graph Representation Learning"],
                    "abstract": "<jats:p>Abstract: We propose a novel GNN architecture.</jats:p>",
                    "published-print": {"date-parts": [[2025, 1, 15]]},
                    "container-title": ["IEEE Transactions on Knowledge and Data Engineering"],
                    "is-referenced-by-count": 12,
                    "subject": ["Artificial Intelligence", "Data Mining"],
                    "author": [
                        {
                            "given": "Sudeshna",
                            "family": "Sarkar",
                            "ORCID": "https://orcid.org/0000-0001-2345-6789",
                            "affiliation": [{"name": "Department of Computer Science and Engineering, Indian Institute of Technology Kharagpur"}]
                        }
                    ]
                }
            ]
        }
    }
    mock_get.return_value = mock_resp

    works = client.search_works_by_author("Sudeshna Sarkar")
    assert works is not None
    assert len(works) == 1
    assert works[0]["doi"] == "10.1109/tkde.2025.9999"
    assert works[0]["abstract"] == "We propose a novel GNN architecture."
    assert works[0]["publication_year"] == 2025
    assert works[0]["authorships"][0]["author_position"] == "first"
    assert works[0]["authorships"][0]["author"]["orcid"] == "https://orcid.org/0000-0001-2345-6789"
