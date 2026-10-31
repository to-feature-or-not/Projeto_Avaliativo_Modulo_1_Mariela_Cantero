"""Phase 2 - Raw -> Silver.

- Converts text to DECIMAL ('1.234,56') and DATE ('DD/MM/YYYY').
- Computes total_value and duration_days on silver_trip.
- Enforces referential integrity: child rows with unknown id_trip are dropped.
- Idempotent: TRUNCATE before load.
- Fast insert via psycopg2.extras.execute_values (not pandas.to_sql).
"""

import logging
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from sqlalchemy import text
from psycopg2.extras import execute_values

import config
from banco import get_engine


logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

ZERO = Decimal("0")

def clean_payment_type(text):
    """
    Normalizes the payment type to the values observed in the dataset.

    WARNING: This mapping covers ONLY the empirical cases found in the
    2025_Pagamento.csv file (DIÁRIAS, PASSAGEM, RESTITUIÇÃO, Related
    service: insurance). Unforeseen values are returned as they are
    (after clean_mojibake), and the Gold layer analysis handles them via
    GROUP BY.

    Singular cases (e.g., "Diária") were not observed in the 2025 dataset
    and therefore are not handled here. If the source changes, this mapping
    must be reviewed.
    """
    if pd.isna(text): return text
    text = str(text)
    if "DI" in text and "RIA" in text: return "DIÁRIAS"
    if "RESTITUI" in text: return "RESTITUIÇÃO"
    if "Servi" in text and "seguro" in text: return "Serviço correlato: seguro"
    if "PASSAGEM" in text: return "PASSAGEM"
    return text


