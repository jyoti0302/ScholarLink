"""
Phase 2A Step 7 (Stage 3): QueryUnderstandingService & QueryExpansionService.

Supports:
1. Rules-first deterministic understanding & expansion using the Phase C topic taxonomy,
   canonical topic names, acronym aliases, and domain/area mappings (zero external API required).
2. Optional configurable LLM provider (e.g. Gemini 2.5 Flash) with strict JSON schema parsing,
   budget/timeout guards, and automatic fallback to rules-first expansion.
"""
from dataclasses import dataclass, field
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.search.document_builder import normalize_known_research_typos
from data_processing.topic_normalization import (
    ACRONYM_AND_ALIAS_MAP,
    TAXONOMY_RULES,
)

# Bidirectional acronym expansion table for search queries
ACRONYM_EXPANSIONS: Dict[str, str] = {
    "nlp": "Natural Language Processing",
    "ai": "Artificial Intelligence",
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "cv": "Computer Vision",
    "llm": "Large Language Models",
    "llms": "Large Language Models",
    "rag": "Retrieval-Augmented Generation",
    "iot": "Internet of Things",
    "cfd": "Computational Fluid Dynamics",
    "vlsi": "Very Large Scale Integration",
    "fem": "Finite Element Method",
    "fea": "Finite Element Analysis",
    "uav": "Unmanned Aerial Vehicles",
    "gnn": "Graph Neural Networks",
    "hci": "Human-Computer Interaction",
    "cps": "Cyber-Physical Systems",
    "mems": "Micro-Electro-Mechanical Systems",
    "gis": "Geographic Information Systems",
    "ann": "Artificial Neural Networks",
    "cnn": "Convolutional Neural Networks",
    "gan": "Generative Adversarial Networks",
}
REVERSE_ACRONYMS: Dict[str, str] = {v.lower(): k.upper() for k, v in ACRONYM_EXPANSIONS.items()}

# Curated interdisciplinary & subfield expansion pairs (used when LLM is disabled/unavailable)
CONCEPT_SUBFIELD_EXPANSIONS: List[Tuple[str, List[str]]] = [
    ("generative ai", ["large language models", "diffusion models", "generative adversarial networks"]),
    ("large language model", ["natural language processing", "retrieval-augmented generation", "foundation models"]),
    ("healthcare", ["medical imaging", "clinical decision support", "biomedical diagnosis", "point-of-care diagnostics"]),
    ("medical", ["clinical decision support", "biomedical imaging", "disease diagnosis"]),
    ("computer vision", ["object detection", "image segmentation", "visual recognition", "hyperspectral imaging"]),
    ("natural language processing", ["text mining", "machine translation", "speech processing", "sentiment analysis"]),
    ("robotics", ["autonomous systems", "motion planning", "manipulators", "unmanned aerial vehicles"]),
    ("biotechnology", ["molecular biology", "bioinformatics", "bioprocess engineering", "genetic engineering"]),
    ("drug delivery", ["nanocarriers", "controlled release", "targeted therapy", "polymeric nanoparticles"]),
    ("crispr", ["gene editing", "genome engineering", "functional genomics"]),
    ("mining safety", ["mine ventilation", "strata control", "rock burst", "hazard monitoring"]),
    ("slope stability", ["landslide susceptibility", "geotechnical stability", "rock slope engineering"]),
    ("rock mechanics", ["geomechanics", "fracture mechanics in rock", "tunneling and underground excavation"]),
    ("fluid mechanics", ["computational fluid dynamics", "turbulent flows", "heat transfer and multiphase flow"]),
    ("additive manufacturing", ["3d printing", "laser powder bed fusion", "wire arc additive manufacturing"]),
    (
        "transformer architecture",
        [
            "self-attention",
            "multi-head attention",
            "transformer encoder",
            "transformer decoder",
            "vision transformers",
            "transformer-based nlp",
        ],
    ),
    ("vision transformer", ["vision transformers", "self-attention for computer vision", "visual recognition"]),
    ("power transformer", ["transformer fault diagnosis", "dissolved gas analysis", "high voltage insulation"]),
]

