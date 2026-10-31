"""3_analise_BR.py — Versão em Português da Análise da Camada Gold.

Objetivo
--------
Gera um relatório *reprodutível* em português a partir da camada Silver,
espelhando as 7 perguntas de negócio respondidas interativamente no
`3_analise.ipynb`.

Pré-requisitos
--------------
    python run_pipeline.py     # popula as camadas raw + silver

Saídas
------
    outputs/figures/q1_top_agencies.png ... q7_top_payers.png
    outputs/relatorio_analise_BR.md      (relatório markdown com tabelas + gráficos)
    docs/relatorio_analise_BR.html       (deliverable final em HTML)

Execução
--------
    python reports/3_analise_BR.py
"""

import logging
import sys
import base64
from pathlib import Path

# Garante que o script encontre o config.py e banco.py na raiz do projeto
sys.path.append(str(Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")  # backend headless — não abre janela GUI
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import pandas as pd
import seaborn as sns
import numpy as np
from sqlalchemy import text

import config
from banco import get_engine

# ---------------------------------------------------------------------------
# Logs e caminhos de saída
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

FIG_DIR = config.OUTPUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = config.OUTPUT_DIR / "relatorio_analise_BR.md"

sns.set_theme(
    style="whitegrid",
    rc={"axes.facecolor": "#f8f9fa", "grid.color": "#e9ecef"},
)

# Dicionário para traduzir os cabeçalhos das tabelas no relatório final
TRADUCOES_COLUNAS = {
    "total_trips": "Total de Viagens",
    "zero_cost_trips": "Viagens sem Custo",
    "zero_cost_percent": "% Sem Custo",
    "earliest_date": "Data Mais Antiga",
    "latest_date": "Data Mais Recente",
    "total_spent": "Total Gasto (R$)",
    "agency_name": "Órgão",
    "total_cost": "Custo Total (R$)",
    "destination": "Destino",
    "trip_count": "Qtd. Viagens",
    "avg_cost_per_trip": "Custo Médio por Viagem (R$)",
    "traveler_name": "Viajante",
    "start_date": "Data de Ida",
    "end_date": "Data de Volta",
    "duration_days": "Duração (Dias)",
    "total_value": "Custo Total (R$)",
    "payment_type": "Tipo de Pagamento",
    "avg_amount": "Valor Médio (R$)",
    "transport_mode": "Meio de Transporte",
    "usage_count": "Qtd. de Trechos",
    "destination_state": "UF de Destino",
    "segment_count": "Qtd. de Trechos",
    "total_paid": "Total Pago (R$)"
}

# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------
def query_df(engine, sql: str) -> pd.DataFrame:
    """Executa uma string SQL e retorna um DataFrame."""
    return pd.read_sql(text(sql.replace("%", "%%")), engine)

def format_brl(x, decimals=2):
    """Formata número para o padrão brasileiro (R$ 1.234,56)."""
    if pd.isnull(x): return x
    s = f"{x:,.{decimals}f}"
    return f"R$ {s.replace(',', 'X').replace('.', ',').replace('X', '.')}"

def format_int_br(x):
    """Formata inteiro para o padrão brasileiro (1.234)."""
    if pd.isnull(x): return x
    return f"{int(x):,}".replace(",", ".")

def df_to_md(df: pd.DataFrame, formatters: dict = None) -> str:
    """DataFrame → tabela markdown com formatação opcional e colunas traduzidas."""
    df_formatted = df.rename(columns=TRADUCOES_COLUNAS).copy()
    if formatters:
        for col, fmt in formatters.items():
            col_pt = TRADUCOES_COLUNAS.get(col, col)
            if col_pt in df_formatted.columns:
                df_formatted[col_pt] = df_formatted[col_pt].apply(fmt)
                
    headers = "| " + " | ".join(str(c) for c in df_formatted.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df_formatted.columns) + " |"
    rows = [
        "| " + " | ".join(str(v) for v in row) + " |"
        for row in df_formatted.itertuples(index=False)
    ]
    return "\n".join([headers, sep] + rows)

def save_fig(fig, name: str) -> str:
    """Salva uma figura matplotlib e retorna seu nome de arquivo."""
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("  salvo: %s", path)
    return path.name

def get_formatters(df):
    """Gera dicionário de formatação para colunas numéricas e monetárias no padrão BR."""
    fmt = {}
    for col in df.columns:
        c_lower = col.lower()
        if any(k in c_lower for k in ['cost', 'value', 'amount', 'paid', 'spent']):
            fmt[col] = lambda x: format_brl(x)
        elif any(k in c_lower for k in ['count', 'trips', 'days']):
            fmt[col] = lambda x: format_int_br(x)
        elif 'percent' in c_lower:
            fmt[col] = lambda x: f"{x:.2f}%".replace(".", ",") if pd.notnull(x) else x
    return fmt

# ---------------------------------------------------------------------------
# Camada Gold (tabelas + views)
# ---------------------------------------------------------------------------
GOLD_TABLES = {
    "gold_payment_types": """
        CREATE TABLE gold_payment_types AS
        SELECT payment_type, AVG(amount) AS avg_amount
        FROM silver_payment
        GROUP BY payment_type
        ORDER BY avg_amount DESC;
    """,
    "gold_transport_modes": """
        CREATE TABLE gold_transport_modes AS
        SELECT transport_mode, COUNT(*) AS usage_count
        FROM silver_segment
        WHERE transport_mode IS NOT NULL AND transport_mode <> ''
        GROUP BY transport_mode
        ORDER BY usage_count DESC;
    """,
    "gold_destination_states": """
        CREATE TABLE gold_destination_states AS
        SELECT destination_state, COUNT(*) AS segment_count
        FROM silver_segment
        WHERE destination_state IS NOT NULL AND destination_state <> ''
        GROUP BY destination_state
        ORDER BY segment_count DESC;
    """,
    "gold_top_payer_agencies": """
        CREATE TABLE gold_top_payer_agencies AS
        SELECT p.payer_agency_name       AS agency_name,
               COUNT(DISTINCT t.id_trip) AS trip_count,
               SUM(p.amount)             AS total_paid
        FROM silver_payment p
        JOIN silver_trip t ON p.id_trip = t.id_trip
        WHERE p.payer_agency_name IS NOT NULL
        GROUP BY p.payer_agency_name
        ORDER BY total_paid DESC
        LIMIT 10;
    """,
}

def create_gold_layer(engine) -> None:
    logger.info("Criando camada Gold (tabelas + views)...")
    with engine.begin() as conn:
        for name in GOLD_TABLES:
            conn.execute(text(f"DROP VIEW IF EXISTS vw_{name} CASCADE;"))
            conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE;"))
        for name, ddl in GOLD_TABLES.items():
            conn.execute(text(ddl))
            conn.execute(text(f"CREATE VIEW vw_{name} AS SELECT * FROM {name};"))
    logger.info("  %d tabelas Gold + views criadas.", len(GOLD_TABLES))

# ---------------------------------------------------------------------------
# Perguntas de negócio
# ---------------------------------------------------------------------------
def q1_top_agencies(engine) -> dict:
    sql = """
        SELECT agency_name, SUM(total_value) AS total_cost
        FROM silver_trip
        WHERE total_value > 0
        GROUP BY agency_name
        ORDER BY total_cost DESC
        LIMIT 5;
    """
    df = query_df(engine, sql)
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.barplot(
        data=df, x="total_cost", y="agency_name",
        hue="agency_name",
        palette=["#475569", "#64748b", "#94a3b8", "#cbd5e1", "#e2e8f0"],
        legend=False, ax=ax,
    )
    ax.set_title("Top 5 Órgãos por Custo Total", fontsize=13)
    ax.set_xlabel("Custo Total (R$)")
    ax.set_ylabel("Órgão")
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"R$ {x/1e6:,.1f} M")
    )
    fig.tight_layout()
    img = save_fig(fig, "q1_top_agencies")
    return {"title": "Q1 — Os 5 órgãos com maior custo total",
            "tables": [(None, df)], "image": img}

