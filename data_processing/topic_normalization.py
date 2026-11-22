"""
Non-destructive research topic normalization and 3-tier taxonomy mapper (Phase 2 / Phase C).

Preserves every original `topic_name` row and relationship while populating:
- canonical_topic_name
- domain_name (Tier 1)
- area_name (Tier 2)
- is_generic_root (OpenAlex Level-0 broad discipline tags)
- is_noisy_artifact (Wikipedia parenthetical disambiguation suffixes, sentence fragments, unsplit lists)
"""
import re
from typing import Dict, Iterable, Optional, Set, Tuple

# 1. Acronym and Alias Canonical Mappings
ACRONYM_AND_ALIAS_MAP: Dict[str, str] = {
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "natural language processing (nlp)": "Natural Language Processing",
    "iot": "Internet of Things",
    "internet of things": "Internet of Things",
    "internet of things (iot)": "Internet of Things",
    "industrial iot": "Industrial Internet of Things",
    "iiot": "Industrial Internet of Things",
    "cfd": "Computational Fluid Dynamics",
    "computational fluid dynamics": "Computational Fluid Dynamics",
    "computational fluid dynamics (cfd)": "Computational Fluid Dynamics",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "machine-learning": "Machine Learning",
    "ai": "Artificial Intelligence",
    "artificial intelligence": "Artificial Intelligence",
    "artificial intelligence (ai)": "Artificial Intelligence",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "deep-learning": "Deep Learning",
    "cv": "Computer Vision",
    "computer vision": "Computer Vision",
    "vlsi": "Very Large Scale Integration (VLSI)",
    "very large scale integration": "Very Large Scale Integration (VLSI)",
    "vlsi design": "Very Large Scale Integration (VLSI)",
    "uav": "Unmanned Aerial Vehicles",
    "uavs": "Unmanned Aerial Vehicles",
    "unmanned aerial vehicle": "Unmanned Aerial Vehicles",
    "unmanned aerial vehicles": "Unmanned Aerial Vehicles",
    "fem": "Finite Element Method",
    "finite element method": "Finite Element Method",
    "finite-element method": "Finite Element Method",
    "finite element": "Finite Element Method",
    "finite-element": "Finite Element Method",
    "fea": "Finite Element Analysis",
    "finite element analysis": "Finite Element Analysis",
    "gnn": "Graph Neural Networks",
    "gnns": "Graph Neural Networks",
    "graph neural network": "Graph Neural Networks",
    "graph neural networks": "Graph Neural Networks",
    "llm": "Large Language Models",
    "llms": "Large Language Models",
    "large language model": "Large Language Models",
    "large language models": "Large Language Models",
    "rag": "Retrieval-Augmented Generation",
    "retrieval augmented generation": "Retrieval-Augmented Generation",
    "retrieval-augmented generation": "Retrieval-Augmented Generation",
    "hci": "Human-Computer Interaction",
    "human computer interaction": "Human-Computer Interaction",
    "human-computer interaction": "Human-Computer Interaction",
    "cps": "Cyber-Physical Systems",
    "cyber physical systems": "Cyber-Physical Systems",
    "cyber-physical systems": "Cyber-Physical Systems",
    "cyberphysical systems": "Cyber-Physical Systems",
    "cyber physical system": "Cyber-Physical Systems",
    "cyber-physical system": "Cyber-Physical Systems",
    "biomechanics": "Biomechanics",
    "bio mechanics": "Biomechanics",
    "bio-mechanics": "Biomechanics",
    "cognitive neuropsychology": "Cognitive Neuropsychology",
    "cognitive neuro-psychology": "Cognitive Neuropsychology",
    "mems": "Micro-Electro-Mechanical Systems (MEMS)",
    "micro electro mechanical systems": "Micro-Electro-Mechanical Systems (MEMS)",
    "micro-electro-mechanical systems": "Micro-Electro-Mechanical Systems (MEMS)",
    "gis": "Geographic Information Systems",
    "geographic information system": "Geographic Information Systems",
    "geographic information systems": "Geographic Information Systems",
    "ann": "Artificial Neural Networks",
    "artificial neural network": "Artificial Neural Networks",
    "artificial neural networks": "Artificial Neural Networks",
    "cnn": "Convolutional Neural Networks",
    "convolutional neural network": "Convolutional Neural Networks",
    "convolutional neural networks": "Convolutional Neural Networks",
    # Spelling & punctuation fixes identified in audit
    "structuress": "Structures",
    "tansportation": "Transportation",
    "6g": "6G Wireless Communications",
    "- 6g": "6G Wireless Communications",
    "decision-making": "Decision Making",
    "decision making": "Decision Making",
    "ground water": "Groundwater",
    "groundwater": "Groundwater",
    "micro-grid": "Microgrids",
    "microgrid": "Microgrids",
    "microgrids": "Microgrids",
    "multi-objective optimization": "Multi-Objective Optimization",
    "multi–objective optimization": "Multi-Objective Optimization",
    "multiobjective optimization": "Multi-Objective Optimization",
    "image-processing": "Image Processing",
    "image processing": "Image Processing",
    "non-destructive testing": "Non-Destructive Testing",
    "nondestructive testing": "Non-Destructive Testing",
    "phase-change material": "Phase Change Materials",
    "phase change material": "Phase Change Materials",
    "phase change materials": "Phase Change Materials",
    "bio-energy": "Bioenergy",
    "bioenergy": "Bioenergy",
    "bio-fuels": "Biofuels",
    "biofuel": "Biofuels",
    "biofuels": "Biofuels",
    "co-design": "Hardware-Software Co-Design",
    "codesign": "Hardware-Software Co-Design",
    "electro-spinning": "Electrospinning",
    "electrospinning": "Electrospinning",
    "geo-polymer": "Geopolymers",
    "geopolymer": "Geopolymers",
    "geopolymers": "Geopolymers",
    "micro-machining": "Micromachining",
    "micromachining": "Micromachining",
    "micro-structural": "Microstructure",
    "microstructural": "Microstructure",
    "nano-composites": "Nanocomposites",
    "nanocomposite": "Nanocomposites",
    "nanocomposites": "Nanocomposites",
    "sub-surface": "Subsurface Hydrology",
    "subsurface": "Subsurface Hydrology",
}