def clean_mojibake(text):
    """Attempts to revert mojibake and removes replacement characters."""
    if text is None or pd.isna(text):
        return text
    
    text = str(text)
    
    # 1. Tries to fix the encoding (UTF-8 read as Latin-1)
    try:
        text = text.encode('latin1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass # If it fails, keeps the original text
        
    # 2. Replaces the error character (U+FFFD) with an empty string
    text = text.replace('\ufffd', '').replace('ï¿½', '')
    
    # 3. Manual corrections for specific words that lost letters
    # (Based on the Q7 visualization)
    text = text.replace("SeguranAa", "Segurança")
    text = text.replace("PAblica", "Pública")
    text = text.replace("AeronAutica", "Aeronáutica")
    text = text.replace("ExArcito", "Exército")
    text = text.replace("GestAo", "Gestão")
    text = text.replace("InovaAAo", "Inovação")
    text = text.replace("MinistArio", "Ministério")
    text = text.replace("RelaAAes", "Relações")
    text = text.replace("vAnculo", "vínculo")
    text = text.replace("PecuAria", "Pecuária")
    
    return text.strip()

# ---------- Converters ----------

def to_decimal(value) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None

    has_comma = "," in s
    has_dot = "." in s

    if has_comma and has_dot:
        s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        s = s.replace(",", ".")

    try:
        val = Decimal(s)
        if val < 0:
            logger.warning("  Negative value found and set to zero: %s", val)
            return ZERO
        return val
    except (InvalidOperation, ValueError):
        return None


def to_date(value):
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except (ValueError, TypeError):
        return None


def to_int(value) -> int | None:
    if value is None or pd.isna(value):
        return None
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


# ---------- Bulk insert ----------

def bulk_insert(engine, table: str, df: pd.DataFrame, columns: list) -> int:
    """Fast bulk insert using psycopg2.extras.execute_values."""
    if df.empty:
        return 0
    clean = df[columns].astype(object).where(pd.notna(df[columns]), None)
    rows = clean.values.tolist()

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        cols_sql = ", ".join(f'"{c}"' for c in columns)
        sql = f'INSERT INTO {table} ({cols_sql}) VALUES %s'
        execute_values(cur, sql, rows, page_size=1000)
        raw_conn.commit()
        return len(rows)
    finally:
        raw_conn.close()


# ---------- Per-table transformations ----------

def transform_trip(df: pd.DataFrame) -> pd.DataFrame:
    out = df.rename(columns=config.TRIP_COLUMN_MAP).copy()

    before = len(out)
    out = out.drop_duplicates(subset=["id_trip"], keep="first")
    if len(out) < before:
        logger.warning("  %d duplicate id_trip dropped (kept first)", before - len(out))

    for col in ("daily_allowance", "ticket_cost", "refund_amount", "other_expenses"):
        out[col] = out[col].apply(to_decimal)
    out["start_date"] = out["start_date"].apply(to_date)
    out["end_date"] = out["end_date"].apply(to_date)
    out["agency_name"] = out["agency_name"].fillna("Desconhecido").replace("", "Desconhecido")

    out["total_value"] = (
        out["daily_allowance"].fillna(ZERO)
        + out["ticket_cost"].fillna(ZERO)
        + out["other_expenses"].fillna(ZERO)
        - out["refund_amount"].fillna(ZERO)
    )

    def _duration(row):
        si, ei = row["start_date"], row["end_date"]
        if pd.isna(si) or pd.isna(ei):
            return None
        return (ei - si).days + 1

    out["duration_days"] = out.apply(_duration, axis=1)
    return out[[
        "id_trip", "proposal_number", "status", "urgent_trip",
        "agency_code", "agency_name", "traveler_name", "position",
        "start_date", "end_date", "destinations", "purpose",
        "daily_allowance", "ticket_cost", "refund_amount",
        "other_expenses", "total_value", "duration_days",
    ]]


def _filter_by_trip(df: pd.DataFrame, valid_ids: set) -> pd.DataFrame:
    before = len(df)
    out = df[df["identificador_do_processo_de_viagem"].isin(valid_ids)].copy()
    dropped = before - len(out)
    if dropped:
        logger.warning("  %d rows with unknown id_trip (dropped)", dropped)
    return out


def transform_payment(df: pd.DataFrame, valid_ids: set) -> pd.DataFrame:
    out = _filter_by_trip(df, valid_ids).rename(columns=config.PAYMENT_COLUMN_MAP)
    out["amount"] = out["amount"].apply(to_decimal)
    out["payment_type"] = out["payment_type"].apply(clean_mojibake).apply(clean_payment_type)
    out["payment_type"] = out["payment_type"].replace("", pd.NA).fillna("Não informado")
    out["payer_agency_name"] = out["payer_agency_name"].apply(clean_mojibake)
    out["paying_unit_name"] = out["paying_unit_name"].apply(clean_mojibake)
    return out[["id_trip", "proposal_number", "payer_agency_name",
                "paying_unit_name", "payment_type", "amount"]]


def transform_ticket(df: pd.DataFrame, valid_ids: set) -> pd.DataFrame:
    out = _filter_by_trip(df, valid_ids).rename(columns=config.TICKET_COLUMN_MAP)
    out["ticket_value"] = out["ticket_value"].apply(to_decimal)
    out["service_fee"] = out["service_fee"].apply(to_decimal)
    out["issue_date"] = out["issue_date"].apply(to_date)
    return out[[
        "id_trip", "transport_mode",
        "outbound_origin_country", "outbound_origin_state", "outbound_origin_city",
        "outbound_destination_country", "outbound_destination_state", "outbound_destination_city",
        "ticket_value", "service_fee", "issue_date",
    ]]


def transform_segment(df: pd.DataFrame, valid_ids: set) -> pd.DataFrame:
    out = _filter_by_trip(df, valid_ids).rename(columns=config.SEGMENT_COLUMN_MAP)
    out["segment_sequence"] = out["segment_sequence"].apply(to_int)
    out["origin_date"] = out["origin_date"].apply(to_date)
    out["destination_date"] = out["destination_date"].apply(to_date)
    out["daily_count"] = out["daily_count"].apply(to_decimal)
    out = out[[
        "id_trip", "segment_sequence",
        "origin_date", "origin_country", "origin_state", "origin_city",
        "destination_date", "destination_country", "destination_state", "destination_city",
        "transport_mode", "daily_count",
    ]]
    before = len(out)
    out = out.drop_duplicates(subset=["id_trip", "segment_sequence"])
    if len(out) < before:
        logger.warning("  %d duplicate (id_trip, segment_sequence) dropped", before - len(out))
    return out


# ---------- Pipeline ----------

def truncate_silver(engine) -> None:
    tables = ", ".join(config.SILVER_TABLES)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


def main() -> None:
    start_time = time.time()
    engine = get_engine()
    truncate_silver(engine)

    # --- 1) Trip ---
    info = config.TABLES["trip"]
    raw_trip, silver_trip = info["raw"], info["silver"]

    logger.info("Reading %s...", raw_trip)
    df = pd.read_sql(f"SELECT * FROM {raw_trip}", engine)
    logger.info("  %d rows", len(df))
    silver = transform_trip(df)
    logger.info("Inserting into %s (bulk)...", silver_trip)
    n = bulk_insert(engine, silver_trip, silver, silver.columns.tolist())
    logger.info("OK %s: %d rows", silver_trip, n)
    valid_ids = set(silver["id_trip"])

    # --- 2) Ticket ---
    info = config.TABLES["ticket"]
    raw_ticket, silver_ticket = info["raw"], info["silver"]

    logger.info("Reading %s...", raw_ticket)
    df = pd.read_sql(f"SELECT * FROM {raw_ticket}", engine)
    logger.info("  %d raw rows", len(df))
    silver = transform_ticket(df, valid_ids)
    logger.info("Inserting into %s (bulk)...", silver_ticket)
    n = bulk_insert(engine, silver_ticket, silver,  silver.columns.tolist())
    logger.info("OK %s: %d rows", silver_ticket, n)

    # --- 3) Payment ---
    info = config.TABLES["payment"]
    raw_payment, silver_payment = info["raw"], info["silver"]

    logger.info("Reading %s...", raw_payment)
    df = pd.read_sql(f"SELECT * FROM {raw_payment}", engine)
    logger.info("  %d raw rows", len(df))
    silver = transform_payment(df, valid_ids)
    logger.info("Inserting into %s (bulk)...", silver_payment)
    n = bulk_insert(engine, silver_payment, silver,  silver.columns.tolist())
    logger.info("OK %s: %d rows", silver_payment, n)

    # --- 4) Segment ---
    info = config.TABLES["segment"]
    raw_segment, silver_segment = info["raw"], info["silver"]

    logger.info("Reading %s...", raw_segment)
    df = pd.read_sql(f"SELECT * FROM {raw_segment}", engine)
    logger.info("  %d raw rows", len(df))
    silver = transform_segment(df, valid_ids)
    logger.info("Inserting into %s (bulk)...", silver_segment)
    n = bulk_insert(engine, silver_segment, silver,  silver.columns.tolist())
    logger.info("OK %s: %d rows", silver_segment, n)

    elapsed = time.time() - start_time
    logger.info("Phase 2 (Silver) completed in %.2f seconds", elapsed)


if __name__ == "__main__":
    main()