def q2_top_destinations(engine) -> dict:
    sql = """
        WITH trip_destination AS (
            SELECT DISTINCT t.id_trip, s.destination_city, t.total_value
            FROM silver_trip t
            JOIN silver_segment s ON t.id_trip = s.id_trip
            WHERE s.destination_city IS NOT NULL AND t.total_value > 0
        )
        SELECT destination_city AS destination,
               COUNT(*) AS trip_count,
               ROUND(AVG(total_value), 2) AS avg_cost_per_trip
        FROM trip_destination
        GROUP BY destination_city
        HAVING COUNT(*) >= 6
        ORDER BY avg_cost_per_trip DESC
        LIMIT 3;
    """
    df = query_df(engine, sql)
    fig, ax = plt.subplots(figsize=(11, 5))
    sns.barplot(
        data=df, x="avg_cost_per_trip", y="destination",
        hue="destination",
        palette=["#1E3A5F", "#3D5A80", "#98C1D9"],
        legend=False, ax=ax,
    )
    ax.set_title("Top 3 Destinos por Custo Médio por Viagem", fontsize=13)
    ax.set_xlabel("Custo Médio por Viagem (R$)")
    ax.set_ylabel("Cidade de Destino")
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"R$ {x/1e3:,.0f} K")
    )
    fig.tight_layout()
    img = save_fig(fig, "q2_top_destinations")
    return {"title": "Q2 — Os 3 destinos com maior custo médio",
            "tables": [(None, df)], "image": img}

