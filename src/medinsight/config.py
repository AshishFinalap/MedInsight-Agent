from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "medinsight.duckdb"

# Seed queries for the prototype, not a claim of current
# Sanofi ownership or endorsement.
DRUGS = {
    "Dupixent": "dupilumab",
    "Lantus": "insulin glargine",
    "Plavix": "clopidogrel",
    "Lovenox": "enoxaparin",
    "Aubagio": "teriflunomide",
}

OPENFDA_BASE = "https://api.fda.gov"
TRIALS_BASE = "https://clinicaltrials.gov/api/v2/studies"

EVENTS_PER_DRUG = 500
LABELS_PER_DRUG = 5
TRIALS_PER_DRUG = 100
REQUEST_TIMEOUT = 30
