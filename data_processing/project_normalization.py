"""
Non-destructive normalization helpers for research project titles (Phase 2 / Phase B).

All functions are pure: they return a new string / label and never touch the database.
Callers are responsible for preserving the original extracted title.
"""
import re
from typing import Dict, Iterable, Optional, Set

# ---------------------------------------------------------------------------
# 1. Missing-space / hyphen repair
# ---------------------------------------------------------------------------
# Explicit, manually reviewed list of line-wrap concatenations found in the IIT Kharagpur
# project corpus. A generic camelCase splitter is deliberately NOT used because the corpus
# contains many legitimate product / tool names (TensorFlow, AquaHawk, DeepFake, BlockSpatial,
# AgriSmart, GlasGrid, AutoSuggest, ...).
EXPLICIT_SPACING_FIXES: Dict[str, str] = {
    # TitleCase + TitleCase line-wrap joins
    "InstrumentationSystem": "Instrumentation System",
    "DrugLoaded": "Drug Loaded",
    "CondensateFormation": "Condensate Formation",
    "TheirRole": "Their Role",
    "FluxHollow": "Flux Hollow",
    "MetalOrganic": "Metal-Organic",
    "WasteWater": "Waste-Water",
    "DesignNetwork": "Design Network",
    "CanalSystem": "Canal System",
    "SemiAutonomous": "Semi-Autonomous",
    "MiningBlock": "Mining Block",
    "MouzaAskola": "Mouza Askola",
    "ComputerVision": "Computer Vision",
    "LabelFree": "Label-Free",
    "AntiCyclic": "Anti-Cyclic",
    "UttarPradesh": "Uttar Pradesh",
    "PorousMedium": "Porous Medium",
    "SuperiorIntracellular": "Superior Intracellular",
    # lowercase joins / lost hyphens
    "multiplexedlateral": "multiplexed lateral",
    "Sedimentaeration": "Sediment-aeration",
    "Photovoltaicthermal": "Photovoltaic-thermal",
    "Arsenicin": "Arsenic in",
    "Temperatureand": "Temperature and",
    "Sourcesbased": "Sources based",
    "alkylidenebutenolide": "alkylidene-butenolide",
    "stimuliresponsive": "stimuli-responsive",
    "DEDbased": "DED-based",
    "CMTWAAM": "CMT-WAAM",
}
LITERAL_FIXES = [
    ("Lab-on- a-Chip", "Lab-on-a-Chip"),
    ("Lab-ona-Chip", "Lab-on-a-Chip"),
    ("-toMedium", "-to-Medium"),
]
_FUNCTION_WORD_JOIN = re.compile(r"\b(of|for|and|in|on|with|the|to|by|from|via)([A-Z][a-z]{2,})\b")
_COMMA_NO_SPACE = re.compile(r",(?=[A-Z][a-z])")


def fix_missing_spaces(title: Optional[str]) -> Optional[str]:
    """Repairs line-wrap concatenations ('CondensateFormation', 'forTuberculosis', 'Jhargram,West')."""
    if not title:
        return title
    out = title
    for bad, good in LITERAL_FIXES:
        out = out.replace(bad, good)
    for bad, good in EXPLICIT_SPACING_FIXES.items():
        out = re.sub(rf"\b{re.escape(bad)}\b", good, out)
    out = _FUNCTION_WORD_JOIN.sub(lambda m: f"{m.group(1)} {m.group(2)}", out)
    out = _COMMA_NO_SPACE.sub(", ", out)
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return out