def q3_longest_trip(engine) -> dict:
    sql_general = """
        SELECT traveler_name, agency_name, start_date, end_date,
               duration_days, total_value
        FROM silver_trip
        WHERE duration_days IS NOT NULL
        ORDER BY duration_days DESC LIMIT 1;
    """
    sql_with_cost = """
        SELECT traveler_name, agency_name, duration_days, total_value
        FROM silver_trip
        WHERE duration_days IS NOT NULL AND total_value > 0
        ORDER BY duration_days DESC LIMIT 1;
    """
    df_general = query_df(engine, sql_general)
    df_cost    = query_df(engine, sql_with_cost)

    avg_days = float(query_df(
        engine,
        "SELECT ROUND(AVG(duration_days), 1) AS a FROM silver_trip "
        "WHERE duration_days IS NOT NULL;",
    ).iloc[0]["a"])

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # --- Painel 1 (Barras) ---
    values = [
        float(df_general.iloc[0]["duration_days"]),
        float(df_cost.iloc[0]["duration_days"]),
        avg_days,
    ]
    bars = axes[0].bar(
        ["Mais Longa\n(Geral)", "Mais Longa\n(Com Custo)", "Média das\nViagens"],
        values,
        color=["#1E3A5F", "#3D5A80", "#98C1D9"],
        edgecolor="white", linewidth=1.5,
    )
    for bar, val in zip(bars, values):
        axes[0].text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 5, f"{val:.0f}",
                ha="center", fontsize=10, fontweight="bold")
    axes[0].set_title("Duração: Extremos vs Média", fontsize=13)
    axes[0].set_ylabel("Duração (Dias)")
    axes[0].grid(axis="y", linestyle="--", alpha=0.4)
    axes[0].set_axisbelow(True)
    
    # --- Painel 2 (Dispersão) ---
    df_top50 = query_df(engine, """
        SELECT traveler_name, duration_days, total_value
        FROM silver_trip
        WHERE duration_days IS NOT NULL AND total_value > 0
        ORDER BY duration_days DESC LIMIT 50;
    """)
    axes[1].scatter(df_top50["duration_days"], df_top50["total_value"], 
                    color="steelblue", alpha=0.7, label="Top 50 viagens")
    axes[1].scatter(df_cost["duration_days"], df_cost["total_value"], 
                    color="#1E3A5F", s=200, marker="*", edgecolor="white", linewidth=0.8,
                    label="Viagem + longa (com custo)")
    axes[1].set_title("Top 50 Viagens: Duração vs Custo", fontsize=13)
    axes[1].set_xlabel("Duração (Dias)")
    axes[1].set_ylabel("Custo Total (R$)")
    axes[1].legend(loc="upper left")
    
    fig.tight_layout()
    img = save_fig(fig, "q3_longest_trip")
    
    return {"title": "Q3 — A viagem de maior duração e seu custo",
            "tables": [("Viagem mais longa em geral (custo = 0)", df_general),
                       ("Viagem mais longa com custo registrado", df_cost)],
            "image": img}

def q4_payment_types(engine) -> dict:
    df = query_df(engine, "SELECT * FROM vw_gold_payment_types LIMIT 10;")
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(
        data=df, x="avg_amount", y="payment_type",
        hue="payment_type", palette="Blues_r", legend=False, ax=ax,
    )
    ax.set_title("Valor Médio por Tipo de Pagamento", fontsize=13)
    ax.set_xlabel("Valor Médio (R$)")
    ax.set_ylabel("Tipo de Pagamento")
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"R$ {x:,.0f}")
    )
    fig.tight_layout()
    img = save_fig(fig, "q4_payment_types")
    return {"title": "Q4 — Tipo de pagamento com maior valor médio",
            "tables": [(None, df)], "image": img}

