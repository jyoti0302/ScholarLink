from pathlib import Path
from types import SimpleNamespace

from backend.api.professor_contact import (
    build_professor_contact_info,
    parse_cached_faculty_html_contact,
)


def test_parse_cached_faculty_html_extracts_verified_fields():
    sample_html = """
    <div class="con_bk">
      <h1 class="hndg">Abhijit Das</h1>
      <p class="tx01"><i class="far fa-phone-alt"></i> +91-3222-282350 </p>
      <p class="tx01"><i class="far fa-envelope"></i><a href="mailto:abhij@cse.iitkgp.ac.in">abhij@cse.iitkgp.ac.in</a></p>
    </div>
    <div class="ps_right">
      <a href="http://cse.iitkgp.ac.in/~abhij/" target="_BLANK"><i class="fal fa-globe"></i> Personal Webpage</a>
      <a href="https://www.iitkgp.ac.in/assets/bio_sketch/MDIwMzk=.pdf" target="_BLANK"><i class="far fa-file-download"></i> Bio Sketch</a>
    </div>
    """
    parsed = parse_cached_faculty_html_contact(sample_html)
    assert parsed["office_phone"] == "+91-3222-282350"
    assert parsed["personal_webpage"] == "http://cse.iitkgp.ac.in/~abhij/"
    assert parsed["bio_sketch_url"] == "https://www.iitkgp.ac.in/assets/bio_sketch/MDIwMzk=.pdf"


def test_parse_cached_faculty_html_rejects_placeholders_and_invalid_links():
    sample_html = """
    <div class="con_bk">
      <p class="tx01"><i class="far fa-phone-alt"></i> 0000000 </p>
    </div>
    <div class="ps_right">
      <a href="#" target="_BLANK">Personal Webpage</a>
      <a href="javascript:void(0)" target="_BLANK">Bio Sketch</a>
    </div>
    """
    parsed = parse_cached_faculty_html_contact(sample_html)
    assert parsed["office_phone"] is None
    assert parsed["personal_webpage"] is None
    assert parsed["bio_sketch_url"] is None


def test_build_professor_contact_info_reuses_db_and_cached_html_without_fabrication(tmp_path: Path):
    html_file = tmp_path / "www_iitkgp_ac_in_department_CS_faculty_cs-sample.html"
    html_file.write_text(
        """
        <div class="con_bk">
          <p class="tx01"><i class="far fa-phone-alt"></i> +91-3222-283460</p>
        </div>
        <div class="ps_right">
          <a href="https://cse.iitkgp.ac.in/~sample/">Personal Webpage</a>
        </div>
        """,
        encoding="utf-8",
    )

    prof = SimpleNamespace(
        email="sample@cse.iitkgp.ac.in",
        research_group="https://cnerg-iitkgp.github.io/",
        profile_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-sample",
        source_url="https://www.iitkgp.ac.in/department/CS/faculty/cs-sample",
        orcid="0000-0001-2345-6789",
        irins_id="123456",
        openalex_author_id="A123456789",
    )
    dept = SimpleNamespace(
        name="Computer Science and Engineering",
        official_url="https://www.iitkgp.ac.in/department/CS",
    )
    univ = SimpleNamespace(
        name="Indian Institute of Technology Kharagpur",
        city="Kharagpur",
        country="India",
    )

    contact = build_professor_contact_info(prof, dept, univ, profiles_dir=tmp_path)
    assert contact.email == "sample@cse.iitkgp.ac.in"
    assert contact.office_phone == "+91-3222-283460"
    assert contact.office_room is None  # Never fabricated
    assert contact.department_address == "Computer Science and Engineering, Indian Institute of Technology Kharagpur, India"
    assert contact.department_url == "https://www.iitkgp.ac.in/department/CS"
    assert contact.research_group_website == "https://cnerg-iitkgp.github.io/"
    assert contact.personal_webpage == "https://cse.iitkgp.ac.in/~sample/"
    assert contact.source_url == "https://www.iitkgp.ac.in/department/CS/faculty/cs-sample"
    link_labels = [l.label for l in contact.academic_links]
    assert "Personal Webpage" in link_labels
    assert "ORCID Profile" in link_labels
    assert "IRINS Profile" in link_labels
    assert "OpenAlex Author Profile" in link_labels


def test_build_professor_contact_info_handles_no_contact_gracefully(tmp_path: Path):
    prof = SimpleNamespace(
        email=None,
        research_group=None,
        profile_url=None,
        source_url=None,
        orcid=None,
        irins_id=None,
        openalex_author_id=None,
    )
    contact = build_professor_contact_info(prof, None, None, profiles_dir=tmp_path)
    assert contact.email is None
    assert contact.office_phone is None
    assert contact.office_room is None
    assert contact.department_address is None
    assert contact.department_url is None
    assert contact.research_group_website is None
    assert contact.academic_links == []
