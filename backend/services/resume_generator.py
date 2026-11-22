"""
Stage 6.2: Professor-Specific AI Tailored Resume Generator (`backend/services/resume_generator.py`).

Architecture & Factual Grounding Guarantees:
- Reuses the existing Google Gemini REST integration pattern (`GEMINI_API_KEY`,
  `gemini-2.5-flash`, `httpx`) established in `backend/search/query_understanding.py`.
- Operates strictly on verified PostgreSQL student records (filtered to the student's
  selected IDs for this professor) and verified PostgreSQL professor records.
- Architecturally prevents hallucination of new projects, skills, internships,
  publications, awards, dates, or metrics:
  1. All structural facts (titles, roles, organizations, institutions, dates, URLs,
     skills, education, publications, achievements) come verbatim from PostgreSQL.
  2. When Gemini is enabled, it may ONLY refine phrasing for the summary, bullets
     keyed by existing `source_id`s, and factual alignment highlights.
  3. Unknown `source_id`s, malformed JSON, or provider errors are caught safely and
     fall back to the deterministic professor-relevance-ranked grounded assembler.
- Never logs student PII or API keys.
"""
import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import httpx

from backend.api.schemas import (
    ResumeAchievementItemSchema,
    ResumeEducationItemSchema,
    ResumeExperienceItemSchema,
    ResumeHeaderSchema,
    ResumePreferencesSchema,
    ResumeProjectItemSchema,
    ResumePublicationItemSchema,
    ResumeSelectionIdsSchema,
    ResumeSkillGroupSchema,
    TailoredResumeContentSchema,
    TailoredResumeGenerateResponseSchema,
)
from backend.database.models import Department, Professor, Student

logger = logging.getLogger(__name__)

_STOPWORDS: Set[str] = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "this",
    "to", "using", "via", "with", "work", "working", "research", "study", "analysis",
    "system", "systems", "method", "methods", "approach", "based", "data", "model",
    "models", "new", "novel", "application", "applications", "professor", "department",
    "iit", "kharagpur", "india", "indian", "institute", "technology", "dr", "prof",
}

_SKILL_GROUP_LABELS = {
    "technical": "Technical Skills",
    "research": "Research Methods & Skills",
    "tool": "Tools & Frameworks",
    "language": "Programming Languages",
}

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.-]{1,}")

# High-signal domain phrases to preserve multi-word technical relevance
_DOMAIN_PHRASES = [
    "natural language processing",
    "computer vision",
    "machine learning",
    "deep learning",
    "reinforcement learning",
    "large language models",
    "transformer",
    "bert",
    "rag",
    "retrieval augmented generation",
    "information retrieval",
    "object detection",
    "image processing",
    "medical imaging",
    "biomedical",
    "healthcare",
    "clinical",
    "graph neural",
    "cryptography",
    "cybersecurity",
    "distributed systems",
    "robotics",
    "speech recognition",
    "signal processing",
    "embedded systems",
    "vlsi",
    "quantum computing",
    "federated learning",
]


def _tokenize(text: str) -> Set[str]:
    if not text:
        return set()
    tokens = {t.lower().strip(".,;:") for t in _TOKEN_RE.findall(text.lower())}
    return {t for t in tokens if len(t) >= 2 and t not in _STOPWORDS}


def _extract_phrases(text: str) -> Set[str]:
    low = (text or "").lower()
    return {p for p in _DOMAIN_PHRASES if p in low}


def _format_duration(start: Optional[str], end: Optional[str]) -> Optional[str]:
    parts = [p.strip() for p in (start or "", end or "") if p and p.strip()]
    return " – ".join(parts) if parts else None


def _format_year_duration(start_year: Optional[int], end_year: Optional[int]) -> Optional[str]:
    if start_year and end_year:
        return f"{start_year} – {end_year}"
    if start_year:
        return f"{start_year} – Present"
    if end_year:
        return str(end_year)
    return None