def q5_transport_modes(engine) -> dict:
    df = query_df(engine, "SELECT * FROM vw_gold_transport_modes LIMIT 10;")
    fig, ax = plt.subplots(figsize=(10, 5))
    palette = ["#0F172A", "#1E293B", "#334155", "#164E63",
               "#155E75", "#0C4A6E", "#075985", "#1E3A8A",
               "#334155", "#475569"]
    sns.barplot(
        data=df, x="usage_count", y="transport_mode",
        hue="transport_mode", palette=palette[:len(df)],
        legend=False, ax=ax,
    )
    ax.set_title("Top 10 Meios de Transporte Mais Usados", fontsize=13)
    ax.set_xlabel("Quantidade de Trechos")
    ax.set_ylabel("Meio de Transporte")
    fig.tight_layout()
    img = save_fig(fig, "q5_transport_modes")
    return {"title": "Q5 — Meio de transporte mais usado",
            "tables": [(None, df)], "image": img}

def q6_destination_states(engine) -> dict:
    df = query_df(engine, "SELECT * FROM vw_gold_destination_states LIMIT 10;")
    
    cmap = sns.color_palette("Blues_r", as_cmap=True)
    paleta = [cmap(x) for x in np.linspace(0.0, 0.75, len(df))]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    sns.barplot(
        data=df, x="segment_count", y="destination_state",
        hue="destination_state", palette=paleta,
        legend=False, ax=ax,
    )
    ax.set_title("Top 10 UFs de Destino (Mais Trechos)", fontsize=13)
    ax.set_xlabel("Quantidade de Trechos")
    ax.set_ylabel("UF de Destino")
    fig.tight_layout()
    img = save_fig(fig, "q6_destination_states")
    return {"title": "Q6 — UF de destino que aparece em mais trechos",
            "tables": [(None, df)], "image": img}

def q7_top_payers(engine) -> dict:
    df = query_df(engine, "SELECT * FROM vw_gold_top_payer_agencies LIMIT 10;")
    fig, ax = plt.subplots(figsize=(11, 5))
    y = range(len(df))
    ax.hlines(y=y, xmin=0, xmax=df["total_paid"],
              color="#94a3b8", linewidth=1.5)
    ax.plot(df["total_paid"], y, "o", markersize=10, color="#1e3a5f")
    ax.set_yticks(list(y))
    ax.set_yticklabels(df["agency_name"])
    ax.invert_yaxis()
    ax.set_xlabel("Total Pago (R$)")
    ax.set_title("Top 10 Órgãos Pagadores — Total Pago", fontsize=13)
    ax.xaxis.set_major_formatter(
        ticker.FuncFormatter(lambda x, _: f"R$ {x/1e6:,.1f} M")
    )
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    fig.tight_layout()
    img = save_fig(fig, "q7_top_payers")
    return {"title": "Q7 — Órgão que pagou mais no total",
            "tables": [(None, df)], "image": img}

# ---------------------------------------------------------------------------
# Auditoria + relatório
# ---------------------------------------------------------------------------
def run_audit(engine) -> pd.DataFrame:
    sql = """
        SELECT
            COUNT(*) AS total_trips,
            COUNT(*) FILTER (WHERE total_value = 0) AS zero_cost_trips,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE total_value = 0) / COUNT(*), 2
            ) AS zero_cost_percent,
            MIN(start_date) AS earliest_date,
            MAX(end_date)   AS latest_date,
            SUM(total_value) AS total_spent
        FROM silver_trip;
    """
    return query_df(engine, sql)

