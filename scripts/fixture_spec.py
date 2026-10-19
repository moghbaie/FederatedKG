"""Hand-authored specification of the synthetic FederatedKG fixtures.

Everything here is SYNTHETIC. UniProt accessions and PSI-MI terms are real identifiers
(verified 2026-10-19) used only as normalized vocabulary; interactions, hypotheses and
observations are invented and must never be attributed to any real researcher.
"""

NORMALIZATION = "fkg-norm/1.0"
CREATED_AT = "2026-01-01T00:00:00Z"
FIXTURE_VERSION = "1"

# UniProt accession -> primary gene symbol (verified reviewed entries).
PROTEINS = {
    "P00533": "EGFR", "P62993": "GRB2", "P12931": "SRC", "P31749": "AKT1",
    "P42345": "MTOR", "P07900": "HSP90AA1", "P60709": "ACTB", "P04406": "GAPDH",
    "P63104": "YWHAZ", "P62258": "YWHAE", "P12004": "PCNA", "P24941": "CDK2",
    "P04637": "TP53", "Q13547": "HDAC1", "P35222": "CTNNB1", "P11021": "HSPA5",
    "P67775": "PPP2CA", "Q09472": "EP300", "P55072": "VCP", "P25786": "PSMA1",
    "Q99459": "CDC5L", "O14744": "PRMT5", "P0CG48": "UBC", "O60885": "BRD4",
    "Q93034": "CUL5", "Q15370": "ELOB", "Q15369": "ELOC", "Q13951": "CBFB",
    "Q9HC16": "APOBEC3G", "Q9UHD2": "TBK1", "Q14653": "IRF3", "Q7Z434": "MAVS",
    "O95786": "RIGI", "P42224": "STAT1",
    "P0DTC2": "S", "P0DTC9": "N", "P0DTC5": "M", "P0DTC3": "ORF3a",
    "P0DTC6": "ORF6", "P0DTC8": "ORF8",
}
SYMBOL_TO_ACC = {v: k for k, v in PROTEINS.items()}

# PSI-MI interaction detection methods (verified via EBI OLS).
METHODS = {
    "MI:0427": "Identification by mass spectrometry",
    "MI:0004": "affinity chromatography technology",
    "MI:0019": "coimmunoprecipitation",
    "MI:0676": "tandem affinity purification",
    "MI:1314": "proximity-dependent biotin identification",
    "MI:0007": "anti tag coimmunoprecipitation",
    "MI:0018": "two hybrid",
}

# Local controlled topic vocabulary (urn:fkg:topic:<id>).
TOPICS = {
    "proteomics": "Proteomics",
    "mass_spectrometry": "Mass spectrometry",
    "quantitative_proteomics": "Quantitative proteomics",
    "peptide_identification": "Peptide identification",
    "interactomics": "Interactomics",
    "protein_complexes": "Protein complexes",
    "ap_ms": "Affinity purification mass spectrometry",
    "proximity_labeling": "Proximity labeling",
    "host_pathogen": "Host-pathogen interactions",
    "systems_biology": "Systems biology",
    "innate_immunity": "Innate immunity",
    "single_cell_proteomics": "Single-cell proteomics",
    "protein_turnover": "Protein turnover",
    "chromatin_regulation": "Chromatin regulation",
    "antiviral_signaling": "Antiviral signaling",
}