# 2. Broad OpenAlex Level-0 Root Concepts
GENERIC_ROOT_TOPICS: Set[str] = {
    "computer science",
    "engineering",
    "chemistry",
    "physics",
    "materials science",
    "biology",
    "mathematics",
    "environmental science",
    "medicine",
    "geology",
    "geography",
    "psychology",
    "business",
    "economics",
    "political science",
    "sociology",
    "philosophy",
    "history",
    "art",
    "quantum mechanics",
    "organic chemistry",
}

# Wikipedia parenthetical disambiguation domains that indicate OpenAlex concept-tag noise
WIKIPEDIA_DISAMBIG_SUFFIX_RE = re.compile(
    r"\s*\((grammar|psychology|behavioral psychology|linguistics|philosophy|mathematics|logic|"
    r"computer science|programming|statistics|physics|chemistry|biology|economics|sociology|law|"
    r"music|architecture|engineering|geology|medicine|botany|zoology|ecology|genetics|biochemistry|"
    r"finance|management|marketing|politics|telecom|electronics|optics|thermodynamics|mechanics|"
    r"acoustics|astronomy|cartography|typography|rail|aviation|maritime|military|sports|games|"
    r"journal|newspaper|magazine|film|novel|album|song|band|company|organization|software)\)\s*$",
    flags=re.IGNORECASE,
)


