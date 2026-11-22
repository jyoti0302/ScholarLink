import io
from types import SimpleNamespace
import zipfile

from backend.api.schemas import ResumePreferencesSchema, ResumeSelectionIdsSchema
from backend.services.resume_exporter import export_resume_docx, export_resume_pdf
from backend.services.resume_generator import generate_tailored_resume


def _make_student():
    return SimpleNamespace(
        id=1,
        email="aarav@iitkgp.ac.in",
        full_name="Aarav Sharma",
        phone="+91-9876543210",
        institution="IIT Kharagpur",
        department="Computer Science and Engineering",
        degree_program="B.Tech",
        graduation_year=2027,
        current_year_or_semester="6th Semester",
        research_interests_summary="Natural language processing, computer vision, and biomedical AI.",
        github_url="https://github.com/aarav",
        linkedin_url="https://linkedin.com/in/aarav",
        portfolio_url=None,
        educations=[
            SimpleNamespace(
                id=1,
                institution="IIT Kharagpur",
                degree="B.Tech",
                department_major="Computer Science and Engineering",
                start_year=2023,
                graduation_year=2027,
                cgpa_or_percentage="9.1 / 10.0",
                relevant_coursework="Deep Learning, NLP, Computer Vision",
            )
        ],
        skills=[
            SimpleNamespace(id=10, name="BERT & Transformers", category="technical", proficiency_level="Advanced", experience_context="NLP fine-tuning"),
            SimpleNamespace(id=11, name="OpenCV & Object Detection", category="technical", proficiency_level="Advanced", experience_context="Computer vision pipelines"),
            SimpleNamespace(id=12, name="Ablation Study Design", category="research", proficiency_level="Intermediate", experience_context="Benchmark evaluation"),
        ],
        projects=[
            SimpleNamespace(
                id=101,
                entry_type="project",
                title="RAG Pipeline with BERT Reranking",
                role="Lead Developer",
                organization="KGP NLP Group",
                description="Built a retrieval augmented generation pipeline for Indian language QA.",
                problem_statement=None,
                methodology="Fine-tuned BERT cross-encoder for passage reranking.",
                technologies_tools="Python, PyTorch, Hugging Face, FAISS",
                outcomes_results="Improved MRR@10 by 19% on benchmark dataset.",
                start_date="Jan 2026",
                end_date="Apr 2026",
                project_url=None,
                github_url="https://github.com/aarav/rag-bert",
            ),
            SimpleNamespace(
                id=102,
                entry_type="project",
                title="Real-Time Object Detection for Autonomous Drones",
                role="Vision Engineer",
                organization="Aerial Robotics Club",
                description="Implemented image processing and object detection for onboard drone cameras.",
                problem_statement=None,
                methodology="Quantized YOLO computer vision backbone for edge inference.",
                technologies_tools="PyTorch, OpenCV, TensorRT",
                outcomes_results="Achieved 42 FPS with 0.86 mAP on validation set.",
                start_date="Aug 2025",
                end_date="Dec 2025",
                project_url=None,
                github_url="https://github.com/aarav/drone-cv",
            ),
            SimpleNamespace(
                id=103,
                entry_type="research_experience",
                title="Clinical Biomedical NLP Summarization",
                role="Undergraduate Research Assistant",
                organization="AI Health Lab",
                description="Biomedical clinical note summarization with transformer models.",
                problem_statement=None,
                methodology="Domain-adaptive pretraining on biomedical abstracts.",
                technologies_tools="PyTorch, BioBERT",
                outcomes_results="Increased ROUGE-L by 4.1 points over baseline.",
                start_date="May 2025",
                end_date="Jul 2025",
                project_url="https://arxiv.org/abs/2501.00001",
                github_url=None,
            ),
        ],
        experiences=[
            SimpleNamespace(
                id=201,
                organization="Microsoft Research India",
                role="Research Intern",
                location="Bengaluru",
                start_date="May 2025",
                end_date="Jul 2025",
                responsibilities="Evaluated transformer language models on multilingual NLP tasks.",
                achievements="Reduced inference latency by 15%.",
                technologies_used="Python, PyTorch, ONNX",
            )
        ],
        achievements=[
            SimpleNamespace(
                id=301,
                entry_type="achievement",
                title="Institute Silver Medal Nominee",
                issuing_organization="IIT Kharagpur",
                date_awarded="2025",
                description="Top 5% academic standing.",
                credential_url=None,
            )
        ],
        publications=[
            SimpleNamespace(
                id=401,
                title="Efficient Cross-Lingual Retrieval",
                authors="A. Sharma, P. Mitra",
                journal_or_conference="ACL Workshop",
                publication_date="2026",
                doi_or_url="https://doi.org/10.1000/test",
                abstract="Studies sparse-dense retrieval for Indian languages.",
            )
        ],
    )