PERSONAS = {
    "persona_a": {
        "display_name": "Persona A",
        "theme": "Mass spectrometry and proteomics",
        "verified": True,
        "inspiration": {"name": "Matthias Mann", "doi": "10.1038/nature01511",
                        "citation": "Aebersold R, Mann M. Mass spectrometry-based proteomics. Nature. 2003."},
        "published_topics": ["proteomics", "mass_spectrometry", "quantitative_proteomics", "protein_complexes"],
        "private_topics": ["single_cell_proteomics"],
        "proteins": ["EGFR", "GRB2", "SRC", "AKT1", "MTOR", "HSP90AA1", "ACTB", "GAPDH", "YWHAZ",
                     "YWHAE", "PCNA", "CDK2", "TP53", "HDAC1", "CTNNB1", "HSPA5", "PPP2CA", "EP300"],
        # Source labels that differ from the normalized symbol (exercise the mapping table).
        "label_aliases": {"EGFR": "ErbB1", "HSP90AA1": "HSP90-alpha", "YWHAZ": "14-3-3 zeta"},
        "methods": ["MI:0427", "MI:0004"],
        "interactions": [
            ("EGFR", "GRB2"), ("EGFR", "SRC"), ("GRB2", "SRC"), ("AKT1", "MTOR"),
            ("AKT1", "HSP90AA1"), ("HSP90AA1", "CDK2"), ("CDK2", "PCNA"), ("PCNA", "HDAC1"),
            ("TP53", "EP300"), ("TP53", "HDAC1"), ("CTNNB1", "EP300"), ("YWHAZ", "YWHAE"),
            ("YWHAZ", "AKT1"), ("PPP2CA", "AKT1"), ("HSPA5", "HSP90AA1"), ("ACTB", "GAPDH"),
            ("CANARY", "EGFR"), ("CANARY", "MTOR"),
        ],
    },
    "persona_b": {
        "display_name": "Persona B",
        "theme": "Protein identification and analytical proteomics",
        "verified": True,
        "inspiration": {"name": "John R. Yates III", "doi": "10.1038/85686",
                        "citation": "Washburn MP, Wolters D, Yates JR 3rd. Large-scale analysis of the yeast proteome "
                                    "by multidimensional protein identification technology. Nat Biotechnol. 2001."},
        "published_topics": ["proteomics", "mass_spectrometry", "peptide_identification", "interactomics"],
        "private_topics": ["protein_turnover"],
        "proteins": ["ACTB", "GAPDH", "HSP90AA1", "HSPA5", "PCNA", "CDK2", "VCP", "PSMA1", "CDC5L",
                     "PRMT5", "YWHAZ", "TP53", "HDAC1", "UBC", "BRD4", "EGFR", "PPP2CA", "YWHAE"],
        "label_aliases": {"HSP90AA1": "HSP90", "HSPA5": "BiP", "VCP": "p97"},
        "methods": ["MI:0427", "MI:0019"],
        "interactions": [
            ("ACTB", "GAPDH"), ("HSP90AA1", "HSPA5"), ("CDK2", "PCNA"), ("VCP", "PSMA1"),
            ("VCP", "UBC"), ("PSMA1", "UBC"), ("CDC5L", "PRMT5"), ("YWHAZ", "YWHAE"),
            ("TP53", "HDAC1"), ("BRD4", "HDAC1"), ("EGFR", "YWHAZ"), ("PPP2CA", "YWHAZ"),
            ("CDK2", "TP53"), ("HSP90AA1", "CDK2"), ("CANARY", "VCP"), ("CANARY", "PRMT5"),
        ],
    },
    "persona_c": {
        "display_name": "Persona C",
        "theme": "Protein interaction networks and affinity purification",
        "verified": True,
        "inspiration": {"name": "Anne-Claude Gingras", "doi": "10.1038/nmeth.1541",
                        "citation": "Choi H, et al. SAINT: probabilistic scoring of affinity purification-mass "
                                    "spectrometry data. Nat Methods. 2011."},
        "published_topics": ["interactomics", "protein_complexes", "ap_ms", "proximity_labeling", "mass_spectrometry"],
        "private_topics": ["chromatin_regulation"],
        "proteins": ["PPP2CA", "YWHAZ", "YWHAE", "HDAC1", "BRD4", "EP300", "CTNNB1", "GRB2", "SRC",
                     "TP53", "CDC5L", "PRMT5", "UBC", "VCP", "CUL5", "ELOB", "ELOC", "CBFB"],
        "label_aliases": {"PPP2CA": "PP2A-C", "EP300": "p300", "ELOB": "Elongin B", "ELOC": "Elongin C"},
        "methods": ["MI:0676", "MI:1314", "MI:0007"],
        "interactions": [
            ("PPP2CA", "YWHAZ"), ("YWHAZ", "YWHAE"), ("HDAC1", "BRD4"), ("BRD4", "EP300"),
            ("EP300", "CTNNB1"), ("GRB2", "SRC"), ("TP53", "EP300"), ("CDC5L", "PRMT5"),
            ("VCP", "UBC"), ("CUL5", "ELOB"), ("ELOB", "ELOC"), ("CUL5", "CBFB"),
            ("TP53", "HDAC1"), ("SRC", "YWHAE"), ("CANARY", "PPP2CA"), ("CANARY", "CUL5"),
        ],
    },
    "persona_d": {
        "display_name": "Persona D",
        "theme": "Host-pathogen interactions and systems biology",
        "verified": True,
        "inspiration": {"name": "Nevan Krogan", "doi": "10.1038/s41586-020-2286-9",
                        "citation": "Gordon DE, et al. A SARS-CoV-2 protein interaction map reveals targets for "
                                    "drug repurposing. Nature. 2020."},
        "published_topics": ["interactomics", "host_pathogen", "systems_biology", "protein_complexes"],
        "private_topics": ["antiviral_signaling"],
        "proteins": ["CUL5", "ELOB", "ELOC", "CBFB", "APOBEC3G", "UBC", "BRD4", "PRMT5", "TBK1", "IRF3",
                     "MAVS", "RIGI", "STAT1", "HDAC1", "S", "N", "M", "ORF3a", "ORF6", "ORF8"],
        "label_aliases": {"S": "Spike", "N": "Nucleocapsid", "M": "Membrane protein", "RIGI": "DDX58"},
        "methods": ["MI:0007", "MI:0004", "MI:0018"],
        "interactions": [
            ("CUL5", "ELOB"), ("ELOB", "ELOC"), ("CUL5", "CBFB"), ("APOBEC3G", "CUL5"),
            ("TBK1", "IRF3"), ("MAVS", "RIGI"), ("MAVS", "TBK1"), ("STAT1", "IRF3"),
            ("BRD4", "HDAC1"), ("PRMT5", "UBC"), ("N", "BRD4"), ("M", "TBK1"),
            ("ORF6", "STAT1"), ("ORF3a", "UBC"), ("ORF8", "HDAC1"), ("S", "CBFB"),
            ("CANARY", "MAVS"), ("CANARY", "S"),
        ],
    },
    "persona_e": {
        "display_name": "Persona E",
        "theme": "Unverified visitor (authorization testing only)",
        "verified": False,
        "inspiration": None,
        "published_topics": ["proteomics"],
    },
}

