import logging
import re
from typing import Dict, List, Optional, Tuple
from data_processing.cleaning import clean_author_name

logger = logging.getLogger(__name__)

INSTITUTION_KEYWORDS = [
    "kharagpur",
    "iit kgp",
    "iit-kgp",
    "iitkgp",
    "indian institute of technology kharagpur"
]


class AuthorDisambiguator:
    def __init__(
        self,
        high_confidence_threshold: float = 0.80,
        ambiguous_threshold: float = 0.45
    ):
        self.high_threshold = high_confidence_threshold
        self.ambiguous_threshold = ambiguous_threshold

    @staticmethod
    def _tokenize_with_case(raw_name: str) -> List[str]:
        cleaned = clean_author_name(raw_name)
        raw_tokens = re.findall(r"[A-Za-z]+", cleaned)
        expanded: List[str] = []
        for idx, tok in enumerate(raw_tokens):
            # Split 2-letter ALL-CAPS leading/middle initials like "VN" -> ["v", "n"]
            if len(tok) == 2 and tok.isupper() and idx < len(raw_tokens) - 1:
                expanded.extend([tok[0].lower(), tok[1].lower()])
            else:
                expanded.append(tok.lower())
        return expanded

    def calculate_name_similarity(self, name_a: str, name_b: str) -> float:
        """
        Calculates similarity between two author names while requiring compatible
        first-name and surname matching (including validated initials and South Indian
        inverted surname-initial order). Rejects shared middle+surname only matches
        where given names, surnames, or initials conflict.
        """
        toks_a = self._tokenize_with_case(name_a)
        toks_b = self._tokenize_with_case(name_b)

        if not toks_a or not toks_b:
            return 0.0

        if toks_a == toks_b:
            return 1.0

        if set(toks_a) == set(toks_b):
            return 0.98

        full_a = [t for t in toks_a if len(t) > 1]
        init_a = [t for t in toks_a if len(t) == 1]
        full_b = [t for t in toks_b if len(t) > 1]
        init_b = [t for t in toks_b if len(t) == 1]

        shared_full = set(full_a).intersection(set(full_b))
        if not shared_full:
            return 0.0

        # Step 1: Match identical full tokens first so initials cannot match an already-shared surname/middle name
        unmatched_full_a = [t for t in full_a if t not in full_b]
        unmatched_full_b = [t for t in full_b if t not in full_a]

        # Step 2: Check if unmatched full tokens on one side are explained by 1-letter initials on the other side
        rem_init_b = list(init_b)
        truly_unmatched_full_a = []
        for t in unmatched_full_a:
            if t[0] in rem_init_b:
                rem_init_b.remove(t[0])
            else:
                truly_unmatched_full_a.append(t)

        rem_init_a = list(init_a)
        truly_unmatched_full_b = []
        for t in unmatched_full_b:
            if t[0] in rem_init_a:
                rem_init_a.remove(t[0])
            else:
                truly_unmatched_full_b.append(t)

        # Match any identical leftover 1-letter initials (e.g. "P V S N Murthy" vs "P. V. Murthy")
        common_inits = []
        for ia in list(rem_init_a):
            if ia in rem_init_b:
                rem_init_a.remove(ia)
                rem_init_b.remove(ia)
                common_inits.append(ia)

        # Step 3: If BOTH sides have unexplained tokens (full words or conflicting initials), reject!
        # Examples rejected here:
        # - "Gaurab Das Mahapatra" vs "Rita Das Mahapatra" (truly_unmatched_full: gaurab vs rita)
        # - "Krothapalli Sreenivasa Rao" vs "Y. Sreenivasa Rao" (krothapalli vs rem_init 'y')
        # - "G P Raja Sekhar" vs "T. Raja Sekhar" (rem_init 'g','p' vs rem_init 't')
        if (truly_unmatched_full_a or rem_init_a) and (truly_unmatched_full_b or rem_init_b):
            return 0.0

        # Step 4: Zero unexplained tokens and zero leftover initials -> exact initial expansion!
        # Examples preserved here:
        # - "Hari V Warrior" <-> "Hari Vijayan Warrior"
        # - "Mahendra Reddy Vanteru" <-> "V. Mahendra Reddy"
        # - "V N Achutha Naikan" <-> "VN Achutha Naikan"
        if not truly_unmatched_full_a and not truly_unmatched_full_b and not rem_init_a and not rem_init_b:
            if len(shared_full) >= 2:
                return 0.92
            if len(shared_full) == 1 and (toks_a[-1] == toks_b[-1] or toks_a[0] == toks_b[0]):
                # e.g. "N. Ganguly" <-> "Niloy Ganguly"
                return 0.65

        # Step 5: Same first full token AND same last full token with no conflicting initials,
        # where one side simply omitted a middle name (e.g. "Subhransu Ranjan Samantaray" <-> "Subhransu Samantaray")
        if (
            len(full_a) >= 2
            and len(full_b) >= 2
            and full_a[0] == full_b[0]
            and full_a[-1] == full_b[-1]
            and not rem_init_a
            and not rem_init_b
        ):
            return 0.88

        # Step 6: Uncertain subset / extra initial on one side (e.g., "Arup Das" vs "Arup K. Das",
        # "Sri Krishna Kumar" vs "Krishna Kumar", "P V S N Murthy" vs "P. V. Murthy") -> needs_review (0.55)
        if toks_a[-1] == toks_b[-1] and (len(shared_full) >= 2 or (len(shared_full) >= 1 and common_inits)):
            return 0.55

        return 0.0

    def match_author_candidate(
        self,
        professor_name: str,
        professor_topics: List[str],
        candidate: Dict,
        known_orcid: Optional[str] = None,
        known_openalex_id: Optional[str] = None
    ) -> Tuple[float, str, str]:
        """
        Matches an OpenAlex author candidate against a Professor.
        Returns:
            (confidence_score, verification_status, evidence_summary)
        """
        score = 0.0
        evidence_items = []

        cand_name = candidate.get("display_name", "")
        name_sim = self.calculate_name_similarity(professor_name, cand_name)

        if name_sim >= 0.95:
            score += 0.45
            evidence_items.append(f"Exact name match ('{cand_name}')")
        elif name_sim >= 0.70:
            score += 0.25
            evidence_items.append(f"Strong name match ('{cand_name}')")
        elif name_sim >= 0.50:
            score += 0.15
            evidence_items.append(f"Partial name match ('{cand_name}')")
        else:
            return 0.0, "rejected", "Name similarity below threshold"

        # Check Known OpenAlex ID
        cand_id = candidate.get("openalex_id", "")
        if known_openalex_id and cand_id:
            if known_openalex_id.split("/")[-1] == cand_id.split("/")[-1]:
                score += 0.30
                evidence_items.append("Verified OpenAlex Author ID match")

        # Check ORCID
        cand_orcid = candidate.get("orcid")
        if known_orcid and cand_orcid:
            if known_orcid.rstrip("/").split("/")[-1] == cand_orcid.rstrip("/").split("/")[-1]:
                score += 0.25
                evidence_items.append(f"ORCID match ({cand_orcid})")

        # Check Institution Affiliation
        institutions = [inst.lower() for inst in candidate.get("institutions", [])]
        has_kgp_affiliation = any(
            any(kw in inst for kw in INSTITUTION_KEYWORDS)
            for inst in institutions
        )

        if has_kgp_affiliation:
            score += 0.40
            evidence_items.append("Confirmed IIT Kharagpur institutional affiliation")
        else:
            # Check historical affiliations
            affs = candidate.get("affiliations", [])
            for aff in affs:
                inst_name = (aff.get("institution") or {}).get("display_name", "").lower()
                if any(kw in inst_name for kw in INSTITUTION_KEYWORDS):
                    score += 0.25
                    evidence_items.append("Historical IIT Kharagpur affiliation found")
                    has_kgp_affiliation = True
                    break

        # Check Topic / Concept Overlap
        cand_concepts = [c.lower() for c in candidate.get("summary_stats", {}).get("top_concepts", [])]
        matched_topics = []
        for pt in professor_topics:
            pt_low = pt.lower()
            if any(pt_low in c or c in pt_low for c in cand_concepts):
                matched_topics.append(pt)

        if matched_topics:
            score += min(0.15, len(matched_topics) * 0.05)
            evidence_items.append(f"Topic overlap: {', '.join(matched_topics[:3])}")

        final_score = min(1.0, round(score, 2))
        evidence_str = "; ".join(evidence_items)

        if final_score >= self.high_threshold and has_kgp_affiliation:
            status = "pending"  # High confidence, pending final review/auto-approval
        elif final_score >= self.ambiguous_threshold:
            status = "needs_review"  # Ambiguous match, flag for human verification
        else:
            status = "rejected"

        return final_score, status, evidence_str

    def evaluate_publication_authorship(
        self,
        professor_name: str,
        work: Dict
    ) -> Tuple[float, str, Optional[str]]:
        """
        Evaluates whether a publication authorship belongs to the professor.
        Returns:
            (confidence_score, evidence, author_position)
        """
        score = 0.0
        evidence_items = []
        author_position = None
        has_kgp_aff = False

        authorships = work.get("authorships", [])
        for authorship in authorships:
            author_data = authorship.get("author", {})
            auth_name = author_data.get("display_name", "")
            sim = self.calculate_name_similarity(professor_name, auth_name)

            if sim >= 0.70:
                author_position = authorship.get("author_position")
                evidence_items.append(f"Author name match in paper ('{auth_name}', pos: {author_position})")

                # Check institutions in this authorship
                insts = authorship.get("institutions", [])
                for inst in insts:
                    inst_name = inst.get("display_name", "").lower()
                    if any(kw in inst_name for kw in INSTITUTION_KEYWORDS):
                        has_kgp_aff = True
                        evidence_items.append("Paper authorship affiliated with IIT Kharagpur")
                        break

                if sim >= 0.95:
                    score += 0.50
                else:
                    score += 0.30

                if has_kgp_aff:
                    score += 0.40

                break

        final_score = min(1.0, round(score, 2))
        return final_score, "; ".join(evidence_items), author_position