def _make_professor(prof_id: int, name: str, interests: str, bio: str):
    return SimpleNamespace(
        id=prof_id,
        name=name,
        designation="Professor",
        research_interests=interests,
        biography=bio,
        professor_projects=[],
        professor_publications=[],
    )


def test_professor_specific_tailoring_prioritizes_relevant_projects_for_nlp_vs_cv():
    student = _make_student()
    dept = SimpleNamespace(name="Computer Science and Engineering")
    selected = ResumeSelectionIdsSchema(
        project_ids=[101, 102],
        research_experience_ids=[103],
        technical_skill_ids=[10, 11],
        research_skill_ids=[12],
        include_research_interests=True,
        experience_ids=[201],
        achievement_ids=[301],
        publication_ids=[401],
    )
    prefs = ResumePreferencesSchema(title="Research Resume", template="academic_research")

    nlp_prof = _make_professor(
        1,
        "Prof. NLP Faculty",
        "Natural Language Processing, BERT, RAG, Information Retrieval, Transformer Models",
        "Works on large language models and multilingual NLP.",
    )
    cv_prof = _make_professor(
        2,
        "Prof. Vision Faculty",
        "Computer Vision, Object Detection, Image Processing, Autonomous Robotics",
        "Works on real-time visual recognition and edge vision.",
    )

    nlp_res = generate_tailored_resume(student, nlp_prof, dept, selected, prefs)
    cv_res = generate_tailored_resume(student, cv_prof, dept, selected, prefs)

    # Same student profile produces different ordering for NLP vs CV professors
    assert nlp_res.content.projects[0].source_id == 101
    assert cv_res.content.projects[0].source_id == 102
    assert nlp_res.content.projects[0].title == "RAG Pipeline with BERT Reranking"
    assert cv_res.content.projects[0].title == "Real-Time Object Detection for Autonomous Drones"


def test_llm_grounding_strips_unknown_source_ids_and_preserves_original_facts():
    student = _make_student()
    dept = SimpleNamespace(name="Computer Science and Engineering")
    prof = _make_professor(1, "Prof. NLP Faculty", "Natural Language Processing, BERT", "NLP research.")
    selected = ResumeSelectionIdsSchema(project_ids=[101], technical_skill_ids=[10])
    prefs = ResumePreferencesSchema(title="NLP Resume")

    def fake_gemini(_payload):
        return {
            "summary": "B.Tech CSE student at IIT Kharagpur focused on BERT and RAG systems.",
            "project_bullets": {
                "101": ["Built a BERT-based RAG pipeline improving MRR@10 by 19%."],
                "9999": ["HALLUCINATED PROJECT THAT DOES NOT EXIST"],
            },
            "alignment_highlights": ["Direct overlap in BERT and retrieval-augmented generation."],
        }

    res = generate_tailored_resume(student, prof, dept, selected, prefs, llm_callable=fake_gemini)
    assert res.generation_mode == "gemini"
    assert len(res.content.projects) == 1
    assert res.content.projects[0].source_id == 101
    assert res.content.projects[0].title == "RAG Pipeline with BERT Reranking"
    assert res.content.projects[0].duration == "Jan 2026 – Apr 2026"
    assert "HALLUCINATED" not in str(res.content.model_dump())