def build_plural_and_punct_canonical_map(all_topic_names: Iterable[str]) -> Dict[str, str]:
    """
    Builds a lookup mapping lowercased topic names across singular/plural pairs and
    hyphen/space/punctuation variant groups to a unified canonical display name, without
    merging semantically ambiguous concepts.
    """
    lower_to_originals: Dict[str, list] = {}
    for name in all_topic_names:
        cleaned = re.sub(r"^\s*[-•*&/.,:;]+\s*", "", (name or "").strip())
        k = cleaned.lower()
        if k:
            lower_to_originals.setdefault(k, []).append(cleaned)

    # First, group by alphanumeric key (collapsing hyphen vs space variants)
    alnum_to_lowers: Dict[str, list] = {}
    for k in lower_to_originals:
        # Do not collapse topics with parenthetical qualifiers into bare words via alphanumeric stripping
        if "(" in k or ")" in k:
            continue
        nk = re.sub(r"[^a-z0-9]+", "", k)
        if len(nk) > 3:
            alnum_to_lowers.setdefault(nk, []).append(k)

    canonical_by_lower: Dict[str, str] = {}

    def _format_display(text: str) -> str:
        text = re.sub(r"^\s*[-•*&/.,:;]+\s*", "", text.strip())
        if text.islower() or text.isupper():
            return text.title()
        return text[0].upper() + text[1:] if text else text

    for nk, lowers in alnum_to_lowers.items():
        if len(lowers) > 1:
            # Prefer clean multi-word or hyphenated version without leading punctuation
            best_low = sorted(
                lowers,
                key=lambda x: (
                    bool(re.match(r"^[a-z0-9]", x)),
                    "-" in x or " " in x,
                    len(x),
                ),
                reverse=True,
            )[0]
            disp = _format_display(lower_to_originals[best_low][0])
            for l in lowers:
                canonical_by_lower[l] = disp

    # Next, link singular/plural pairs (prefer plural form for countable research topics like Sensors, Biofuels)
    all_lowers = sorted(lower_to_originals.keys())
    lower_set = set(all_lowers)
    for k in all_lowers:
        if len(k) <= 4 or "(" in k or ")" in k:
            continue
        plural = None
        if k + "s" in lower_set and not k.endswith("ss"):
            plural = k + "s"
        elif k.endswith("y") and (k[:-1] + "ies") in lower_set:
            plural = k[:-1] + "ies"
        if plural:
            target = canonical_by_lower.get(plural) or _format_display(lower_to_originals[plural][0])
            canonical_by_lower[k] = target
            canonical_by_lower[plural] = target

    return canonical_by_lower