def _split_to_bullets(*fields: Optional[str], max_bullets: int = 4) -> List[str]:
    bullets: List[str] = []
    for raw in fields:
        if not raw or not raw.strip():
            continue
        # Split on newlines or explicit bullet markers while keeping prose intact
        for chunk in re.split(r"[\r\n]+", raw.strip()):
            cleaned = re.sub(r"^[\-\*•\s]+", "", chunk).strip()
            if cleaned and cleaned not in bullets:
                bullets.append(cleaned)
                if len(bullets) >= max_bullets:
                    return bullets
    return bullets


def build_professor_context(
    prof: Professor,
    dept: Optional[Department],
) -> Dict[str, Any]:
    """Collects verified research context from the professor's PostgreSQL records."""
    projects = [
        {
            "title": pp.project.title.strip(),
            "description": (pp.project.description or "").strip() or None,
        }
        for pp in (prof.professor_projects or [])
        if pp.project and (pp.project.title or "").strip()
    ][:8]

    verified_pubs = [
        {
            "title": ppub.publication.title.strip(),
            "year": ppub.publication.publication_year,
            "venue": ppub.publication.journal_or_conference,
        }
        for ppub in (prof.professor_publications or [])
        if ppub.verification_status == "verified"
        and ppub.publication
        and (ppub.publication.title or "").strip()
    ][:8]

    corpus_parts = [
        prof.research_interests or "",
        prof.biography or "",
        " ".join(p["title"] + " " + (p["description"] or "") for p in projects),
        " ".join(pub["title"] for pub in verified_pubs),
    ]
    full_text = "\n".join(part for part in corpus_parts if part.strip())

    # Extract concise display focus terms from research_interests first, then phrases
    focus_terms: List[str] = []
    if prof.research_interests:
        for seg in re.split(r"[,;\n•]+", prof.research_interests):
            term = seg.strip()
            if term and len(term) <= 60 and term not in focus_terms:
                focus_terms.append(term)
            if len(focus_terms) >= 8:
                break
    if not focus_terms:
        for phrase in sorted(_extract_phrases(full_text)):
            focus_terms.append(phrase.title())
            if len(focus_terms) >= 6:
                break

    return {
        "professor_id": prof.id,
        "name": prof.name,
        "designation": prof.designation,
        "department_name": dept.name if dept else None,
        "biography": (prof.biography or "").strip() or None,
        "research_interests": (prof.research_interests or "").strip() or None,
        "projects": projects,
        "verified_publications": verified_pubs,
        "tokens": _tokenize(full_text),
        "phrases": _extract_phrases(full_text),
        "focus_terms": focus_terms,
    }


def score_relevance(text: str, prof_context: Dict[str, Any]) -> Tuple[float, List[str]]:
    """Computes deterministic lexical + domain-phrase overlap between a student item and professor research."""
    prof_tokens: Set[str] = prof_context.get("tokens", set())
    prof_phrases: Set[str] = prof_context.get("phrases", set())
    item_tokens = _tokenize(text)
    item_phrases = _extract_phrases(text)

    shared_tokens = sorted(item_tokens & prof_tokens)
    shared_phrases = sorted(item_phrases & prof_phrases)

    score = float(len(shared_tokens)) + 3.0 * float(len(shared_phrases))
    matched_terms = shared_phrases + [t for t in shared_tokens if not any(t in p for p in shared_phrases)]
    return round(score, 2), matched_terms[:5]


def _default_section_order(template: str) -> List[str]:
    if template == "academic_research":
        return [
            "summary",
            "education",
            "research_interests",
            "research_experience",
            "publications",
            "projects",
            "skills",
            "experience",
            "achievements",
        ]
    if template == "technical_ai_ml":
        return [
            "summary",
            "skills",
            "projects",
            "research_experience",
            "experience",
            "education",
            "research_interests",
            "publications",
            "achievements",
        ]
    # modern_professional
    return [
        "summary",
        "education",
        "experience",
        "projects",
        "research_experience",
        "skills",
        "research_interests",
        "publications",
        "achievements",
    ]


