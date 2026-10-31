"""Phase 1 - Extract and load the Raw layer.

Pipeline:
  1. Download the source .zip from Google Drive (skipped if already present).
  2. Extract the four CSVs into data/raw/ (flattening any internal folders).
  3. TRUNCATE + bulk-load each CSV into its raw_* table using Postgres COPY.

Idempotent (TRUNCATE + skip-if-exists) and resilient (per-table try/except).
"""

import logging
import sys
import os
import zipfile
from pathlib import Path

import gdown

import config
from banco import get_engine, truncate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    stream=sys.stdout, 
    force=True 
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1) Download
# ---------------------------------------------------------------------------
def download_zip() -> Path:
    """Download the source zip if not already on disk."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    if config.ZIP_PATH.exists() and not config.FORCE_DOWNLOAD:
        logger.info(
            "Zip already present at %s - skipping download "
            "(set FORCE_DOWNLOAD=true in config.py to re-download)",
            config.ZIP_PATH,
        )
        return config.ZIP_PATH
    
    if config.ZIP_PATH.exists() and config.FORCE_DOWNLOAD:
        logger.info("FORCE_DOWNLOAD=true - re-downloading zip.")
        try:
            config.ZIP_PATH.unlink() 
            logger.info("Zip antigo apagado com sucesso!")
        except Exception as e:
            logger.error("Erro ao apagar o zip antigo (ele pode estar aberto no WinRAR): %s", e)
            raise e 
        
    PLACEHOLDER_IDS = {"", "your_drive_file_id_here"}

    if config.DRIVE_FILE_ID in PLACEHOLDER_IDS:
        raise RuntimeError(
            "DRIVE_FILE_ID não configurado. Edite o arquivo .env "
            "(veja o modelo em .env.example) e preencha o ID real do Google Drive."
        )

    logger.info("Downloading zip from Google Drive (id=%s)...", config.DRIVE_FILE_ID)

    # If running via run_pipeline, hide the bar (quiet=True)
    is_pipeline = os.environ.get("PIPELINE_MODE") == "1"

    gdown.download(id=config.DRIVE_FILE_ID, output=str(config.ZIP_PATH), quiet=is_pipeline)

    if not config.ZIP_PATH.exists():
        raise RuntimeError(
            f"The download process ended, but the file was not found at {config.ZIP_PATH}. "
            "This usually happens if the Google Drive link is private or the DRIVE_FILE_ID is wrong. "
            "Ensure the file is shared as 'Anyone with the link'."
        )
    return config.ZIP_PATH


# ---------------------------------------------------------------------------
# 2) Extraction
# ---------------------------------------------------------------------------
def extract_zip(zip_path: Path) -> None:
    """Extract all zip members into DATA_DIR, flattening internal folders."""
    logger.info("Checking zip contents -> %s", config.DATA_DIR)
    with zipfile.ZipFile(zip_path) as zf:
        members = zf.namelist()
        logger.info("  Zip contains: %s", members)
        extracted = skipped = 0
        for member in members:
            filename = Path(member).name
            if not filename or member.endswith("/"):
                continue
            target = config.DATA_DIR / filename

            if target.exists() and target.stat().st_size > 0 and not config.FORCE_DOWNLOAD:
                logger.info("  Skipping %s (already extracted)", filename)
                skipped += 1
                continue

            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
            logger.info("  Extracted %s", filename)
            extracted += 1

        logger.info("  Summary: %d extracted, %d skipped", extracted, skipped)
        if extracted == 0 and skipped == 0:
            raise RuntimeError(f"No files were extracted from {zip_path}")


# ---------------------------------------------------------------------------
# 3) Load into Raw
# ---------------------------------------------------------------------------
def load_raw_table(engine, table: str, csv_path: Path) -> None:
    """Stream-load one CSV into its raw table using Postgres COPY (fast)."""
    logger.info("Loading %s from %s", table, csv_path.name)
    try:
        with engine.begin() as conn:
            truncate(conn, table)

        raw_conn = engine.raw_connection()
        try:
            with open(csv_path, "rb") as f:
                cursor = raw_conn.cursor()
                sql = f"COPY {table} FROM STDIN WITH (FORMAT csv, DELIMITER '{config.CSV_SEPARATOR}', HEADER true, ENCODING '{config.CSV_ENCODING}')"
                cursor.copy_expert(sql, f)
            raw_conn.commit()
            logger.info("OK   %-15s (COPY completed)", table)
        finally:
            raw_conn.close()
    except Exception as exc:
        logger.exception("FAIL %-15s %s", table, exc)
        raise


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def main() -> None:
    zip_path = download_zip()
    extract_zip(zip_path)

    engine = get_engine()

    for entity, info in config.TABLES.items():
        csv_path = config.DATA_DIR / info["csv"]
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing CSV: {csv_path}")
        load_raw_table(engine, info["raw"], csv_path)

    logger.info("Phase 1 (Raw) completed")


if __name__ == "__main__":
    main()