# 3. Three-Tier Taxonomy Rules: Domain (Tier 1) -> Research Area (Tier 2) -> Canonical Topic (Tier 3)
TAXONOMY_RULES: list = [
    # (Domain, Research Area, keyword_regex)
    (
        "Computer Science & Artificial Intelligence",
        "Natural Language Processing & Information Retrieval",
        r"\b(natural language|nlp|language model|llm|retrieval|text mining|speech|sentiment|dialogue|machine translation|question answering|information extraction|summarization)\b",
    ),
    (
        "Computer Science & Artificial Intelligence",
        "Computer Vision & Image Processing",
        r"\b(computer vision|image processing|object detection|segmentation|face recognition|video|biometric|hyperspectral|medical imaging|pattern recognition|optical flow|super-resolution)\b",
    ),
    (
        "Computer Science & Artificial Intelligence",
        "Machine Learning & Data Science",
        r"\b(machine learning|deep learning|neural network|reinforcement learning|graph neural|federated learning|transfer learning|generative ai|artificial intelligence|data mining|big data|recommend|clustering|classification|anomaly detection|explainable ai|trustworthy ai|analytics|decision making|decision support)\b",
    ),
    (
        "Computer Science & Artificial Intelligence",
        "Cybersecurity, Cryptography & Systems",
        r"\b(cryptograph|cyber|security|blockchain|intrusion|malware|privacy|authentication|side-channel|puf|cloud computing|distributed system|operating system|compiler|formal verification|software engineering|database|iot|internet of things|edge computing|fog computing)\b",
    ),
    (
        "Computer Science & Artificial Intelligence",
        "Algorithms, Networks & Human-Computer Interaction",
        r"\b(algorithm|graph theory|combinator|automata|human-computer|hci|social network|wireless sensor network|computer network|sdn|5g|6g)\b",
    ),
    (
        "Electrical, Electronics & Communication Engineering",
        "VLSI, Semiconductor Devices & Nanoelectronics",
        r"\b(vlsi|cmos|mosfet|finfet|semiconductor|fpga|asic|integrated circuit|memristor|spintronics|nanoelectronics|system-on-chip|network-on-chip|cad for vlsi|hemt|gan|sic)\b",
    ),
    (
        "Electrical, Electronics & Communication Engineering",
        "Signal Processing, Communications & Photonics",
        r"\b(signal processing|mimo|ofdm|antenna|microwave|rf|radar|optical fiber|photonic|plasmonic|laser|terahertz| millimeter wave|telecommunication|channel estimation|coding theory|modulation|acoustic)\b",
    ),
    (
        "Electrical, Electronics & Communication Engineering",
        "Power Systems, Power Electronics & Control",
        r"\b(power system|power electronic|smart grid|microgrid|hvdc|inverter|converter|motor drive|electric vehicle|renewable energy integration|control system|nonlinear control|robust control|adaptive control|sliding mode|pid|state estimation|fault diagnosis|high voltage|insulation)\b",
    ),
    (
        "Mechanical, Aerospace & Manufacturing Engineering",
        "Thermofluids, Combustion & Aerodynamics",
        r"\b(fluid dynamics|cfd|turbulence|heat transfer|combustion|aerodynamic|hypersonic|supersonic|microfluidics|nanofluid|two-phase flow|boiling|condensation|refrigeration|air conditioning|cryogenic|gas turbine|propulsion|wind tunnel|boundary layer|vortex)\b",
    ),
    (
        "Mechanical, Aerospace & Manufacturing Engineering",
        "Robotics, Autonomous Systems & Mechanics",
        r"\b(robot|uav|unmanned aerial|autonomous vehicle|mechatronics|manipulator|kinematics|vibration|rotor|fracture mechanics|contact mechanics|tribology|wear|lubrication|fatigue|finite element|fem|fea|composite structure|plates and shells|wave propagation|metamaterial)\b",
    ),
    (
        "Mechanical, Aerospace & Manufacturing Engineering",
        "Manufacturing, Machining & Industrial Engineering",
        r"\b(additive manufacturing|3d printing|welding|machining|micromachining|casting|forming|laser processing|supply chain|operations research|logistics|scheduling|quality control|ergonomics|reliability|maintenance|industry 4\.0|digital twin)\b",
    ),
    (
        "Materials, Metallurgical & Chemical Engineering",
        "Advanced Materials, Nanomaterials & Metallurgy",
        r"\b(nanomaterial|nanocomposite|nanoparticle|nanotube|graphene|2d material|thin film|polymer|hydrogel|elastomer|rubber|ceramic|alloy|steel|titanium|corrosion|electrodeposition|coating|microstructure|phase transformation|crystallography|sintering|powder metallurgy|biomaterial|shape memory|piezoelectric|magnetocaloric)\b",
    ),
    (
        "Materials, Metallurgical & Chemical Engineering",
        "Chemical Processes, Catalysis & Energy Storage",
        r"\b(catalys|electrocatalys|photocatalys|reaction engineering|distillation|adsorption|membrane|desalination|reverse osmosis|nanofiltration|mass transfer|process control|process intensification|battery|lithium-ion|supercapacitor|fuel cell|electrode|hydrogen|electrochemistry|pyrolysis|gasification|biofuel|biodiesel|biorefinery)\b",
    ),
    (
        "Civil, Infrastructure, Earth & Environmental Sciences",
        "Structural, Geotechnical & Transportation Engineering",
        r"\b(concrete|reinforced concrete|steel structure|bridge|seismic|earthquake|structural health|pavement|asphalt|bitumen|traffic|transportation|highway|railway|soil mechanics|geotechnical|foundation|slope stability|landslide|tunnel|rock mechanics|mining|blasting)\b",
    ),
    (
        "Civil, Infrastructure, Earth & Environmental Sciences",
        "Water Resources, Environmental & Climate Sciences",
        r"\b(hydrology|groundwater|watershed|flood|irrigation|hydraulics|river|coastal|ocean|monsoon|climate|atmospheric|aerosol|remote sensing|gis|wastewater|sewage|sludge|water treatment|air pollution|solid waste|bioremediation|heavy metal|arsenic|carbon sequestration|sustainability|environmental)\b",
    ),
    (
        "Civil, Infrastructure, Earth & Environmental Sciences",
        "Geology, Geophysics & Architecture",
        r"\b(geolog|geophysic|tectonic|mineral|ore|petrolog|sediment|stratigraph|paleontolog|gravity|magnetic|urban planning|architecture|housing|heritage|landscape)\b",
    ),
    (
        "Biosciences, Bioengineering, Agriculture & Medical Technology",
        "Biotechnology, Molecular Biology & Bioinformatics",
        r"\b(protein|enzyme|dna|rna|gene|genomic|transcriptom|proteom|crispr|cell biology|microbiolog|bacteria|virus|cancer|tumor|leukemia|tuberculosis|malaria|immunolog|vaccine|drug delivery|drug discovery|pharmacolog|neuroscience|bioinformatics|systems biology|metabolic|fermentation)\b",
    ),
    (
        "Biosciences, Bioengineering, Agriculture & Medical Technology",
        "Biomedical Engineering, Biosensors & Healthcare",
        r"\b(biomedical|biosensor|point-of-care|lab-on-a-chip|microfluidic diagnostic|tissue engineering|regenerative medicine|prosthetic|implant|biomechanics|eeg|ecg|medical device|telemedicine|public health|epidemiology)\b",
    ),
    (
        "Biosciences, Bioengineering, Agriculture & Medical Technology",
        "Agriculture, Food Engineering & Rural Technology",
        r"\b(agricultur|crop|rice|wheat|soil fertility|fertilizer|pest|horticultur|aquaculture|fishery|food processing|food packaging|dairy|post-harvest|drying|extrusion|probiotic|nutrition)\b",
    ),
    (
        "Basic Sciences (Physics, Chemistry & Mathematics)",
        "Chemistry & Molecular Sciences",
        r"\b(organic synthesis|asymmetric synthesis|total synthesis|organometallic|coordination chemistry|supramolecular|metal-organic framework|mof|photochemistry|spectroscopy|nmr|mass spectrometry|quantum chemistry|molecular dynamics|density functional theory|dft|click chemistry|heterocyclic|fluorine|carbohydrate|peptide)\b",
    ),
    (
        "Basic Sciences (Physics, Chemistry & Mathematics)",
        "Physics, Quantum Science & Astrophysics",
        r"\b(quantum|superconduct|Bose-einstein|condensed matter|topological insulator|magnetism|skyrmion|astrophysics|cosmology|gravitational|dark matter|plasma physics|nuclear physics|high energy physics|particle physics|nonlinear optics|ultrafast|soliton|general relativity)\b",
    ),
    (
        "Basic Sciences (Physics, Chemistry & Mathematics)",
        "Mathematics, Statistics & Scientific Computing",
        r"\b(differential equation|partial differential|numerical analysis|algebra|Lie group|topology|number theory|functional analysis|operator theory|probability|stochastic|time series|bayesian|statistical inference|biostatistics|fuzzy|optimization|linear programming|convex|game theory|dynamical system)\b",
    ),
    (
        "Humanities, Social Sciences, Management & Law",
        "Management, Economics, Finance & Law",
        r"\b(finance|financial|banking|stock market|corporate governance|accounting|marketing|consumer|human resource|organizational|entrepreneurship|innovation|intellectual property|patent|copyright|competition law|environmental law|constitutional|human rights|arbitration|criminal law|cyber law|econometrics|macroeconomics|microeconomics|development economics|public policy|health economics)\b",
    ),
    (
        "Humanities, Social Sciences, Management & Law",
        "Humanities, Psychology & Social Sciences",
        r"\b(literature|linguistics|phonetics|cognitive|psychology|mindfulness|well-being|sociology|gender|caste|migration|urbanization|history|philosophy|ethics|sanskrit|indian knowledge|education|pedagogy|communication studies)\b",
    ),
]