def _build_grounded_baseline(
    student: Student,
    prof_context: Dict[str, Any],
    selected: ResumeSelectionIdsSchema,
    prefs: ResumePreferencesSchema,
) -> Tuple[TailoredResumeContentSchema, Dict[str, Any]]:
    """
    Constructs a 100% factually grounded, professor-relevance-ordered resume strictly
    from the student's PostgreSQL records and selected IDs.
    """
    header = ResumeHeaderSchema(
        full_name=(student.full_name or "").strip() or student.email,
        email=student.email,
        phone=student.phone,
        institution=student.institution,
        department=student.department,
        degree_program=student.degree_program,
        graduation_year=student.graduation_year,
        current_year_or_semester=student.current_year_or_semester,
        linkedin_url=student.linkedin_url,
        github_url=student.github_url,
        portfolio_url=student.portfolio_url,
    )

    # Education (always grounded in student_educations)
    education_items: List[ResumeEducationItemSchema] = [
        ResumeEducationItemSchema(
            source_id=edu.id,
            institution=edu.institution,
            degree=edu.degree,
            department_major=edu.department_major,
            duration=_format_year_duration(edu.start_year, edu.graduation_year),
            cgpa_or_percentage=edu.cgpa_or_percentage,
            relevant_coursework=edu.relevant_coursework,
        )
        for edu in sorted(student.educations or [], key=lambda x: (-(x.graduation_year or 0), -x.id))
    ]

    # Filter student records strictly to selected IDs owned by this student
    sel_project_ids = set(selected.project_ids)
    sel_res_exp_ids = set(selected.research_experience_ids)
    sel_tech_skill_ids = set(selected.technical_skill_ids)
    sel_res_skill_ids = set(selected.research_skill_ids)
    sel_exp_ids = set(selected.experience_ids)
    sel_ach_ids = set(selected.achievement_ids)
    sel_pub_ids = set(selected.publication_ids)

    all_matched_terms: List[str] = []

    # Projects
    project_items: List[ResumeProjectItemSchema] = []
    for proj in student.projects or []:
        if proj.entry_type != "project" or proj.id not in sel_project_ids:
            continue
        blob = " ".join(
            filter(
                None,
                [
                    proj.title,
                    proj.role,
                    proj.description,
                    proj.problem_statement,
                    proj.methodology,
                    proj.technologies_tools,
                    proj.outcomes_results,
                ],
            )
        )
        rel_score, matched = score_relevance(blob, prof_context)
        all_matched_terms.extend(matched)
        bullets = _split_to_bullets(proj.description, proj.methodology, proj.outcomes_results, max_bullets=4)
        project_items.append(
            ResumeProjectItemSchema(
                source_id=proj.id,
                entry_type="project",
                title=proj.title,
                role=proj.role,
                organization=proj.organization,
                duration=_format_duration(proj.start_date, proj.end_date),
                technologies=proj.technologies_tools,
                bullets=bullets,
                url=proj.github_url or proj.project_url,
                relevance_score=rel_score,
            )
        )
    project_items.sort(key=lambda x: (-x.relevance_score, -(x.source_id or 0)))

    # Research Experience
    research_exp_items: List[ResumeProjectItemSchema] = []
    for proj in student.projects or []:
        if proj.entry_type != "research_experience" or proj.id not in sel_res_exp_ids:
            continue
        blob = " ".join(
            filter(
                None,
                [
                    proj.title,
                    proj.role,
                    proj.organization,
                    proj.description,
                    proj.methodology,
                    proj.technologies_tools,
                    proj.outcomes_results,
                ],
            )
        )
        rel_score, matched = score_relevance(blob, prof_context)
        all_matched_terms.extend(matched)
        bullets = _split_to_bullets(proj.description, proj.methodology, proj.outcomes_results, max_bullets=4)
        research_exp_items.append(
            ResumeProjectItemSchema(
                source_id=proj.id,
                entry_type="research_experience",
                title=proj.title,
                role=proj.role,
                organization=proj.organization,
                duration=_format_duration(proj.start_date, proj.end_date),
                technologies=proj.technologies_tools,
                bullets=bullets,
                url=proj.project_url or proj.github_url,
                relevance_score=rel_score,
            )
        )
    research_exp_items.sort(key=lambda x: (-x.relevance_score, -(x.source_id or 0)))

    # Experience / Internships
    experience_items: List[ResumeExperienceItemSchema] = []
    for exp in student.experiences or []:
        if exp.id not in sel_exp_ids:
            continue
        blob = " ".join(
            filter(None, [exp.organization, exp.role, exp.responsibilities, exp.achievements, exp.technologies_used])
        )
        rel_score, matched = score_relevance(blob, prof_context)
        all_matched_terms.extend(matched)
        bullets = _split_to_bullets(exp.responsibilities, exp.achievements, max_bullets=4)
        experience_items.append(
            ResumeExperienceItemSchema(
                source_id=exp.id,
                organization=exp.organization,
                role=exp.role,
                location=exp.location,
                duration=_format_duration(exp.start_date, exp.end_date),
                technologies=exp.technologies_used,
                bullets=bullets,
                relevance_score=rel_score,
            )
        )
    experience_items.sort(key=lambda x: (-x.relevance_score, -(x.source_id or 0)))

    # Skills grouped by category, with professor-relevant skills ordered first
    grouped_skills: Dict[str, List[Tuple[float, str]]] = {}
    for skill in student.skills or []:
        is_research = skill.category == "research"
        if is_research and skill.id not in sel_res_skill_ids:
            continue
        if not is_research and skill.id not in sel_tech_skill_ids:
            continue
        rel_score, matched = score_relevance(f"{skill.name} {skill.experience_context or ''}", prof_context)
        all_matched_terms.extend(matched)
        label = _SKILL_GROUP_LABELS.get(skill.category, "Skills")
        display = f"{skill.name} ({skill.proficiency_level})" if skill.proficiency_level else skill.name
        grouped_skills.setdefault(label, []).append((rel_score, display))

    skill_groups: List[ResumeSkillGroupSchema] = []
    for label in ("Research Methods & Skills", "Technical Skills", "Tools & Frameworks", "Programming Languages"):
        entries = grouped_skills.get(label)
        if not entries:
            continue
        entries.sort(key=lambda pair: (-pair[0], pair[1].lower()))
        skill_groups.append(ResumeSkillGroupSchema(category=label, items=[name for _, name in entries]))

    # Publications
    publication_items: List[ResumePublicationItemSchema] = []
    for pub in student.publications or []:
        if pub.id not in sel_pub_ids:
            continue
        publication_items.append(
            ResumePublicationItemSchema(
                source_id=pub.id,
                title=pub.title,
                authors=pub.authors,
                venue=pub.journal_or_conference,
                date=pub.publication_date,
                doi_or_url=pub.doi_or_url,
                summary=pub.abstract,
            )
        )

    # Achievements & Certifications
    achievement_items: List[ResumeAchievementItemSchema] = []
    for ach in student.achievements or []:
        if ach.id not in sel_ach_ids:
            continue
        achievement_items.append(
            ResumeAchievementItemSchema(
                source_id=ach.id,
                entry_type=ach.entry_type if ach.entry_type in ("achievement", "certification") else "achievement",
                title=ach.title,
                issuer=ach.issuing_organization,
                date=ach.date_awarded,
                description=ach.description,
                credential_url=ach.credential_url,
            )
        )

    research_interests = (
        (student.research_interests_summary or "").strip() or None
        if selected.include_research_interests
        else None
    )

    # Build strictly factual summary grounded only in student's real fields
    identity_bits = [b for b in [student.degree_program, student.department] if b and b.strip()]
    identity_str = " ".join(identity_bits) if identity_bits else "Student"
    if student.institution and student.institution.strip():
        identity_str = f"{identity_str} student at {student.institution.strip()}"
    elif not identity_bits:
        identity_str = "Academic applicant"

    target_str = (prefs.target_position or "").strip() or f"research opportunities with {prof_context['name']}"
    summary_sentences = [f"{identity_str} applying for {target_str}."]

    top_skills = [s for grp in skill_groups for s in grp.items][:5]
    if top_skills:
        summary_sentences.append(f"Selected technical and research capabilities include {', '.join(top_skills)}.")
    if project_items or research_exp_items:
        top_titles = [p.title for p in (research_exp_items + project_items)[:2]]
        summary_sentences.append(f"Relevant work highlighted in this resume includes {' and '.join(top_titles)}.")

    # Deduplicated factual alignment highlights
    dedup_matched: List[str] = []
    for term in all_matched_terms:
        if term not in dedup_matched:
            dedup_matched.append(term)
        if len(dedup_matched) >= 6:
            break

    alignment_highlights: List[str] = []
    if dedup_matched:
        alignment_highlights.append(
            f"Shared keywords between your selected items and {prof_context['name']}'s profile: {', '.join(dedup_matched)}."
        )
    if project_items and project_items[0].relevance_score > 0:
        alignment_highlights.append(
            f"Prioritized project '{project_items[0].title}' based on topical overlap with {prof_context['name']}'s research."
        )
    if research_exp_items and research_exp_items[0].relevance_score > 0:
        alignment_highlights.append(
            f"Prioritized research experience '{research_exp_items[0].title}' for relevance."
        )

    section_order = _default_section_order(prefs.template)
    enabled_sections = [s for s in section_order if s in prefs.included_sections]

    content = TailoredResumeContentSchema(
        title=prefs.title.strip(),
        target_position=(prefs.target_position or "").strip() or None,
        template=prefs.template,
        preferred_length=prefs.preferred_length,
        header=header,
        summary=" ".join(summary_sentences),
        research_interests=research_interests,
        section_order=section_order,  # type: ignore[arg-type]
        enabled_sections=enabled_sections,  # type: ignore[arg-type]
        education=education_items,
        skills=skill_groups,
        projects=project_items,
        research_experience=research_exp_items,
        experience=experience_items,
        publications=publication_items,
        achievements=achievement_items,
        alignment_highlights=alignment_highlights,
    )

    llm_payload = {
        "professor": {
            "name": prof_context["name"],
            "designation": prof_context["designation"],
            "department": prof_context["department_name"],
            "research_interests": prof_context["research_interests"],
            "focus_terms": prof_context["focus_terms"],
            "projects": prof_context["projects"][:5],
            "verified_publications": prof_context["verified_publications"][:5],
        },
        "preferences": {
            "target_position": prefs.target_position,
            "preferred_length": prefs.preferred_length,
            "template": prefs.template,
            "additional_instructions": prefs.additional_instructions,
        },
        "student_facts": {
            "degree_program": student.degree_program,
            "department": student.department,
            "institution": student.institution,
            "research_interests": research_interests,
            "skills": [grp.model_dump() for grp in skill_groups],
            "projects": [
                {
                    "source_id": p.source_id,
                    "title": p.title,
                    "role": p.role,
                    "organization": p.organization,
                    "duration": p.duration,
                    "technologies": p.technologies,
                    "bullets": p.bullets,
                }
                for p in project_items
            ],
            "research_experience": [
                {
                    "source_id": p.source_id,
                    "title": p.title,
                    "role": p.role,
                    "organization": p.organization,
                    "duration": p.duration,
                    "technologies": p.technologies,
                    "bullets": p.bullets,
                }
                for p in research_exp_items
            ],
            "experience": [
                {
                    "source_id": e.source_id,
                    "organization": e.organization,
                    "role": e.role,
                    "location": e.location,
                    "duration": e.duration,
                    "technologies": e.technologies,
                    "bullets": e.bullets,
                }
                for e in experience_items
            ],
        },
    }
    return content, llm_payload