_AI_CONTEXT_RE = re.compile(
    r"\b(artificial\s+intelligence|ai|deep\s+learning|machine\s+learning|neural|nlp|"
    r"natural\s+language|computer\s+vision|vision\s+transformer|vit|llm|llms|"
    r"large\s+language\s+model|self[\-\s]?attention|multi[\-\s]?head\s+attention|"
    r"encoder|decoder|generative\s+ai)\b",
    re.IGNORECASE,
)
_POWER_CONTEXT_RE = re.compile(
    r"\b(electrical|power\s+transformer|distribution\s+transformer|high\s+voltage|"
    r"substation|winding|dissolved\s+gas|dga|fault\s+diagnosis|power\s+system|"
    r"power\s+grid|hvdc|lvac|switchgear|insulation|tap\s+changer)\b",
    re.IGNORECASE,
)
_CONVERSATIONAL_PREFIX_RE = re.compile(
    r"^(?:"
    r"i\s+(?:want|would\s+like)\s+to\s+(?:work|research|study)\s+(?:on|in|about)\s+|"
    r"looking\s+for\s+(?:professors|faculty|research)\s+(?:in|on|about)\s+|"
    r"interested\s+in\s+(?:research\s+(?:in|on)\s+)?|"
    r"(?:work|working)\s+(?:in|on)\s+(?:the\s+(?:field|area)\s+of\s+)?|"
    r"research\s+(?:related\s+to|in|on)\s+"
    r")+",
    re.IGNORECASE,
)
_FIELD_CONNECTOR_RE = re.compile(
    r"\s+(?:working\s+in\s+the\s+(?:field|area)\s+of|in\s+the\s+(?:field|area)\s+of|"
    r"focusing\s+on|focused\s+on|specializing\s+in)\s+",
    re.IGNORECASE,
)

STOPWORDS = {
    "i", "want", "to", "work", "working", "on", "in", "for", "the", "a", "an", "of", "and", "or",
    "with", "about", "find", "professors", "faculty", "research", "interested", "looking", "whose",
    "is", "are", "related", "applications", "using", "based", "field", "area",
}


@dataclass
class QueryUnderstandingResult:
    raw_query: str
    cleaned_query: str
    main_field: Optional[str]
    application_domain: Optional[str]
    core_concepts: List[str] = field(default_factory=list)
    matched_domains: List[str] = field(default_factory=list)
    matched_areas: List[str] = field(default_factory=list)
    provider_used: str = "rules"
    research_topic: Optional[str] = None
    excluded_domains: List[str] = field(default_factory=list)


@dataclass
class ExpandedQuery:
    query_text: str
    query_kind: str  # "original" | "canonical_alias" | "subfield" | "llm"
    weight: float


@dataclass
class QueryExpansionResult:
    understanding: QueryUnderstandingResult
    queries: List[ExpandedQuery]  # Index 0 is ALWAYS the original query


