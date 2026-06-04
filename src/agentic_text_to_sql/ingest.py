"""`python -m agentic_text_to_sql.ingest` — Extract-Load step (the "EL" before dbt's "T").

Downloads a PINNED revision of the UCI *Online Retail II* dataset from the Hugging Face Hub
and bulk-COPYs it into a `raw` schema in Postgres. dbt then cleans + models it into the
star schema (the "T").

Provenance / license (interview-defensible):
- Upstream: UCI Machine Learning Repository, "Online Retail II" (id 502), CC BY 4.0.
  Real UK/EU online-retail invoices, 2009-12-01 .. 2011-12-09.
- We pin the Hub repo AND commit sha, so every run/CI loads byte-identical data -> the eval
  gold set stays deterministic even though the source is real, messy, third-party data.

Why a separate `raw` schema (not dbt seeds):
- ~1M rows / ~95 MB is far past what dbt seeds are for. Real pipelines extract-load outside
  dbt, then transform inside it. The agent's read-only role is granted on `public` only, so
  it can never see `raw` — only the curated marts.

Connects as the SUPERUSER (write access) — a BUILD step, like dbt. The agent never uses
these credentials; it only ever connects with the read-only role.
"""

from __future__ import annotations

import os

import psycopg
from huggingface_hub import hf_hub_download

# --- Pinned source (do not bump casually; it changes the gold set) ----------
HF_REPO_ID = "attik/Online-Retail-II-UCI"
HF_FILENAME = "online_retail_II.csv"
HF_REVISION = "0b3df9f6148646fa3e490141472dd76c191480ef"
HF_REPO_TYPE = "dataset"

RAW_SCHEMA = "raw"
RAW_TABLE = "online_retail"

# CSV header order: Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country
# Loaded as TEXT — the data is dirty (blank customer ids, '?' descriptions, cancellations).
# dbt staging does the casting + cleaning, which is exactly the skill this repo shows.
RAW_COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
]


def _superuser_dsn() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_SUPERUSER", "postgres")
    pw = os.environ.get("POSTGRES_SUPERUSER_PASSWORD", "postgres")
    db = os.environ.get("POSTGRES_DB", "warehouse")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def _download() -> str:
    print(f"downloading {HF_REPO_ID}@{HF_REVISION[:8]} :: {HF_FILENAME} ...")
    path = hf_hub_download(
        repo_id=HF_REPO_ID,
        repo_type=HF_REPO_TYPE,
        filename=HF_FILENAME,
        revision=HF_REVISION,
    )
    print(f"  cached at {path}")
    return path


def _load(csv_path: str) -> int:
    cols = ", ".join(f"{c} text" for c in RAW_COLUMNS)
    collist = ", ".join(RAW_COLUMNS)
    with psycopg.connect(_superuser_dsn(), autocommit=True) as conn:
        conn.execute("SET client_encoding TO 'UTF8'")
        # Idempotent: rebuild the raw table from scratch each run.
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
        conn.execute(f"DROP TABLE IF EXISTS {RAW_SCHEMA}.{RAW_TABLE}")
        conn.execute(f"CREATE TABLE {RAW_SCHEMA}.{RAW_TABLE} ({cols})")
        copy_sql = (
            f"COPY {RAW_SCHEMA}.{RAW_TABLE} ({collist}) "
            f"FROM STDIN WITH (FORMAT csv, HEADER true)"
        )
        with (
            conn.cursor() as cur,
            cur.copy(copy_sql) as copy,
            open(csv_path, "rb") as fh,
        ):
            while chunk := fh.read(1 << 16):
                copy.write(chunk)
        row = conn.execute(f"SELECT count(*) FROM {RAW_SCHEMA}.{RAW_TABLE}").fetchone()
        return int(row[0]) if row else 0


def main() -> None:
    path = _download()
    n = _load(path)
    print(f"ingest OK -> {RAW_SCHEMA}.{RAW_TABLE}: {n:,} rows loaded.")


if __name__ == "__main__":
    main()
