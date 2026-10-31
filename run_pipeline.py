"""run_pipeline.py - Orchestrates the entire data pipeline."""

import logging
import subprocess
import sys
import time
import os

from sqlalchemy import text

import config
from banco import get_engine

# Setup logging to both console and file
log_format = "%(asctime)s | %(levelname)-7s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.FileHandler(config.OUTPUT_DIR / "pipeline.log", mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SCRIPTS = [
    "0_criar_banco.py",
    "1_extrair.py",
    "2_transformar.py",
]


def run_script(script_name: str) -> None:
    """Runs a Python script and captures its output into the logger."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("STARTING: %s", script_name)
    logger.info("=" * 60)
    
    start_time = time.time()

    env = os.environ.copy()
    env["PIPELINE_MODE"] = "1" 

    # Popen allows us to read the output line by line in real-time
    process = subprocess.Popen(
        [sys.executable, script_name],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env
    )

    # Read and log each line printed by the child script
    if process.stdout is not None:
        for line in process.stdout:
            logger.info("[%s] %s", script_name, line.strip())
            
    process.wait()

    if process.returncode != 0:
        logger.error("FAILED: %s. Pipeline aborted.", script_name)
        sys.exit(1)

    elapsed = time.time() - start_time
    logger.info("FINISHED: %s in %.2f seconds", script_name, elapsed)


def print_summary() -> None:
    """Connects to the database and prints the row count for all tables."""
    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE SUMMARY - ROW COUNTS")
    logger.info("=" * 60)
    
    engine = get_engine()
    
    try:
        with engine.connect() as conn:
            logger.info("--- RAW LAYER ---")
            for entity, info in config.TABLES.items():
                table = info["raw"]
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                logger.info("%-20s : %d rows", table, count)
                
            logger.info("")
            logger.info("--- SILVER LAYER ---")
            for entity, info in config.TABLES.items():
                table = info["silver"]
                count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                logger.info("%-20s : %d rows", table, count)
                
        logger.info("=" * 60)
        logger.info("Pipeline completed successfully. Check 'outputs/pipeline.log' for details.")
        logger.info("You can now open '3_analise.ipynb' to view the Gold layer.")
        
    except Exception as e:
        logger.error("Could not generate summary: %s", e)


def main() -> None:
    logger.info("🚀 STARTING FULL PIPELINE EXECUTION")
    
    for script in SCRIPTS:
        run_script(script)
        
    print_summary()


if __name__ == "__main__":
    main()