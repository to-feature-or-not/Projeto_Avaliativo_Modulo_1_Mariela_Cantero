"""0_criar_banco.py - Reads 0_criar_banco.sql and applies it to PostgreSQL.

The SQL file uses the __DB_NAME__ placeholder, replaced at runtime with
POSTGRES_CONFIG["dbname"] from config.py. This keeps the database name
defined in a single place.
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine, text

import config
from banco import _build_url

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# --- Constants (change here if the file is ever renamed) ---
SQL_FILE = "0_criar_banco.sql"
DB_NAME_PLACEHOLDER = "__DB_NAME__"


def execute_block(conn, sql_block: str) -> None:
    """Split a SQL block by ';', strip comment lines, execute what remains."""
    for chunk in sql_block.split(";"):
        lines = [
            line for line in chunk.splitlines()
            if not line.strip().startswith("--")
        ]
        statement = "\n".join(lines).strip()
        if statement:
            first = statement.splitlines()[0][:70]
            logger.info("  running: %s...", first)
            conn.execute(text(statement))


def main() -> None:
    db_name = config.POSTGRES_CONFIG["dbname"]

    sql_path = Path(__file__).with_name(SQL_FILE)
    if not sql_path.exists():
        raise FileNotFoundError(f"File not found: {sql_path}")

    # Read the SQL script and substitute the database-name placeholder
    sql_content = sql_path.read_text(encoding="utf-8")
    sql_content = sql_content.replace(DB_NAME_PLACEHOLDER, db_name)

    # Split around the psql meta-command "\c <db_name>"
    parts = sql_content.split(f"\\c {db_name}")
    script_create_db = parts[0]
    script_create_tables = parts[1] if len(parts) > 1 else ""

    # 1) Connect to 'postgres' and create the project database
    logger.info("Creating database '%s'...", db_name)
    admin_db = config.POSTGRES_CONFIG["admin_db"]
    admin_engine = create_engine(_build_url(admin_db), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        execute_block(conn, script_create_db)

    # 2) Connect to the new database and create the 8 tables
    logger.info("Creating the 8 tables (Raw + Silver)...")
    db_engine = create_engine(_build_url(db_name))
    with db_engine.begin() as conn:
        execute_block(conn, script_create_tables)

    logger.info("Database '%s' and tables created successfully!", db_name)


if __name__ == "__main__":
    main()