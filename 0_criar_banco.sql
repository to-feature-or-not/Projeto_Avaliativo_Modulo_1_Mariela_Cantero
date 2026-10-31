-- ============================================================
-- 0_criar_banco.sql
-- Phase 0 - creates the 'transparency' database and 8 tables (4 Raw + 4 Silver).
-- ============================================================

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = '__DB_NAME__' AND pid <> pg_backend_pid();

DROP DATABASE IF EXISTS __DB_NAME__;
CREATE DATABASE __DB_NAME__ WITH ENCODING 'UTF8' TEMPLATE template0;

\c __DB_NAME__

-- ============================================================
-- RAW LAYER - all VARCHAR, no constraints, faithful to CSV
-- (auto-generated from the real CSV headers)
-- ============================================================

-- raw_trip: 22 columns
DROP TABLE IF EXISTS raw_trip CASCADE;
CREATE TABLE raw_trip (
    identificador_do_processo_de_viagem    VARCHAR,
    numero_da_proposta__pcdp               VARCHAR,
    situacao                               VARCHAR,
    viagem_urgente                         VARCHAR,
    justificativa_urgencia_viagem          VARCHAR,
    codigo_do_orgao_superior               VARCHAR,
    nome_do_orgao_superior                 VARCHAR,
    codigo_orgao_solicitante               VARCHAR,
    nome_orgao_solicitante                 VARCHAR,
    cpf_viajante                           VARCHAR,
    nome                                   VARCHAR,
    cargo                                  VARCHAR,
    funcao                                 VARCHAR,
    descricao_funcao                       VARCHAR,
    periodo___data_de_inicio               VARCHAR,
    periodo___data_de_fim                  VARCHAR,
    destinos                               VARCHAR,
    motivo                                 VARCHAR,
    valor_diarias                          VARCHAR,
    valor_passagens                        VARCHAR,
    valor_devolucao                        VARCHAR,
    valor_outros_gastos                    VARCHAR
);

-- raw_payment: 10 columns
DROP TABLE IF EXISTS raw_payment CASCADE;
CREATE TABLE raw_payment (
    identificador_do_processo_de_viagem    VARCHAR,
    numero_da_proposta__pcdp               VARCHAR,
    codigo_do_orgao_superior               VARCHAR,
    nome_do_orgao_superior                 VARCHAR,
    codigo_do_orgao_pagador                VARCHAR,
    nome_do_orgao_pagador                  VARCHAR,
    codigo_da_unidade_gestora_pagadora     VARCHAR,
    nome_da_unidade_gestora_pagadora       VARCHAR,
    tipo_de_pagamento                      VARCHAR,
    valor                                  VARCHAR
);

-- raw_ticket: 19 columns
DROP TABLE IF EXISTS raw_ticket CASCADE;
CREATE TABLE raw_ticket (
    identificador_do_processo_de_viagem    VARCHAR,
    numero_da_proposta__pcdp               VARCHAR,
    meio_de_transporte                     VARCHAR,
    pais___origem_ida                      VARCHAR,
    uf___origem_ida                        VARCHAR,
    cidade___origem_ida                    VARCHAR,
    pais___destino_ida                     VARCHAR,
    uf___destino_ida                       VARCHAR,
    cidade___destino_ida                   VARCHAR,
    pais___origem_volta                    VARCHAR,
    uf___origem_volta                      VARCHAR,
    cidade___origem_volta                  VARCHAR,
    pais___destino_volta                   VARCHAR,
    uf___destino_volta                     VARCHAR,
    cidade___destino_volta                 VARCHAR,
    valor_da_passagem                      VARCHAR,
    taxa_de_servico                        VARCHAR,
    data_da_emissao_compra                 VARCHAR,
    hora_da_emissao_compra                 VARCHAR
);