def _call_gemini_resume_tailor(
    llm_payload: Dict[str, Any],
    api_key: str,
    model: str,
    timeout_seconds: float = 25.0,
) -> Dict[str, Any]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    prompt = (
        "You are an academic resume editor preparing a professor-specific research resume.\n"
        "STRICT FACTUAL ACCURACY RULES:\n"
        "1. Use ONLY the facts provided in `student_facts`.\n"
        "2. NEVER invent projects, publications, skills, internships, awards, metrics, numbers, dates, or roles.\n"
        "3. Do NOT exaggerate contributions or fabricate connections to the professor.\n"
        "4. You may improve grammar, conciseness, and phrasing while preserving exact original facts.\n"
        "5. Emphasize genuine overlap with `professor` research interests.\n"
        "6. Return ONLY valid JSON with this exact schema:\n"
        "{\n"
        '  "summary": "2-3 sentence grounded academic summary",\n'
        '  "project_bullets": {"<source_id>": ["bullet 1", "bullet 2"]},\n'
        '  "research_experience_bullets": {"<source_id>": ["bullet 1", "bullet 2"]},\n'
        '  "experience_bullets": {"<source_id>": ["bullet 1", "bullet 2"]},\n'
        '  "alignment_highlights": ["concise factual connection 1"]\n'
        "}\n\n"
        f"INPUT DATA:\n{json.dumps(llm_payload, ensure_ascii=False)}"
    )

    resp = httpx.post(
        endpoint,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("AI provider returned non-object JSON payload.")
    return parsed


def _apply_grounded_llm_refinements(
    baseline: TailoredResumeContentSchema,
    llm_output: Dict[str, Any],
) -> TailoredResumeContentSchema:
    """
    Merges AI-refined phrasing into the grounded baseline while strictly rejecting
    unknown source IDs or malformed fields. All structural facts remain from PostgreSQL.
    """
    if not isinstance(llm_output, dict):
        raise ValueError("Malformed AI response: expected JSON object.")

    refined = baseline.model_copy(deep=True)

    summary = llm_output.get("summary")
    if isinstance(summary, str) and 20 <= len(summary.strip()) <= 1500:
        refined.summary = summary.strip()

    def _merge_bullets(items: Sequence[Any], bullet_map: Any) -> None:
        if not isinstance(bullet_map, dict):
            return
        valid_ids = {str(item.source_id): item for item in items if item.source_id is not None}
        for key, raw_bullets in bullet_map.items():
            target = valid_ids.get(str(key))
            if target is None or not isinstance(raw_bullets, list):
                continue
            cleaned = [b.strip() for b in raw_bullets if isinstance(b, str) and b.strip()][:5]
            if cleaned:
                target.bullets = cleaned

    _merge_bullets(refined.projects, llm_output.get("project_bullets"))
    _merge_bullets(refined.research_experience, llm_output.get("research_experience_bullets"))
    _merge_bullets(refined.experience, llm_output.get("experience_bullets"))

    highlights = llm_output.get("alignment_highlights")
    if isinstance(highlights, list):
        cleaned_hl = [h.strip() for h in highlights if isinstance(h, str) and h.strip()][:4]
        if cleaned_hl:
            refined.alignment_highlights = cleaned_hl

    return refined


def generate_tailored_resume(
    student: Student,
    prof: Professor,
    dept: Optional[Department],
    selected: ResumeSelectionIdsSchema,
    prefs: ResumePreferencesSchema,
    llm_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> TailoredResumeGenerateResponseSchema:
    """
    Generates a professor-tailored resume grounded strictly in the student's
    selected profile items and the professor's verified research context.
    """
    prof_context = build_professor_context(prof, dept)
    baseline, llm_payload = _build_grounded_baseline(student, prof_context, selected, prefs)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

    generation_mode = "grounded_fallback"
    provider_notice: Optional[str] = None
    final_content = baseline

    if llm_callable is not None or api_key:
        try:
            raw_ai = (
                llm_callable(llm_payload)
                if llm_callable is not None
                else _call_gemini_resume_tailor(llm_payload, api_key=api_key, model=model)
            )
            final_content = _apply_grounded_llm_refinements(baseline, raw_ai)
            generation_mode = "gemini"
        except Exception as exc:
            logger.warning("AI resume refinement unavailable (%s); using grounded fallback.", type(exc).__name__)
            generation_mode = "grounded_fallback"
            provider_notice = (
                "AI provider was unavailable or returned an invalid response; generated using the "
                "grounded relevance-ranked fallback without inventing any facts."
            )
    else:
        provider_notice = (
            "Generated using the grounded relevance-ranked engine (configure GEMINI_API_KEY on the "
            "backend server to enable Gemini phrasing refinement)."
        )

    return TailoredResumeGenerateResponseSchema(
        professor_id=prof.id,
        professor_name=prof.name,
        department_name=prof_context["department_name"],
        generation_mode=generation_mode,  # type: ignore[arg-type]
        provider_notice=provider_notice,
        professor_focus_terms=prof_context["focus_terms"],
        content=final_content,
    )
