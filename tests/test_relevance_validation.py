from backend.database.models import EvidenceType
from backend.search.query_understanding import QueryExpansionService, QueryUnderstandingService
from backend.search.ranking import ProfessorAggregationService, ProfessorEvidenceBundle
from backend.search.relevance_validation import RelevanceValidationService
from backend.search.retrieval import RetrievedEvidenceItem


def _item(
    doc_id: str,
    prof_id: int,
    ev_type: str,
    title: str,
    snippet: str,
    orig_dense: float = 0.0,
    orig_sparse: float = 0.0,
    exp_dense: float = 0.0,
    exp_sparse: float = 0.0,
    rrf: float = 0.85,
    content_hash: str = "",
):
    return RetrievedEvidenceItem(
        document_id=doc_id,
        professor_id=prof_id,
        department_id=1,
        evidence_type=ev_type,
        score=rrf,
        rrf_rank=1,
        originating_query="q",
        query_kind="original" if orig_dense > 0 or orig_sparse > 0 else "subfield",
        query_weight=1.0,
        original_dense_score=orig_dense,
        original_sparse_score=orig_sparse,
        expanded_dense_score=exp_dense,
        expanded_sparse_score=exp_sparse,
        rrf_score=rrf,
        payload={
            "title": title,
            "text_snippet": snippet,
            "canonical_topics": [],
            "content_hash": content_hash or doc_id,
            "confidence_score": 0.9,
        },
    )


def test_q15_and_q16_positive_cases_remain_discoverable():
    val = RelevanceValidationService()

    # Q15 positive case: Generative AI for healthcare applications
    b_q15 = ProfessorEvidenceBundle(
        professor_id=1,
        department_id=1,
        items_by_type={
            EvidenceType.RESEARCH_INTEREST.value: [
                _item("d1", 1, EvidenceType.RESEARCH_INTEREST.value, "Research Interests", "Generative AI, Medical Imaging, Healthcare", orig_dense=0.635, orig_sparse=0.16)
            ],
            EvidenceType.RESEARCH_PROJECT.value: [
                _item("d2", 1, EvidenceType.RESEARCH_PROJECT.value, "Generative AI Models for Medical Imaging", "Sponsor: ICMR", orig_dense=0.62, orig_sparse=0.14)
            ],
        },
    )
    dec15 = val.validate_bundle("Generative AI for healthcare applications", b_q15)
    assert dec15.is_valid is True
    assert dec15.max_allowed_category == "strong"

    # Q16 positive case: Natural language processing for Indian languages
    b_q16 = ProfessorEvidenceBundle(
        professor_id=2,
        department_id=1,
        items_by_type={
            EvidenceType.RESEARCH_INTEREST.value: [
                _item("d3", 2, EvidenceType.RESEARCH_INTEREST.value, "Research Interests — Pawan Goyal", "Natural Language Processing, Indian Languages", orig_dense=0.631, orig_sparse=0.115)
            ],
            EvidenceType.CANDIDATE_PUBLICATION.value: [
                _item("d4", 2, EvidenceType.CANDIDATE_PUBLICATION.value, "Indian Language Machine Translation", "Neural MT for low-resource Indian languages", orig_dense=0.60, orig_sparse=0.10)
            ],
        },
    )
    dec16 = val.validate_bundle("Natural language processing for Indian languages", b_q16)
    assert dec16.is_valid is True
    assert dec16.max_allowed_category == "strong"


def test_q21_single_term_laser_combustion_false_positive_rejected():
    val = RelevanceValidationService()
    q21 = "3D printing and laser powder bed fusion of titanium alloys"

    # True positive: Materials professor with powder bed fusion / titanium alloys
    b_true = ProfessorEvidenceBundle(
        professor_id=10,
        department_id=2,
        items_by_type={
            EvidenceType.RESEARCH_PROJECT.value: [
                _item("m1", 10, EvidenceType.RESEARCH_PROJECT.value, "Development of high strength titanium alloys using additive manufacturing", "Powder bed fusion", orig_dense=0.66, orig_sparse=0.17)
            ]
        },
    )
    assert val.validate_bundle(q21, b_true).is_valid is True

    # False positive: Combustion professor matching ONLY the generic word "laser"
    b_false = ProfessorEvidenceBundle(
        professor_id=20,
        department_id=3,
        items_by_type={
            EvidenceType.VERIFIED_PUBLICATION.value: [
                _item("f1", 20, EvidenceType.VERIFIED_PUBLICATION.value, "LES of Laser Initiation of Combustion of Gaseous Fuel-Air Mixture", "Combustion ignition using laser spark.", orig_dense=0.555, orig_sparse=0.05)
            ]
        },
    )
    dec_false = val.validate_bundle(q21, b_false)
    assert dec_false.is_valid is False
    assert "single_term_overlap_below_concept_guard" in dec_false.reason_codes