# ---------------------------------------------------------------------------
# 2. ALL CAPS -> readable title case, preserving acronyms
# ---------------------------------------------------------------------------
BASE_ACRONYMS: Set[str] = {
    # agencies / institutions
    "IIT", "IITKGP", "ICMR", "DRDO", "ISRO", "MHRD", "MOE", "DST", "DBT", "CSIR", "SERB", "ANRF", "MEITY",
    "DAE", "BRNS", "AICTE", "UGC", "ONGC", "NTPC", "BHEL", "SAIL", "GAIL", "IOCL", "BARC", "NIOT", "INCOIS",
    "IMD", "NRSC", "SAC", "VSSC", "ARDB", "NABARD", "ICAR", "UKIERI", "SPARC", "IMPRINT", "UAY", "GIAN",
    "WB", "WBDST", "UNICEF", "WHO", "USA", "UK", "EU", "NSDI", "NDR", "INSAT", "NASA", "DFID", "BIRAC",
    # technical
    "AI", "ML", "NLP", "IOT", "CFD", "FEM", "FEA", "VLSI", "UAV", "UAVS", "MAV", "MAVS", "CNN", "ANN", "RNN",
    "LSTM", "GPU", "CPU", "FPGA", "ASIC", "CMOS", "MEMS", "NEMS", "RF", "DC", "AC", "HVDC", "PV", "PVT", "LED",
    "OLED", "LIDAR", "RADAR", "SAR", "GPS", "GNSS", "GIS", "DNA", "RNA", "MRNA", "PCR", "HIV", "TB", "MRI",
    "CT", "ECG", "EEG", "EMG", "SEM", "TEM", "XRD", "NMR", "FTIR", "UV", "IR", "NIR", "CO2", "CNT", "CNTS",
    "MOF", "MOFS", "WTP", "STP", "ETP", "CETP", "ZLD", "MLD", "FSTP", "FSM", "DPR", "RCC", "PSC", "HVAC",
    "EV", "EVS", "HEV", "SOFC", "PEM", "LNG", "CNG", "LPG", "IC", "PLC", "SCADA", "ERP", "API", "5G", "4G",
    "6G", "LTE", "MIMO", "OFDM", "WSN", "SDN", "NOC", "SOC", "HPC", "CAD", "CAM", "CNC", "PID", "MPC",
    "QOS", "VR", "AR", "XR", "HCI", "CPS", "GAN", "GANS", "LLM", "LLMS", "RAG", "NDT", "PCB", "LCA", "AMR",
}
# Function words kept lowercase in title case (unless first word)
SMALL_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "into", "nor", "of", "on", "onto",
    "or", "over", "per", "the", "to", "under", "upon", "via", "vs", "with", "within", "without",
}
# Short words that are real English words even though they are 2-4 uppercase letters
COMMON_SHORT_WORDS = {
    "GAS", "OIL", "USE", "NEW", "LOW", "RAW", "DRY", "WET", "HOT", "AIR", "SEA", "ICE", "BIO", "NON", "ALL",
    "ONE", "TWO", "LAB", "LABS", "AGE", "SET", "MAP", "WAY", "HIGH", "WIND", "SOIL", "RICE", "WAVE", "HEAT",
    "FLOW", "LOAD", "IRON", "ZINC", "LEAD", "GOLD", "COAL", "ROAD", "RAIL", "SHIP", "TEST", "CELL", "GENE",
    "DATA", "BASE", "BASED", "SOLAR", "FIRE", "FOOD", "WATER", "SMART", "NANO", "MICRO", "MACRO", "OPEN",
    "IS", "IT", "ITS", "BE", "NO", "UP", "OUT", "OFF", "SUB", "PRE", "POST", "ANTI", "SELF", "MULTI",
    "INTO", "ONTO", "UPON", "OVER", "WITH", "FROM", "THAT", "THIS", "THEIR", "FOR", "AND", "THE", "VIA",
    "HERITAGE", "KIOSK", "PART", "PHASE", "PIT", "TATA", "DESIGN", "MODEL", "STUDY", "SYSTEM", "PROJECT",
    "USING", "UNDER", "INDIA",
}


SPECIAL_CASE_TOKENS = {"RNAI": "RNAi", "SIRNA": "siRNA", "MIRNA": "miRNA", "PH": "pH", "IOT": "IoT",
                       "MOFS": "MOFs", "CNTS": "CNTs", "UAVS": "UAVs", "GANS": "GANs", "LLMS": "LLMs",
                       "EVS": "EVs", "MAVS": "MAVs"}


def learn_acronyms(mixed_case_titles: Iterable[str], min_occurrences: int = 2) -> Set[str]:
    """
    Learns acronyms from titles that are NOT all-caps: tokens written fully in uppercase there
    (e.g. 'UAV', 'DRDO', 'CFD') are treated as acronyms when converting all-caps titles.
    Titles that are themselves mostly uppercase are ignored, and function words / common short
    English words are never accepted as acronyms.
    """
    counts: Dict[str, int] = {}
    for t in mixed_case_titles:
        if not t or t.isupper():
            continue
        words = re.findall(r"[A-Za-z]{2,}", t)
        if not words:
            continue
        upper_ratio = sum(1 for w in words if w.isupper()) / len(words)
        if upper_ratio > 0.35:
            continue
        for tok in re.findall(r"\b[A-Z][A-Z0-9]{1,9}\b", t):
            counts[tok] = counts.get(tok, 0) + 1
    learned = {
        tok for tok, n in counts.items()
        if n >= min_occurrences and tok not in COMMON_SHORT_WORDS and tok.lower() not in SMALL_WORDS
    }
    return learned | BASE_ACRONYMS


def _case_word(word: str, is_first: bool, acronyms: Set[str]) -> str:
    if not word:
        return word
    core = re.sub(r"[^A-Za-z0-9]", "", word)
    if not core:
        return word
    upper_core = core.upper()
    if upper_core in SPECIAL_CASE_TOKENS:
        return word.replace(core, SPECIAL_CASE_TOKENS[upper_core])
    # Keep acronyms and tokens containing digits (CO2, 5G) as written
    if upper_core in acronyms or any(ch.isdigit() for ch in core):
        return word
    # Roman numerals (Phase II, Part III)
    if re.fullmatch(r"[IVX]{1,5}", upper_core) and upper_core not in {"I"}:
        return word
    lower = word.lower()
    if not is_first and core.lower() in SMALL_WORDS:
        return lower
    # Capitalize first alphabetic character
    for i, ch in enumerate(lower):
        if ch.isalpha():
            return lower[:i] + ch.upper() + lower[i + 1:]
    return lower