# Synthetic hypotheses (3 per graph). Text is deliberately marked SYNTHETIC.
HYPOTHESES = {
    "persona_a": ["GRB2-SRC association increases under growth-factor stimulation",
                  "HSP90AA1 stabilizes CDK2 during S phase",
                  "YWHAZ sequesters AKT1 in quiescent cells"],
    "persona_b": ["VCP-PSMA1 co-elution reflects a stable degradation intermediate",
                  "CDC5L-PRMT5 peptides co-vary across fractions",
                  "HSPA5 abundance predicts HSP90AA1 identification depth"],
    "persona_c": ["PPP2CA-YWHAZ proximity depends on scaffold availability",
                  "CUL5-ELOB-ELOC forms a core module across baits",
                  "BRD4-EP300 proximity is chromatin-state dependent"],
    "persona_d": ["Viral ORF6 dampens STAT1-dependent signaling",
                  "CUL5-CBFB recruitment is hijacked by a viral factor",
                  "N protein association with BRD4 alters host transcription"],
}

# Synthetic observations. effect: increases|decreases|binds. context=None -> missing information.
# `expected` is the hand-assigned ground-truth label for the pair it belongs to (see PAIRS below).
_CTX1 = {"cell_type": "HEK293T", "treatment": "EGF 100ng/ml", "timepoint": "15min"}
_CTX2 = {"cell_type": "HeLa", "treatment": "untreated", "timepoint": "0min"}
_CTX3 = {"cell_type": "A549", "treatment": "infection MOI 1", "timepoint": "24h"}
_CTX4 = {"cell_type": "Calu-3", "treatment": "infection MOI 1", "timepoint": "24h"}

