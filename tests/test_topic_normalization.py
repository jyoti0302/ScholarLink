from data_processing.topic_normalization import (
    build_plural_and_punct_canonical_map,
    normalize_single_topic,
)


def test_acronym_and_alias_normalization():
    pmap = build_plural_and_punct_canonical_map(["NLP", "Natural Language Processing", "IoT", "CFD"])
    assert normalize_single_topic("NLP", pmap)[0] == "Natural Language Processing"
    assert normalize_single_topic("IOT", pmap)[0] == "Internet of Things"
    assert normalize_single_topic("Internet of Things (IoT)", pmap)[0] == "Internet of Things"
    assert normalize_single_topic("CFD", pmap)[0] == "Computational Fluid Dynamics"
    assert normalize_single_topic("Computational Fluid Dynamics (CFD)", pmap)[0] == "Computational Fluid Dynamics"


def test_singular_plural_and_punctuation_normalization():
    topics = [
        "Biofuel",
        "Biofuels",
        "Biosensor",
        "Biosensors",
        "Decision-making",
        "Decision making",
        "Multi-objective optimization",
        "Multi–objective optimization",
        "- 6g",
        "6g",
        "structuress",
        "tansportation",
    ]
    pmap = build_plural_and_punct_canonical_map(topics)
    assert normalize_single_topic("Biofuel", pmap)[0] == normalize_single_topic("Biofuels", pmap)[0] == "Biofuels"
    assert normalize_single_topic("Biosensor", pmap)[0] == normalize_single_topic("Biosensors", pmap)[0] == "Biosensors"
    assert normalize_single_topic("Decision-making", pmap)[0] == normalize_single_topic("Decision making", pmap)[0] == "Decision Making"
    assert normalize_single_topic("- 6g", pmap)[0] == normalize_single_topic("6g", pmap)[0] == "6G Wireless Communications"
    assert normalize_single_topic("structuress", pmap)[0] == "Structures"
    assert normalize_single_topic("tansportation", pmap)[0] == "Transportation"


def test_generic_roots_and_noisy_artifacts_flagged_without_merging_ambiguous():
    pmap = build_plural_and_punct_canonical_map(["Computer science", "Object (grammar)", "Action (physics)", "Action"])
    _, _, _, is_gen, is_noisy = normalize_single_topic("Computer science", pmap)
    assert is_gen is True
    assert is_noisy is False

    can_obj, _, _, is_gen_obj, is_noisy_obj = normalize_single_topic("Object (grammar)", pmap)
    assert is_gen_obj is False
    assert is_noisy_obj is True
    # Ambiguous disambiguated topics must not be auto-merged into bare "Action"
    can_act_phys, _, _, _, _ = normalize_single_topic("Action (physics)", pmap)
    can_act, _, _, _, _ = normalize_single_topic("Action", pmap)
    assert can_act_phys != can_act