# Representative parent topic names (if present in research_topics) for each Research Area
AREA_PARENT_TOPIC_CANDIDATES: Dict[str, list] = {
    "Natural Language Processing & Information Retrieval": ["Natural language processing", "Information retrieval"],
    "Computer Vision & Image Processing": ["Computer vision", "Image processing"],
    "Machine Learning & Data Science": ["Machine learning", "Artificial intelligence", "Deep learning"],
    "Cybersecurity, Cryptography & Systems": ["Cryptography", "Computer security", "Internet of Things"],
    "Algorithms, Networks & Human-Computer Interaction": ["Algorithm", "Computer network", "Human–computer interaction"],
    "VLSI, Semiconductor Devices & Nanoelectronics": ["VLSI", "Semiconductor", "Optoelectronics"],
    "Signal Processing, Communications & Photonics": ["Signal processing", "Telecommunications", "Optics"],
    "Power Systems, Power Electronics & Control": ["Power electronics", "Control theory", "Smart grid"],
    "Thermofluids, Combustion & Aerodynamics": ["Fluid dynamics", "Heat transfer", "Computational fluid dynamics"],
    "Robotics, Autonomous Systems & Mechanics": ["Robotics", "Mechanics", "Finite element method"],
    "Manufacturing, Machining & Industrial Engineering": ["Manufacturing", "Operations research", "Supply chain"],
    "Advanced Materials, Nanomaterials & Metallurgy": ["Materials science", "Nanotechnology", "Composite material"],
    "Chemical Processes, Catalysis & Energy Storage": ["Catalysis", "Chemical engineering", "Electrochemistry"],
    "Structural, Geotechnical & Transportation Engineering": ["Structural engineering", "Geotechnical engineering", "Mining engineering"],
    "Water Resources, Environmental & Climate Sciences": ["Environmental science", "Hydrology", "Remote sensing"],
    "Geology, Geophysics & Architecture": ["Geology", "Geophysics", "Architecture"],
    "Biotechnology, Molecular Biology & Bioinformatics": ["Biotechnology", "Molecular biology", "Bioinformatics"],
    "Biomedical Engineering, Biosensors & Healthcare": ["Biomedical engineering", "Biosensor", "Medicine"],
    "Agriculture, Food Engineering & Rural Technology": ["Agriculture", "Food science", "Aquaculture"],
    "Chemistry & Molecular Sciences": ["Chemistry", "Organic chemistry", "Physical chemistry"],
    "Physics, Quantum Science & Astrophysics": ["Physics", "Quantum mechanics", "Condensed matter physics"],
    "Mathematics, Statistics & Scientific Computing": ["Mathematics", "Statistics", "Mathematical optimization"],
    "Management, Economics, Finance & Law": ["Economics", "Business", "Law"],
    "Humanities, Psychology & Social Sciences": ["Psychology", "Sociology", "Philosophy"],
}


