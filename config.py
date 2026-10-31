"""Central configuration. Reads .env manually and exposes typed constants."""

import os
from pathlib import Path


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Manual .env loader (no external dependency)
# ---------------------------------------------------------------------------
def load_env() -> None:
    """Read .env (if present) and load its keys into os.environ."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

load_env()


# ---------------------------------------------------------------------------
# PostgreSQL credentials (from .env)
# ---------------------------------------------------------------------------
POSTGRES_CONFIG = {
    "host":     os.environ.get("POSTGRES_HOST", "localhost"),
    "port":     int(os.environ.get("POSTGRES_PORT", "5432")),
    "user":     os.environ.get("POSTGRES_USER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
    "dbname":   os.environ.get("POSTGRES_DATABASE", "transparency"),
    "admin_db": os.environ.get("POSTGRES_ADMIN_DB", "postgres"),
}


# ---------------------------------------------------------------------------
# Source (Google Drive)
# ---------------------------------------------------------------------------
YEAR = "2025"
DRIVE_FILE_ID = os.environ.get("DRIVE_FILE_ID", "")
ZIP_PATH = DATA_DIR / f"viagens_{YEAR}.zip"

# Se True, re-baixa o zip mesmo se já existir localmente.
# Útil quando a fonte é atualizada. Default: False (economiza banda).
FORCE_DOWNLOAD = False

# ---------------------------------------------------------------------------
# Tables per entity across all Medallion layers.
# Entity keys: trip, payment, ticket, segment
# Each entity: csv (source file), raw (raw table), silver (typed table)
# Add a "gold" key here if/when the Gold layer needs per-entity tables.
# ---------------------------------------------------------------------------
TABLES = {
    "trip": {
        "csv":    f"{YEAR}_Viagem.csv",
        "raw":    "raw_trip",
        "silver": "silver_trip",
    },
    "payment": {
        "csv":    f"{YEAR}_Pagamento.csv",
        "raw":    "raw_payment",
        "silver": "silver_payment",
    },
    "ticket": {
        "csv":    f"{YEAR}_Passagem.csv",
        "raw":    "raw_ticket",
        "silver": "silver_ticket",
    },
    "segment": {
        "csv":    f"{YEAR}_Trecho.csv",
        "raw":    "raw_segment",
        "silver": "silver_segment",
    },
}

# Convenience lists (used for TRUNCATE, logs, iteration, etc.)
SILVER_TABLES = [t["silver"] for t in TABLES.values()]

# CSV characteristics (specified by the assignment)
CSV_SEPARATOR = ";"
CSV_ENCODING = "latin-1"

# ---------------------------------------------------------------------------
# Column mappings: Raw (PT, generated from CSV) -> Silver (EN)
# ---------------------------------------------------------------------------
TRIP_COLUMN_MAP = {
    "identificador_do_processo_de_viagem": "id_trip",
    "numero_da_proposta__pcdp": "proposal_number",
    "situacao": "status",
    "viagem_urgente": "urgent_trip",
    "codigo_do_orgao_superior": "agency_code",
    "nome_do_orgao_superior": "agency_name",
    "nome": "traveler_name",
    "cargo": "position",
    "periodo___data_de_inicio": "start_date",
    "periodo___data_de_fim": "end_date",
    "destinos": "destinations",
    "motivo": "purpose",
    "valor_diarias": "daily_allowance",
    "valor_passagens": "ticket_cost",
    "valor_devolucao": "refund_amount",
    "valor_outros_gastos": "other_expenses",
}

TICKET_COLUMN_MAP = {
    "identificador_do_processo_de_viagem": "id_trip",
    "meio_de_transporte": "transport_mode",
    "pais___origem_ida": "outbound_origin_country",
    "uf___origem_ida": "outbound_origin_state",
    "cidade___origem_ida": "outbound_origin_city",
    "pais___destino_ida": "outbound_destination_country",
    "uf___destino_ida": "outbound_destination_state",
    "cidade___destino_ida": "outbound_destination_city",
    "valor_da_passagem": "ticket_value",
    "taxa_de_servico": "service_fee",
    "data_da_emissao_compra": "issue_date",
}

PAYMENT_COLUMN_MAP = {
    "identificador_do_processo_de_viagem": "id_trip",
    "numero_da_proposta__pcdp": "proposal_number",
    "nome_do_orgao_pagador": "payer_agency_name",
    "nome_da_unidade_gestora_pagadora": "paying_unit_name",
    "tipo_de_pagamento": "payment_type",
    "valor": "amount",
}

SEGMENT_COLUMN_MAP = {
    "identificador_do_processo_de_viagem": "id_trip",
    "sequencia_trecho": "segment_sequence",
    "origem___data": "origin_date",
    "origem___pais": "origin_country",
    "origem___uf": "origin_state",
    "origem___cidade": "origin_city",
    "destino___data": "destination_date",
    "destino___pais": "destination_country",
    "destino___uf": "destination_state",
    "destino___cidade": "destination_city",
    "meio_de_transporte": "transport_mode",
    "numero_diarias": "daily_count",
}