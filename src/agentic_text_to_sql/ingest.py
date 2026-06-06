"""`python -m agentic_text_to_sql.ingest` — Extract-Load step (the "EL" before dbt's "T").

Downloads a PINNED revision of the UCI *Online Retail II* dataset from the Hugging Face Hub
and bulk-loads it into the Snowflake RAW schema. dbt then cleans + models it into the star
schema (the "T").

Provenance / license: UCI Online Retail II (id 502), CC BY 4.0 — real UK/EU online-retail
invoices, 2009-12 .. 2011-12. We pin the Hub repo AND commit sha so every run loads
byte-identical data -> the eval gold set stays deterministic.

Loads as all-TEXT into RAW (the data is dirty: blank customers, '?' descriptions,
cancellations). dbt staging does the casting + cleaning. Connects with the BUILD role; the
agent never uses these credentials.
"""

from __future__ import annotations

import pandas as pd
from huggingface_hub import hf_hub_download
from snowflake.connector.pandas_tools import write_pandas

from agentic_text_to_sql.db import snowflake as sf

# --- Pinned source (do not bump casually; it changes the gold set) ----------
HF_REPO_ID = "attik/Online-Retail-II-UCI"
HF_FILENAME = "online_retail_II.csv"
HF_REVISION = "0b3df9f6148646fa3e490141472dd76c191480ef"

RAW_TABLE = "ONLINE_RETAIL"
# CSV header order: Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country
COLUMNS = [
    "invoice",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "price",
    "customer_id",
    "country",
]


def _download() -> str:
    print(f"downloading {HF_REPO_ID}@{HF_REVISION[:8]} :: {HF_FILENAME} ...")
    path = hf_hub_download(
        repo_id=HF_REPO_ID, repo_type="dataset", filename=HF_FILENAME, revision=HF_REVISION
    )
    print(f"  cached at {path}")
    return path


def _load(csv_path: str) -> int:
    # All-text, empty strings preserved (not NaN) to mirror a raw text load.
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, na_filter=False)
    df.columns = COLUMNS  # rename to snake_case in CSV order

    con = sf.connect(schema=sf.RAW_SCHEMA)
    try:
        # quote_identifiers=False -> Snowflake stores unquoted (UPPERCASE) column names, which
        # the dbt source references case-insensitively.
        ok, _chunks, nrows, _ = write_pandas(
            con,
            df,
            table_name=RAW_TABLE,
            database=sf.database(),
            schema=sf.RAW_SCHEMA,
            auto_create_table=True,
            overwrite=True,
            quote_identifiers=False,
        )
        if not ok:
            raise RuntimeError("write_pandas reported failure")
    finally:
        con.close()
    return int(nrows)


def main() -> None:
    path = _download()
    n = _load(path)
    print(f"ingest OK -> {sf.database()}.{sf.RAW_SCHEMA}.{RAW_TABLE}: {n:,} rows loaded.")


if __name__ == "__main__":
    main()