# Fallback mapping from IIT Kharagpur department codes to (Domain, Research Area)
DEPT_CODE_TAXONOMY_FALLBACK: Dict[str, Tuple[str, str]] = {
    "CS": ("Computer Science & Artificial Intelligence", "Machine Learning & Data Science"),
    "AI": ("Computer Science & Artificial Intelligence", "Machine Learning & Data Science"),
    "CD": ("Computer Science & Artificial Intelligence", "Machine Learning & Data Science"),
    "EC": ("Electrical, Electronics & Communication Engineering", "Signal Processing, Communications & Photonics"),
    "EE": ("Electrical, Electronics & Communication Engineering", "Power Systems, Power Electronics & Control"),
    "AT": ("Electrical, Electronics & Communication Engineering", "VLSI, Semiconductor Devices & Nanoelectronics"),
    "GS": ("Electrical, Electronics & Communication Engineering", "Signal Processing, Communications & Photonics"),
    "ME": ("Mechanical, Aerospace & Manufacturing Engineering", "Thermofluids, Combustion & Aerodynamics"),
    "AE": ("Mechanical, Aerospace & Manufacturing Engineering", "Thermofluids, Combustion & Aerodynamics"),
    "IM": ("Mechanical, Aerospace & Manufacturing Engineering", "Manufacturing, Machining & Industrial Engineering"),
    "OE": ("Mechanical, Aerospace & Manufacturing Engineering", "Robotics, Autonomous Systems & Mechanics"),
    "CH": ("Materials, Metallurgical & Chemical Engineering", "Chemical Processes, Catalysis & Energy Storage"),
    "MT": ("Materials, Metallurgical & Chemical Engineering", "Advanced Materials, Nanomaterials & Metallurgy"),
    "MS": ("Materials, Metallurgical & Chemical Engineering", "Advanced Materials, Nanomaterials & Metallurgy"),
    "RT": ("Materials, Metallurgical & Chemical Engineering", "Advanced Materials, Nanomaterials & Metallurgy"),
    "CR": ("Mechanical, Aerospace & Manufacturing Engineering", "Thermofluids, Combustion & Aerodynamics"),
    "CE": ("Civil, Infrastructure, Earth & Environmental Sciences", "Structural, Geotechnical & Transportation Engineering"),
    "MI": ("Civil, Infrastructure, Earth & Environmental Sciences", "Structural, Geotechnical & Transportation Engineering"),
    "AR": ("Civil, Infrastructure, Earth & Environmental Sciences", "Geology, Geophysics & Architecture"),
    "ID": ("Civil, Infrastructure, Earth & Environmental Sciences", "Geology, Geophysics & Architecture"),
    "GG": ("Civil, Infrastructure, Earth & Environmental Sciences", "Geology, Geophysics & Architecture"),
    "CL": ("Civil, Infrastructure, Earth & Environmental Sciences", "Water Resources, Environmental & Climate Sciences"),
    "ES": ("Civil, Infrastructure, Earth & Environmental Sciences", "Water Resources, Environmental & Climate Sciences"),
    "WM": ("Civil, Infrastructure, Earth & Environmental Sciences", "Water Resources, Environmental & Climate Sciences"),
    "BT": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Biotechnology, Molecular Biology & Bioinformatics"),
    "BS": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Biotechnology, Molecular Biology & Bioinformatics"),
    "BM": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Biomedical Engineering, Biosensors & Healthcare"),
    "MM": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Biomedical Engineering, Biosensors & Healthcare"),
    "AG": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Agriculture, Food Engineering & Rural Technology"),
    "RD": ("Biosciences, Bioengineering, Agriculture & Medical Technology", "Agriculture, Food Engineering & Rural Technology"),
    "CY": ("Basic Sciences (Physics, Chemistry & Mathematics)", "Chemistry & Molecular Sciences"),
    "PH": ("Basic Sciences (Physics, Chemistry & Mathematics)", "Physics, Quantum Science & Astrophysics"),
    "MA": ("Basic Sciences (Physics, Chemistry & Mathematics)", "Mathematics, Statistics & Scientific Computing"),
    "HS": ("Humanities, Social Sciences, Management & Law", "Humanities, Psychology & Social Sciences"),
    "BMG": ("Humanities, Social Sciences, Management & Law", "Management, Economics, Finance & Law"),
    "VG": ("Humanities, Social Sciences, Management & Law", "Management, Economics, Finance & Law"),
    "IP": ("Humanities, Social Sciences, Management & Law", "Management, Economics, Finance & Law"),
    "RJ": ("Humanities, Social Sciences, Management & Law", "Management, Economics, Finance & Law"),
    "RE": ("Electrical, Electronics & Communication Engineering", "Power Systems, Power Electronics & Control"),
    "ET": ("Humanities, Social Sciences, Management & Law", "Humanities, Psychology & Social Sciences"),
}