def smart_title_case(title: Optional[str], acronyms: Set[str]) -> Optional[str]:
    """Converts an ALL CAPS title to readable Title Case while preserving acronyms."""
    if not title or not title.isupper():
        return title
    words = title.split(" ")
    out = []
    first_done = False
    for w in words:
        if not w:
            out.append(w)
            continue
        # Compound tokens containing a digit (SU-8, INSAT-3D, NH-6, PM2.5) are kept verbatim
        if any(ch.isdigit() for ch in w) and re.search(r"[-/]", w):
            out.append(w)
            first_done = True
            continue
        # handle hyphen / slash compounds piece by piece (e.g. "GEO-SPATIAL", "AI/ML")
        parts = re.split(r"([-/])", w)
        cased = []
        for j, part in enumerate(parts):
            if part in ("-", "/"):
                cased.append(part)
                continue
            cased.append(_case_word(part, is_first=(not first_done and j == 0), acronyms=acronyms))
        out.append("".join(cased))
        first_done = True
    result = " ".join(out)
    # Capitalize the word following a colon (subtitle)
    result = re.sub(r"(:\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), result)
    return result


def is_convertible_all_caps(title: Optional[str]) -> bool:
    """Only long, multi-word ALL CAPS titles are converted (short administrative codes are left alone)."""
    if not title or not title.isupper() or len(title) <= 10:
        return False
    return len(re.findall(r"[A-Za-z]{2,}", title)) >= 3


# ---------------------------------------------------------------------------
# 3. Project category classification (labels only, nothing is deleted)
# ---------------------------------------------------------------------------
CATEGORY_SPONSORED = "sponsored_research"
CATEGORY_CONSULTANCY = "industrial_consultancy"
CATEGORY_ROUTINE = "routine_testing_vetting"
CATEGORY_ADMIN = "administrative_or_grant"

ADMIN_EXACT_TITLES = {
    "iitkgp_sub", "icmr_attend", "icmr_pencool", "all labs", "me dnc", "travel grant", "iciam 23",
    "iit - pal", "ishan vikas", "pratichhya", "anrf_travel grant", "legal opinion",
}
_ADMIN_PATTERNS = [
    r"\btravel grants?\b",
    r"\bfor attending\b",
    r"\bforeign travel\b",
    r"\b(international|national|regional) (conference|symposium|workshop)\b",
    r"^\d+(st|nd|rd|th)\b.*\b(conference|symposium|congress)\b",
    r"\bsymposium\b",
    r"^workshop\b",
    r"\bactivation workshop\b",
    r"\btraining programmes? and (national )?workshop\b",
    r"\blegal opinion\b",
    r"\bsummer school\b",
    r"\bshort[- ]term course\b",
]
_ROUTINE_PATTERNS = [
    r"^(phase[- ]?[ivx0-9]+\s*:\s*)?(technical\s+)?(proof[- ]checking|vetting|checking of|testing of|calibration|"
    r"inspection of|third[- ]party (inspection|verification|checking)|tests? (of|on))\b",
    r"^(phase[- ]?[ivx0-9]+\s*:\s*)?(structural |design |drawing )?(vetting|checking|proof[- ]checking) of\b",
    r"^design checking\b",
    r"\bproof[- ]checking\b",
    r"\bvetting of\b",
    r"\bqualification tests?\b",
]
_CONSULTANCY_PATTERNS = [
    r"\bconsultancy\b",
    r"\bconsultation\b",
    r"\bdetailed project report\b",
    r"\bdpr\b",
    r"\btechno[- ](economic[- ])?feasibility\b",
    r"\bdesign review\b",
    r"\badvisory support\b",
    r"\bexpert opinion\b",
]
_RESEARCH_GUARD = re.compile(r"\b(development|developing|design and development|novel|investigation|modell?ing)\b")


def classify_project(title: Optional[str], sponsor: Optional[str] = None, description: Optional[str] = None) -> str:
    """
    Assigns one of four labels. Order of precedence: administrative > routine testing/vetting >
    consultancy > sponsored research. A title starting with research verbs ('Development of',
    'Investigation of', ...) is never labelled routine testing even if it mentions 'testing'.
    """
    t = (title or "").strip()
    tl = t.lower()
    if not tl:
        return CATEGORY_SPONSORED
    if tl in ADMIN_EXACT_TITLES or re.fullmatch(r"[A-Z0-9]+_[A-Z0-9_]+", t):
        return CATEGORY_ADMIN
    if any(re.search(p, tl) for p in _ADMIN_PATTERNS):
        # 'workshop shed', 'old workshop' are buildings, not events
        if not re.search(r"\bworkshop (shed|building)\b|\bold workshop\b|\bpeb workshop\b", tl):
            return CATEGORY_ADMIN
    research_like = bool(_RESEARCH_GUARD.search(tl.split(":")[0][:60]))
    if not research_like and any(re.search(p, tl) for p in _ROUTINE_PATTERNS):
        return CATEGORY_ROUTINE
    if any(re.search(p, tl) for p in _CONSULTANCY_PATTERNS):
        return CATEGORY_CONSULTANCY
    return CATEGORY_SPONSORED