def write_markdown_report(audit, results, path) -> None:
    lines = [
        "# Viagens a Serviço — Análise da Camada Gold (Português)",
        "",
        "> Gerado automaticamente por `3_analise_BR.py`. "
        "Para a versão interativa, abra `3_analise.ipynb`.",
        "",
        "## Visão Geral dos Dados",
        "",
        df_to_md(audit, get_formatters(audit)),
        "",
        "## Perguntas de Negócio",
        "",
    ]
    for r in results:
        lines += [f"### {r['title']}", ""]
        for caption, df in r["tables"]:
            if caption:
                lines += [f"**{caption}**", ""]
            lines += [df_to_md(df, get_formatters(df)), ""]
        lines += [f"![{r['title']}](figures/{r['image']})", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Relatório markdown salvo em %s", path)


# ---------------------------------------------------------------------------
# Deliverable HTML (auto-contido com imagens embutidas)
# ---------------------------------------------------------------------------
HTML_HEADER = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Viagens a Serviço — Relatório de Análise</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
           Roboto, sans-serif; max-width: 1100px; margin: 2rem auto;
           padding: 0 1.5rem; color: #1e293b; line-height: 1.6;
           background: #f8fafc; }
    h1 { color: #0f172a; border-bottom: 3px solid #1e3a5f;
         padding-bottom: .5rem; }
    h2 { color: #1e3a5f; margin-top: 2.5rem;
         border-left: 4px solid #3d5a80; padding-left: .75rem; }
    h3 { color: #334155; margin-top: 1.5rem; }
    table.data-table { border-collapse: collapse; width: 100%;
                       margin: 1rem 0; background: white;
                       box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    table.data-table th { background: #1e3a5f; color: white;
                          padding: .5rem .75rem; text-align: left;
                          font-size: .875rem; }
    table.data-table td { padding: .5rem .75rem;
                          border-bottom: 1px solid #e2e8f0;
                          font-size: .875rem; }
    table.data-table tr:hover td { background: #f1f5f9; }
    img { max-width: 100%; height: auto; margin: 1rem 0;
          border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
    blockquote { border-left: 4px solid #94a3b8; margin: 1rem 0;
                 padding: .5rem 1rem; background: #f1f5f9;
                 color: #475569; }
    .footer { text-align: center; margin-top: 3rem;
              color: #64748b; font-size: .875rem; }
    code { background: #e2e8f0; padding: 2px 6px; border-radius: 4px;
           font-size: .875rem; }
  </style>
</head>
<body>
<h1>Viagens a Serviço — Relatório de Análise (Português)</h1>
<blockquote>Gerado automaticamente por <code>3_analise_BR.py</code>. Para a versão interativa, abra <code>3_analise.ipynb</code>.</blockquote>
"""

HTML_FOOTER = """
<div class="footer">
  Projeto Avaliativo SCTEC - Módulo 1 · Análise da Camada Gold
</div>
</body>
</html>
"""

def fig_to_base64(png_path) -> str:
    """Codifica um PNG como base64 para embutir no HTML."""
    with open(png_path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")

def write_html_report(audit, results, path) -> None:
    parts = [HTML_HEADER]

    # Formata os dados ANTES de traduzir as colunas
    df_audit_fmt = audit.copy()
    for col, fmt in get_formatters(audit).items():
        df_audit_fmt[col] = df_audit_fmt[col].apply(fmt)
    df_audit_pt = df_audit_fmt.rename(columns=TRADUCOES_COLUNAS)

    parts.append("<h2>Visão Geral dos Dados</h2>")
    parts.append(df_audit_pt.to_html(index=False, classes="data-table", border=0))

    parts.append("<h2>Perguntas de Negócio</h2>")
    for r in results:
        parts.append(f"<h3>{r['title']}</h3>")
        for caption, df in r["tables"]:
            if caption:
                parts.append(f"<p><strong>{caption}</strong></p>")
            
            # Formata e depois traduz as colunas
            df_fmt = df.copy()
            for col, fmt in get_formatters(df).items():
                df_fmt[col] = df_fmt[col].apply(fmt)
            df_pt = df_fmt.rename(columns=TRADUCOES_COLUNAS)
            
            parts.append(df_pt.to_html(index=False, classes="data-table", border=0))
            
        img_path = FIG_DIR / r["image"]
        img_b64 = fig_to_base64(img_path)
        parts.append(f'<img src="{img_b64}" alt="{r["title"]}">')

    parts.append(HTML_FOOTER)
    path.write_text("\n".join(parts), encoding="utf-8")
    logger.info("Relatório HTML salvo em %s", path)

# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------
def main() -> None:
    engine = get_engine()

    logger.info("Etapa 1/4 — Auditoria da camada Silver")
    audit = run_audit(engine)

    logger.info("Etapa 2/4 — Construção da camada Gold")
    create_gold_layer(engine)

    logger.info("Etapa 3/4 — Respondendo as 7 perguntas de negócio")
    results = [
        q1_top_agencies(engine),
        q2_top_destinations(engine),
        q3_longest_trip(engine),
        q4_payment_types(engine),
        q5_transport_modes(engine),
        q6_destination_states(engine),
        q7_top_payers(engine),
    ]

    logger.info("Etapa 4/4 — Gerando relatórios")
    # Markdown -> outputs/ (artefato de reprodutibilidade, ignorado pelo git)
    write_markdown_report(audit, results, REPORT_PATH)

    # HTML -> docs/ (deliverable, versionado no GitHub)
    docs_dir = config.BASE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    html_path = docs_dir / "relatorio_analise_BR.html"
    write_html_report(audit, results, html_path)

    logger.info("Concluído.")
    logger.info("  Reprodutibilidade: %s", REPORT_PATH)
    logger.info("  Deliverable:       %s", html_path)


if __name__ == "__main__":
    main()