-- raw_segment: 14 columns
DROP TABLE IF EXISTS raw_segment CASCADE;
CREATE TABLE raw_segment (
    identificador_do_processo_de_viagem    VARCHAR,
    numero_da_proposta__pcdp               VARCHAR,
    sequencia_trecho                       VARCHAR,
    origem___data                          VARCHAR,
    origem___pais                          VARCHAR,
    origem___uf                            VARCHAR,
    origem___cidade                        VARCHAR,
    destino___data                         VARCHAR,
    destino___pais                         VARCHAR,
    destino___uf                           VARCHAR,
    destino___cidade                       VARCHAR,
    meio_de_transporte                     VARCHAR,
    numero_diarias                         VARCHAR,
    missao                                 VARCHAR
);

-- ============================================================
-- SILVER LAYER - typed, PK, FK, 2 extra constraints per table
-- ============================================================

CREATE TABLE silver_trip (
    id_trip              VARCHAR(50)   PRIMARY KEY,
    proposal_number      VARCHAR(50),
    status               VARCHAR(50),
    urgent_trip          VARCHAR(5),
    agency_code          VARCHAR(20),
    agency_name          VARCHAR(255)  NOT NULL,
    traveler_name        VARCHAR(255),
    position             VARCHAR(255),
    start_date           DATE,
    end_date             DATE,
    destinations         VARCHAR(4000),
    purpose              VARCHAR(4000),
    daily_allowance      DECIMAL(10,2) CHECK (daily_allowance >= 0),
    ticket_cost          DECIMAL(10,2),
    refund_amount        DECIMAL(10,2),
    other_expenses       DECIMAL(10,2),
    total_value          DECIMAL(12,2),
    duration_days        INT
);

CREATE TABLE silver_ticket (
    id_ticket                    SERIAL         PRIMARY KEY,
    id_trip                      VARCHAR(50)    NOT NULL,
    transport_mode               VARCHAR(50),
    outbound_origin_country      VARCHAR(60),
    outbound_origin_state        VARCHAR(40),
    outbound_origin_city         VARCHAR(80),
    outbound_destination_country VARCHAR(60),
    outbound_destination_state   VARCHAR(40),
    outbound_destination_city    VARCHAR(80),
    ticket_value                 DECIMAL(10,2)  CHECK (ticket_value >= 0),
    service_fee                  DECIMAL(10,2)  CHECK (service_fee >= 0),
    issue_date                   DATE,
    CONSTRAINT fk_ticket_trip FOREIGN KEY (id_trip)
        REFERENCES silver_trip(id_trip)
);

CREATE TABLE silver_payment (
    id_payment           SERIAL         PRIMARY KEY,
    id_trip              VARCHAR(50)    NOT NULL,
    proposal_number      VARCHAR(50),
    payer_agency_name    VARCHAR(255),
    paying_unit_name     VARCHAR(255),
    payment_type         VARCHAR(50)    NOT NULL,
    amount               DECIMAL(10,2)  CHECK (amount >= 0),
    CONSTRAINT fk_payment_trip FOREIGN KEY (id_trip)
        REFERENCES silver_trip(id_trip)
);

CREATE TABLE silver_segment (
    id_segment           SERIAL         PRIMARY KEY,
    id_trip              VARCHAR(50)    NOT NULL,
    segment_sequence     INT,
    origin_date          DATE,
    origin_country       VARCHAR(80),
    origin_state         VARCHAR(40),
    origin_city          VARCHAR(80),
    destination_date     DATE,
    destination_country  VARCHAR(80),
    destination_state    VARCHAR(40),
    destination_city     VARCHAR(80),
    transport_mode       VARCHAR(50),
    daily_count          DECIMAL(10,2)  CHECK (daily_count >= 0),
    CONSTRAINT uq_segment_trip_seq UNIQUE (id_trip, segment_sequence),
    CONSTRAINT fk_segment_trip FOREIGN KEY (id_trip)
        REFERENCES silver_trip(id_trip)
);
