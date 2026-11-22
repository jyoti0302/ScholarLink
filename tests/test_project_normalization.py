from data_processing.project_normalization import (
    BASE_ACRONYMS,
    CATEGORY_ADMIN,
    CATEGORY_CONSULTANCY,
    CATEGORY_ROUTINE,
    CATEGORY_SPONSORED,
    classify_project,
    fix_missing_spaces,
    is_convertible_all_caps,
    smart_title_case,
)


def test_fix_missing_spaces_and_hyphens():
    assert (
        fix_missing_spaces("Investigation Of Biomolecular CondensateFormation By HOX And TheirRole In Leukemia")
        == "Investigation Of Biomolecular Condensate Formation By HOX And Their Role In Leukemia"
    )
    assert (
        fix_missing_spaces("HIT-TB: Host Targeted Immunomodulatory Therapy forTuberculosis using DrugLoaded Nanocapsules")
        == "HIT-TB: Host Targeted Immunomodulatory Therapy for Tuberculosis using Drug Loaded Nanocapsules"
    )
    assert (
        fix_missing_spaces("Fabrication of a Wash-Free Electrochemical Lab-ona-Chip")
        == "Fabrication of a Wash-Free Electrochemical Lab-on-a-Chip"
    )


def test_smart_title_case_preserves_acronyms():
    raw = "DEVELOPMENT OF AUTONOMOUS UAV AND CFD SIMULATION FOR DRDO AND ISRO"
    assert is_convertible_all_caps(raw) is True
    converted = smart_title_case(raw, BASE_ACRONYMS)
    assert converted == "Development of Autonomous UAV and CFD Simulation for DRDO and ISRO"
    assert is_convertible_all_caps("TRAVEL GRANT") is False


def test_classify_project_categories():
    assert classify_project("TRAVEL GRANT") == CATEGORY_ADMIN
    assert classify_project("ICMR_ATTEND") == CATEGORY_ADMIN
    assert classify_project("Proof Checking of Documents for BHEL Udangudi Project") == CATEGORY_ROUTINE
    assert classify_project("Vetting of Design and Drawing of Intake Well") == CATEGORY_ROUTINE
    assert classify_project("Preparation of Detailed Project Report on Fecal Sludge Management") == CATEGORY_CONSULTANCY
    assert classify_project("Design consultancy for G+3 residential development at Bhubaneswar") == CATEGORY_CONSULTANCY
    assert classify_project("Development and Testing of a Large Scale Conceptual Hydrological Model") == CATEGORY_SPONSORED