def normalize_single_topic(
    raw_name: str,
    plural_punct_map: Dict[str, str],
    primary_dept_code: Optional[str] = None,
) -> Tuple[str, str, str, bool, bool]:
    """
    Returns:
        (canonical_topic_name, domain_name, area_name, is_generic_root, is_noisy_artifact)
    """
    raw = (raw_name or "").strip()
    cleaned = re.sub(r"^\s*[-•*&/.,:;]+\s*", "", raw).strip()
    low = cleaned.lower()

    is_generic = low in GENERIC_ROOT_TOPICS

    # Flag noisy artifacts: Wikipedia disambiguation parentheticals, sentence-length strings (>65 chars),
    # unsplit ';' / ':' strings, or leading punctuation fragments.
    is_wiki_disambig = bool(WIKIPEDIA_DISAMBIG_SUFFIX_RE.search(cleaned))
    is_noisy = bool(
        is_wiki_disambig
        or len(raw) > 65
        or ";" in raw
        or ":" in raw
        or "etc." in low
        or raw[:1] in ("-", "&", "•", "*")
    )

    # IMPORTANT: Do not merge ambiguous Wikipedia disambiguated topics (e.g. "Action (physics)" vs "Action")
    # automatically; keep the disambiguated string unless it is in the explicit alias map.
    if low in ACRONYM_AND_ALIAS_MAP:
        canonical = ACRONYM_AND_ALIAS_MAP[low]
    elif low in plural_punct_map:
        canonical = plural_punct_map[low]
        canonical = ACRONYM_AND_ALIAS_MAP.get(canonical.lower(), canonical)
    else:
        if cleaned.islower():
            canonical = cleaned.title()
        elif cleaned:
            canonical = cleaned[0].upper() + cleaned[1:]
        else:
            canonical = raw

    # Assign 3-tier taxonomy (Domain -> Research Area -> Canonical Topic)
    search_text = f"{canonical} {raw}".lower()
    domain_name = None
    area_name = None
    for dom, area, pattern in TAXONOMY_RULES:
        if re.search(pattern, search_text):
            domain_name = dom
            area_name = area
            break

    if not domain_name and primary_dept_code and primary_dept_code in DEPT_CODE_TAXONOMY_FALLBACK:
        domain_name, area_name = DEPT_CODE_TAXONOMY_FALLBACK[primary_dept_code]

    if not domain_name:
        domain_name = "Interdisciplinary & General Engineering Sciences"
        area_name = "General & Cross-Disciplinary Research"

    return canonical, domain_name, area_name, is_generic, is_noisy