def test_q33_out_of_scope_and_edge_cases():
    val = RelevanceValidationService()

    # Q33 out-of-scope: high RRF (0.85) but low raw original dense (0.49) & sparse (0.035)
    b_q33 = ProfessorEvidenceBundle(
        professor_id=30,
        department_id=4,
        items_by_type={
            EvidenceType.RESEARCH_INTEREST.value: [
                _item("o1", 30, EvidenceType.RESEARCH_INTEREST.value, "Research Interests", "Urban Transportation and Housing", orig_dense=0.49, orig_sparse=0.035, rrf=0.85)
            ]
        },
    )
    dec33 = val.validate_bundle("Medieval Byzantine numismatics and ecclesiastical iconography", b_q33)
    assert dec33.is_valid is False
    assert dec33.max_allowed_category == "insufficient"

    # Empty / department-only evidence -> invalid
    b_dept = ProfessorEvidenceBundle(
        professor_id=31,
        department_id=1,
        items_by_type={
            EvidenceType.DEPARTMENT_CONTEXT.value: [
                _item("dc1", 31, EvidenceType.DEPARTMENT_CONTEXT.value, "Dept of CS", "CS", orig_dense=0.70)
            ]
        },
    )
    assert val.validate_bundle("Machine Learning", b_dept).is_valid is False

    # Candidate-publication-only -> valid if original dense passes, but capped at 'limited'
    b_cand = ProfessorEvidenceBundle(
        professor_id=32,
        department_id=1,
        items_by_type={
            EvidenceType.CANDIDATE_PUBLICATION.value: [
                _item("cp1", 32, EvidenceType.CANDIDATE_PUBLICATION.value, "Machine Learning for Healthcare", "Medical ML", orig_dense=0.62, orig_sparse=0.14)
            ]
        },
    )
    dec_cand = val.validate_bundle("Machine Learning for Healthcare", b_cand)
    assert dec_cand.is_valid is True
    assert dec_cand.max_allowed_category == "limited"

    # Expanded-only match without original-query support -> invalid
    b_exp_only = ProfessorEvidenceBundle(
        professor_id=33,
        department_id=1,
        items_by_type={
            EvidenceType.RESEARCH_PROJECT.value: [
                _item("eo1", 33, EvidenceType.RESEARCH_PROJECT.value, "Expanded Match Only", "Subfield", orig_dense=0.45, orig_sparse=0.02, exp_dense=0.68)
            ]
        },
    )
    dec_exp = val.validate_bundle("Generative AI for healthcare", b_exp_only)
    assert dec_exp.is_valid is False
    assert "expanded_only_without_original_support" in dec_exp.reason_codes

    # Duplicate evidence deduplication preserves single item
    agg = ProfessorAggregationService()
    dup_items = [
        _item("dup1", 40, EvidenceType.RESEARCH_PROJECT.value, "AI Project", "AI", orig_dense=0.65, content_hash="same_h"),
        _item("dup2", 40, EvidenceType.RESEARCH_PROJECT.value, "AI Project", "AI", orig_dense=0.65, content_hash="same_h"),
    ]
    bundles = agg.aggregate(dup_items)
    assert len(bundles[40].items_by_type[EvidenceType.RESEARCH_PROJECT.value]) == 1


def test_query_expansion_drift_validation():
    def _drifting_llm(query, u_res, k):
        return [
            "Large language models for clinical diagnosis",  # aligned (CS/AI)
            "Rock mechanics and strata control in underground coal mines",  # unrelated domain drift!
        ]

    exp_svc = QueryExpansionService(understanding_service=QueryUnderstandingService(), llm_expander=_drifting_llm)
    res = exp_svc.expand("Generative AI for healthcare")
    texts = [q.query_text for q in res.queries]
    assert "Large language models for clinical diagnosis" in texts
    assert "Rock mechanics and strata control in underground coal mines" not in texts