class QueryUnderstandingService:
    """Extracts core research concepts, main field, application domain, and taxonomy mappings."""

    def understand(self, raw_query: str) -> QueryUnderstandingResult:
        cleaned = normalize_known_research_typos(re.sub(r"\s+", " ", (raw_query or "")).strip())
        low = cleaned.lower()

        # Strip conversational prefixes like "Work in ...", "Interested in ...", "Looking for research in ..."
        core_phrase = _CONVERSATIONAL_PREFIX_RE.sub("", low).strip(" .?!")

        # Prefer explicit domain/topic connectors ("working in the field of", "in the field of")
        # before falling back to generic "for" / "in" / "applied to".
        main_field: Optional[str] = None
        app_domain: Optional[str] = None
        research_topic: Optional[str] = None

        m_field = _FIELD_CONNECTOR_RE.split(core_phrase, maxsplit=1)
        if len(m_field) == 2 and m_field[0].strip() and m_field[1].strip():
            left = m_field[0].strip()
            right = m_field[1].strip()
            main_field = ACRONYM_AND_ALIAS_MAP.get(left, left.title())
            research_topic = ACRONYM_AND_ALIAS_MAP.get(right, right.title())
            app_domain = research_topic
        else:
            m_split = re.split(r"\s+(?:for|in|applied to)\s+", core_phrase, maxsplit=1)
            if len(m_split) == 2 and m_split[0] and m_split[1]:
                main_field = ACRONYM_AND_ALIAS_MAP.get(m_split[0].strip(), m_split[0].strip().title())
                app_domain = ACRONYM_AND_ALIAS_MAP.get(m_split[1].strip(), m_split[1].strip().title())
                research_topic = app_domain
            elif core_phrase:
                main_field = ACRONYM_AND_ALIAS_MAP.get(core_phrase, core_phrase.title())
                research_topic = main_field

        # Extract core concepts
        concepts: List[str] = []
        for acr, full in ACRONYM_EXPANSIONS.items():
            if re.search(rf"\b{re.escape(acr)}\b", low):
                if full not in concepts:
                    concepts.append(full)
        for alias_k, canonical in ACRONYM_AND_ALIAS_MAP.items():
            if len(alias_k) > 3 and re.search(rf"\b{re.escape(alias_k)}\b", low):
                if canonical not in concepts:
                    concepts.append(canonical)
        if research_topic and research_topic not in concepts:
            concepts.append(research_topic)

        # Disambiguate Transformer homonym (AI neural Transformer vs Electrical Power Transformer)
        has_transformer_word = bool(re.search(r"\btransformers?\b", low))
        has_ai_ctx = bool(_AI_CONTEXT_RE.search(low))
        has_power_ctx = bool(_POWER_CONTEXT_RE.search(low))
        excluded_domains: List[str] = []

        if has_transformer_word and has_ai_ctx and not has_power_ctx:
            excluded_domains.append("Electrical Power Transformers")
            for c in (
                "Self-Attention",
                "Multi-Head Attention",
                "Transformer Encoder",
                "Transformer Decoder",
                "Vision Transformers",
                "Transformer-based NLP",
            ):
                if c not in concepts:
                    concepts.append(c)
        elif has_transformer_word and has_power_ctx and not has_ai_ctx:
            excluded_domains.append("Neural Transformer Architecture")

        if not concepts:
            tokens = [t for t in re.findall(r"[a-zA-Z0-9\-]+", core_phrase) if t not in STOPWORDS]
            if tokens:
                concepts.append(" ".join(tokens))

        # Match against Phase C 3-tier taxonomy rules
        matched_domains: List[str] = []
        matched_areas: List[str] = []
        for dom, area, pattern in TAXONOMY_RULES:
            if re.search(pattern, low):
                if (
                    "Electrical Power Transformers" in excluded_domains
                    and "electrical" in dom.lower()
                    and not has_power_ctx
                ):
                    continue
                if dom not in matched_domains:
                    matched_domains.append(dom)
                if area not in matched_areas:
                    matched_areas.append(area)

        return QueryUnderstandingResult(
            raw_query=raw_query,
            cleaned_query=cleaned,
            main_field=main_field,
            application_domain=app_domain,
            core_concepts=concepts[:8],
            matched_domains=matched_domains,
            matched_areas=matched_areas,
            provider_used="rules",
            research_topic=research_topic,
            excluded_domains=excluded_domains,
        )


