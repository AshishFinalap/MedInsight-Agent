import os
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from medinsight.config import (  # noqa: E402
    DATA_DIR,
    DB_PATH,
    DRUGS,
    EVENTS_PER_DRUG,
    LABELS_PER_DRUG,
    OPENFDA_BASE,
    REQUEST_TIMEOUT,
    TRIALS_BASE,
    TRIALS_PER_DRUG,
)

load_dotenv(ROOT / ".env")
OPENFDA_API_KEY = os.getenv("OPENFDA_API_KEY", "").strip()

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "MedInsightAgent/0.1 (educational project)"})


def get_json(url, params=None):
    """Fetch JSON; treat a valid no-results response as empty."""
    query = dict(params or {})
    if OPENFDA_API_KEY and url.startswith(OPENFDA_BASE):
        query.setdefault("api_key", OPENFDA_API_KEY)

    response = SESSION.get(url, params=query, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


def fetch_adverse_events(brand, generic, limit):
    rows = []
    for field, term in (("patient.drug.medicinalproduct", brand), ("patient.drug.openfda.generic_name", generic)):
        if len(rows) >= limit:
            break

        remaining = limit - len(rows)
        data = get_json(
            f"{OPENFDA_BASE}/drug/event.json",
            params={
                "search": f'{field}:"{term}"',
                "limit": min(remaining, 100),
            },
        )
        for event in data.get("results", []):
            reactions = event.get("patient", {}).get("reaction", []) or [{}]
            drugs = event.get("patient", {}).get("drug", []) or [{}]
            for reaction in reactions:
                rows.append(
                    {
                        "drug": brand,
                        "report_id": str(event.get("safetyreportid", "")),
                        "receivedate": event.get("receivedate"),
                        "serious": event.get("serious"),
                        "reaction": reaction.get("reactionmeddrapt"),
                        "medicinalproduct": drugs[0].get("medicinalproduct"),
                    }
                )
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break

    return rows[:limit]


def fetch_trials(brand, generic, limit):
    rows = []
    page_token = None

    while len(rows) < limit:
        params = {
            "query.term": f"{brand} OR {generic}",
            "pageSize": min(100, limit - len(rows)),
            "format": "json",
        }
        if page_token:
            params["pageToken"] = page_token

        data = get_json(TRIALS_BASE, params=params)
        studies = data.get("studies", [])
        if not studies:
            break

        for study in studies:
            protocol = study.get("protocolSection", {})
            identification = protocol.get("identificationModule", {})
            status_module = protocol.get("statusModule", {})
            design_module = protocol.get("designModule", {})
            conditions_module = protocol.get("conditionsModule", {})
            rows.append(
                {
                    "drug": brand,
                    "nct_id": identification.get("nctId"),
                    "brief_title": identification.get("briefTitle"),
                    "overall_status": status_module.get("overallStatus"),
                    "phase": ", ".join(design_module.get("phases", []) or []),
                    "conditions": ", ".join(conditions_module.get("conditions", []) or []),
                    "last_update_posted": status_module.get("lastUpdatePostDateStruct", {}).get("date"),
                }
            )
            if len(rows) >= limit:
                break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return rows[:limit]


def fetch_labels(brand, generic, limit):
    rows = []
    seen_labels = set()
    section_keys = {
        "indications_and_usage": "indications",
        "warnings": "warnings",
        "dosage_and_administration": "dosage",
        "adverse_reactions": "adverse_reactions",
    }

    for field, term in (("openfda.brand_name", brand), ("openfda.generic_name", generic)):
        remaining = limit - len(seen_labels)
        if remaining <= 0:
            break

        data = get_json(
            f"{OPENFDA_BASE}/drug/label.json",
            params={
                "search": f'{field}:"{term}"',
                "limit": min(remaining, 100),
            },
        )

        for label in data.get("results", []):
            label_id = label.get("id") or str(label.get("openfda", {}))
            if label_id in seen_labels:
                continue

            seen_labels.add(label_id)

            for api_key, section_name in section_keys.items():
                values = label.get(api_key) or []
                for value in values:
                    text = " ".join(str(value).split())
                    if text:
                        rows.append(
                            {
                                "drug": brand,
                                "label_id": label_id,
                                "section": section_name,
                                "text": text,
                            }
                        )

            if len(seen_labels) >= limit:
                break

    return rows


def _to_frame(rows, columns):
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=columns)


def write_tables(adverse_events, trials, labels):
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    adverse_df = _to_frame(
        adverse_events,
        ["drug", "report_id", "receivedate", "serious", "reaction", "medicinalproduct"],
    )
    trials_df = _to_frame(
        trials,
        ["drug", "nct_id", "brief_title", "overall_status", "phase", "conditions", "last_update_posted"],
    )
    labels_df = _to_frame(labels, ["drug", "label_id", "section", "text"])

    conn = duckdb.connect(str(DB_PATH))
    try:
        conn.begin()
        conn.register("adverse_df", adverse_df)
        conn.register("trials_df", trials_df)
        conn.register("labels_df", labels_df)
        conn.execute("CREATE OR REPLACE TABLE adverse_events AS SELECT * FROM adverse_df")
        conn.execute("CREATE OR REPLACE TABLE trials AS SELECT * FROM trials_df")
        conn.execute("CREATE OR REPLACE TABLE labels AS SELECT * FROM labels_df")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_ingestion():
    adverse_rows = []
    trial_rows = []
    label_rows = []

    for brand, generic in DRUGS.items():
        adverse_rows.extend(fetch_adverse_events(brand, generic, EVENTS_PER_DRUG))
        trial_rows.extend(fetch_trials(brand, generic, TRIALS_PER_DRUG))
        label_rows.extend(fetch_labels(brand, generic, LABELS_PER_DRUG))

    write_tables(adverse_rows, trial_rows, label_rows)

    print(f"adverse_events rows: {len(adverse_rows)}")
    print(f"trials rows: {len(trial_rows)}")
    print(f"labels rows: {len(label_rows)}")
    print(f"database: {DB_PATH}")


if __name__ == "__main__":
    run_ingestion()