OBSERVATIONS = {
    "persona_a": [
        ("o1", "GRB2", "increases", "SRC", _CTX1, 0.8),
        ("o2", "GRB2", "decreases", "SRC", _CTX1, 0.6),   # fabricated contradiction with o1
        ("o3", "AKT1", "increases", "MTOR", _CTX1, 0.9),
        ("o4", "AKT1", "increases", "MTOR", _CTX1, 0.7),  # supports o3
        ("o5", "YWHAZ", "decreases", "AKT1", _CTX1, 0.5),
        ("o6", "YWHAZ", "increases", "AKT1", _CTX2, 0.5), # opposite, different context
        ("o7", "HSP90AA1", "increases", "CDK2", None, 0.4),
        ("o8", "HSP90AA1", "decreases", "CDK2", _CTX2, 0.4),  # missing context on o7
    ],
    "persona_b": [
        ("o1", "VCP", "binds", "PSMA1", _CTX2, 0.8),
        ("o2", "VCP", "binds", "PSMA1", _CTX2, 0.7),
        ("o3", "CDC5L", "increases", "PRMT5", _CTX2, 0.6),
        ("o4", "CDC5L", "decreases", "PRMT5", _CTX2, 0.6),
        ("o5", "HSPA5", "increases", "HSP90AA1", _CTX1, 0.5),
        ("o6", "HSPA5", "decreases", "HSP90AA1", _CTX2, 0.5),
    ],
    "persona_c": [
        ("o1", "PPP2CA", "binds", "YWHAZ", _CTX2, 0.9),
        ("o2", "PPP2CA", "binds", "YWHAZ", _CTX2, 0.8),
        ("o3", "BRD4", "increases", "EP300", _CTX2, 0.6),
        ("o4", "BRD4", "decreases", "EP300", _CTX2, 0.5),
        ("o5", "CUL5", "increases", "CBFB", None, 0.4),
        ("o6", "CUL5", "decreases", "CBFB", _CTX2, 0.4),
    ],
    "persona_d": [
        ("o1", "ORF6", "decreases", "STAT1", _CTX3, 0.8),
        ("o2", "ORF6", "increases", "STAT1", _CTX3, 0.5),
        ("o3", "N", "binds", "BRD4", _CTX3, 0.7),
        ("o4", "N", "binds", "BRD4", _CTX3, 0.6),
        ("o5", "M", "decreases", "TBK1", _CTX3, 0.6),
        ("o6", "M", "increases", "TBK1", _CTX4, 0.6),
        ("o7", "ORF3a", "increases", "UBC", None, 0.3),
    ],
}

# Ground-truth local contradiction labels for observation pairs sharing (s, p-family, o).
LOCAL_PAIR_LABELS = {
    "persona_a": {("o1", "o2"): "contradictory_candidate", ("o3", "o4"): "supporting",
                  ("o5", "o6"): "context_mismatch", ("o7", "o8"): "insufficient_information"},
    "persona_b": {("o1", "o2"): "supporting", ("o3", "o4"): "contradictory_candidate",
                  ("o5", "o6"): "context_mismatch"},
    "persona_c": {("o1", "o2"): "supporting", ("o3", "o4"): "contradictory_candidate",
                  ("o5", "o6"): "insufficient_information"},
    "persona_d": {("o1", "o2"): "contradictory_candidate", ("o3", "o4"): "supporting",
                  ("o5", "o6"): "context_mismatch"},
}

GRAPH_PERSONAS = ["persona_a", "persona_b", "persona_c", "persona_d"]