class QueryExpansionService:
    """
    Generates the original query + up to `max_expansions` (default 5) distinct,
    research-focused subqueries using an optional LLM provider with deterministic
    taxonomy/alias fallback.
    """

    def __init__(
        self,
        understanding_service: Optional[QueryUnderstandingService] = None,
        max_expansions: int = 5,
        llm_expander: Optional[Callable[[str, QueryUnderstandingResult, int], List[str]]] = None,
    ):
        self.understanding_service = understanding_service or QueryUnderstandingService()
        self.max_expansions = max(1, min(max_expansions, 5))
        self.llm_expander = llm_expander

    def _rule_based_expand(
        self,
        raw_query: str,
        u: QueryUnderstandingResult,
    ) -> List[ExpandedQuery]:
        low = raw_query.lower()
        candidates: List[ExpandedQuery] = []
        seen_norm = {re.sub(r"[^a-z0-9]+", "", low)}

        def _add(text: str, kind: str, weight: float):
            t_clean = re.sub(r"\s+", " ", text).strip()
            nk = re.sub(r"[^a-z0-9]+", "", t_clean.lower())
            if (
                t_clean
                and nk
                and nk not in seen_norm
                and len(candidates) < self.max_expansions
                and self.is_expansion_aligned(u, t_clean)
            ):
                seen_norm.add(nk)
                candidates.append(ExpandedQuery(query_text=t_clean, query_kind=kind, weight=weight))

        # 1. Acronym <-> full-form swap
        swapped = raw_query
        for acr, full in ACRONYM_EXPANSIONS.items():
            if re.search(rf"\b{re.escape(acr)}\b", low):
                swapped = re.sub(rf"\b{re.escape(acr)}\b", full, swapped, flags=re.IGNORECASE)
        if swapped != raw_query:
            _add(swapped, "canonical_alias", 0.90)

        # 2. Interdisciplinary / subfield combinations
        field_subfields: List[str] = []
        domain_subfields: List[str] = []
        for trigger, exps in CONCEPT_SUBFIELD_EXPANSIONS:
            if trigger in low:
                if u.application_domain and trigger in u.application_domain.lower():
                    domain_subfields.extend(exps)
                else:
                    field_subfields.extend(exps)

        if u.main_field and u.application_domain:
            _add(f"{u.main_field} applications in {u.application_domain}", "subfield", 0.85)
            for sf in field_subfields[:2]:
                _add(f"{sf} for {u.application_domain}", "subfield", 0.80)
            for df in domain_subfields[:2]:
                _add(f"{u.main_field} for {df}", "subfield", 0.75)
        else:
            for sf in field_subfields + domain_subfields:
                _add(sf, "subfield", 0.80)

        # 3. Taxonomy area context if room remains
        for area in u.matched_areas:
            if u.core_concepts:
                _add(f"{u.core_concepts[0]} and {area}", "subfield", 0.70)

        return candidates[: self.max_expansions]

    def is_expansion_aligned(self, u: QueryUnderstandingResult, expanded_text: str) -> bool:
        """
        Validates that an expanded query preserves the original research intent and does
        not drift into an unrelated taxonomy domain absent from the original query.
        """
        if not u.matched_domains:
            return True
        exp_low = (expanded_text or "").lower()
        exp_domains = {
            dom for dom, _, pattern in TAXONOMY_RULES if re.search(pattern, exp_low)
        }
        if not exp_domains:
            return True
        # Require at least one shared domain with the original query
        return bool(exp_domains & set(u.matched_domains))

    def expand(self, raw_query: str) -> QueryExpansionResult:
        u = self.understanding_service.understand(raw_query)
        original = ExpandedQuery(query_text=u.cleaned_query, query_kind="original", weight=1.0)

        expanded: List[ExpandedQuery] = []
        if self.llm_expander is not None:
            try:
                llm_queries = self.llm_expander(u.cleaned_query, u, self.max_expansions)
                seen_norm = {re.sub(r"[^a-z0-9]+", "", u.cleaned_query.lower())}
                for q in llm_queries:
                    if not isinstance(q, str):
                        continue
                    qc = re.sub(r"\s+", " ", q).strip()
                    nk = re.sub(r"[^a-z0-9]+", "", qc.lower())
                    if qc and nk and nk not in seen_norm and self.is_expansion_aligned(u, qc):
                        seen_norm.add(nk)
                        expanded.append(ExpandedQuery(query_text=qc, query_kind="llm", weight=0.80))
                    if len(expanded) >= self.max_expansions:
                        break
                if expanded:
                    u.provider_used = "llm"
            except Exception:
                expanded = []

        if not expanded:
            rule_cands = self._rule_based_expand(u.cleaned_query, u)
            expanded = [c for c in rule_cands if self.is_expansion_aligned(u, c.query_text)]
            u.provider_used = "rules"

        return QueryExpansionResult(
            understanding=u,
            queries=[original] + expanded[: self.max_expansions],
        )


def build_gemini_query_expander(
    api_key: Optional[str] = None,
    model: str = "gemini-2.5-flash",
    timeout_seconds: float = 8.0,
) -> Optional[Callable[[str, QueryUnderstandingResult, int], List[str]]]:
    """
    Optional Gemini 2.5 Flash expander factory. Returns None if no API key is configured
    so the search engine automatically uses the deterministic rules-first fallback.
    """
    key = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None

    import httpx

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

    def _expand(query: str, u: QueryUnderstandingResult, max_exp: int) -> List[str]:
        prompt = (
            "You are an academic research query expander for university faculty discovery.\n"
            f"User query: {query}\n"
            f"Generate up to {max_exp} distinct, research-focused search subqueries covering relevant "
            "subfields and methods. Do NOT repeat near-identical paraphrases or unrelated topics.\n"
            'Return ONLY valid JSON: {"expanded_queries": ["..."]}'
        )
        resp = httpx.post(
            endpoint,
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
            },
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        txt = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(txt)
        qs = parsed.get("expanded_queries", [])
        return [str(x) for x in qs if isinstance(x, str)][:max_exp]

    return _expand