def test_ai_provider_failure_and_malformed_response_fall_back_safely():
    student = _make_student()
    dept = SimpleNamespace(name="Computer Science and Engineering")
    prof = _make_professor(1, "Prof. NLP Faculty", "NLP", "NLP.")
    selected = ResumeSelectionIdsSchema(project_ids=[101])
    prefs = ResumePreferencesSchema(title="NLP Resume")

    def failing_llm(_payload):
        raise RuntimeError("Upstream timeout")

    res_fail = generate_tailored_resume(student, prof, dept, selected, prefs, llm_callable=failing_llm)
    assert res_fail.generation_mode == "grounded_fallback"
    assert res_fail.provider_notice is not None
    assert len(res_fail.content.projects) == 1

    def malformed_llm(_payload):
        return "not-a-dict"  # type: ignore[return-value]

    res_bad = generate_tailored_resume(student, prof, dept, selected, prefs, llm_callable=malformed_llm)
    assert res_bad.generation_mode == "grounded_fallback"
    assert len(res_bad.content.projects) == 1


def test_security_foreign_item_ids_cannot_leak_into_student_resume():
    student = _make_student()
    dept = SimpleNamespace(name="CSE")
    prof = _make_professor(1, "Prof. NLP", "NLP", "NLP")
    # Pass non-owned/foreign IDs (999, 888) — must be ignored cleanly
    selected = ResumeSelectionIdsSchema(
        project_ids=[999],
        technical_skill_ids=[888],
        experience_ids=[777],
        publication_ids=[666],
    )
    res = generate_tailored_resume(student, prof, dept, selected, ResumePreferencesSchema())
    assert res.content.projects == []
    assert res.content.skills == []
    assert res.content.experience == []
    assert res.content.publications == []


def test_pdf_and_docx_export_produce_valid_non_empty_documents_with_links():
    student = _make_student()
    dept = SimpleNamespace(name="Computer Science and Engineering")
    prof = _make_professor(1, "Prof. NLP Faculty", "NLP, BERT, RAG", "NLP")
    selected = ResumeSelectionIdsSchema(
        project_ids=[101],
        research_experience_ids=[103],
        technical_skill_ids=[10],
        research_skill_ids=[12],
        include_research_interests=True,
        experience_ids=[201],
        achievement_ids=[301],
        publication_ids=[401],
    )

    for tmpl in ("academic_research", "modern_professional", "technical_ai_ml"):
        res = generate_tailored_resume(
            student,
            prof,
            dept,
            selected,
            ResumePreferencesSchema(title="Edited Resume", template=tmpl),
        )
        # Simulate user edit before download
        res.content.summary = "Custom edited summary verified in export."

        pdf_bytes = export_resume_pdf(res.content, template=tmpl)
        assert pdf_bytes.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf_bytes
        assert b"Aarav Sharma" in pdf_bytes
        assert b"Custom edited summary verified in export." in pdf_bytes
        assert b"/Subtype /Link" in pdf_bytes
        assert b"mailto:aarav@iitkgp.ac.in" in pdf_bytes

        docx_bytes = export_resume_docx(res.content, template=tmpl)
        assert len(docx_bytes) > 500
        with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
            names = set(zf.namelist())
            assert {"[Content_Types].xml", "_rels/.rels", "word/document.xml", "word/styles.xml", "word/_rels/document.xml.rels"} <= names
            doc_xml = zf.read("word/document.xml").decode("utf-8")
            rels_xml = zf.read("word/_rels/document.xml.rels").decode("utf-8")
            assert "Aarav Sharma" in doc_xml
            assert "Custom edited summary verified in export." in doc_xml
            assert "RAG Pipeline with BERT Reranking" in doc_xml
            assert "mailto:aarav@iitkgp.ac.in" in rels_xml
            assert "https://github.com/aarav" in rels_xml
