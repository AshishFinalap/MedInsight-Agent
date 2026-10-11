# MedInsight-Agent

Local-first prototype for ingesting public FDA + ClinicalTrials.gov data into DuckDB.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` in `.env` before later agent work.

## Ingest public data

```bash
python scripts/ingest.py
```

This creates/replaces the following DuckDB tables in `data/medinsight.duckdb`:

- `adverse_events`
- `trials`
- `labels`

## Quick verification

```bash
python -c "import duckdb; c=duckdb.connect('data/medinsight.duckdb', read_only=True); print(c.execute('SHOW TABLES').fetchall()); print(c.execute('SELECT drug, COUNT(*) AS reports FROM adverse_events GROUP BY drug ORDER BY drug').fetchall()); print(c.execute('SELECT COUNT(*) FROM trials').fetchone()); print(c.execute('SELECT drug, section FROM labels LIMIT 10').fetchall()); c.close()"
```
