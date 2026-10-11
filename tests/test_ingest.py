import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import ingest


def test_fetch_labels_limits_by_label_document(monkeypatch):
    brand_labels = {
        "results": [
            {
                "id": "label-1",
                "indications_and_usage": ["Use A"],
                "warnings": ["Warn A"],
            },
            {
                "id": "label-2",
                "dosage_and_administration": ["Dose B"],
                "adverse_reactions": ["Reaction B"],
            },
        ]
    }
    generic_labels = {
        "results": [
            {"id": "label-2", "warnings": ["duplicate"]},
            {"id": "label-3", "warnings": ["Warn C"]},
        ]
    }

    def fake_get_json(url, params=None):
        if 'openfda.brand_name:"Dupixent"' in params["search"]:
            return brand_labels
        return generic_labels

    monkeypatch.setattr(ingest, "get_json", fake_get_json)

    rows = ingest.fetch_labels("Dupixent", "dupilumab", limit=2)

    assert {row["label_id"] for row in rows} == {"label-1", "label-2"}
    assert {row["section"] for row in rows} == {
        "indications",
        "warnings",
        "dosage",
        "adverse_reactions",
    }
    assert all(row["drug"] == "Dupixent" for row in rows)


def test_write_tables_replaces_existing_data(tmp_path, monkeypatch):
    db_path = tmp_path / "medinsight.duckdb"
    monkeypatch.setattr(ingest, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ingest, "DB_PATH", db_path)

    ingest.write_tables(
        adverse_events=[{"drug": "A", "report_id": "1", "receivedate": "20240101", "serious": "1", "reaction": "X", "medicinalproduct": "A"}],
        trials=[{"drug": "A", "nct_id": "NCT1", "brief_title": "t1", "overall_status": "RECRUITING", "phase": "PHASE3", "conditions": "c", "last_update_posted": "2024-01-01"}],
        labels=[{"drug": "A", "label_id": "L1", "section": "warnings", "text": "w"}],
    )

    ingest.write_tables(adverse_events=[], trials=[], labels=[])

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        assert {name for (name,) in conn.execute("SHOW TABLES").fetchall()} == {
            "adverse_events",
            "trials",
            "labels",
        }
        assert conn.execute("SELECT COUNT(*) FROM adverse_events").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM trials").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 0
    finally:
        conn.close()
