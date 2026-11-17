"""Camada de dados: SQLite com esquema em SQL padrao.

Decisao registrada na Experiencia Pratica 2: banco relacional embarcado,
com modelo escrito em SQL padrao para permitir migracao futura para
PostgreSQL sem reescrever a regra de negocio.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    usuario    TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil     TEXT NOT NULL CHECK (perfil IN ('dono', 'atendente')),
    ativo      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS produtos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           TEXT NOT NULL,
    unidade        TEXT NOT NULL DEFAULT 'un',
    preco_custo    REAL NOT NULL DEFAULT 0,
    preco_venda    REAL NOT NULL,
    estoque_atual  REAL NOT NULL DEFAULT 0,
    estoque_minimo REAL NOT NULL DEFAULT 0,
    ativo          INTEGER NOT NULL DEFAULT 1,
    CHECK (preco_venda > 0),
    CHECK (estoque_atual >= 0),
    UNIQUE (nome, unidade)
);

CREATE TABLE IF NOT EXISTS clientes (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    nome     TEXT NOT NULL,
    telefone TEXT,
    bairro   TEXT,
    tipo     TEXT NOT NULL DEFAULT 'morador',
    ativo    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS orcamentos (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL REFERENCES clientes(id),
    criado_em  TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'aberto'
               CHECK (status IN ('aberto', 'enviado', 'fechado', 'cancelado')),
    desconto   REAL NOT NULL DEFAULT 0,
    total      REAL NOT NULL DEFAULT 0,
    observacao TEXT,
    criado_por INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS itens_orcamento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    orcamento_id   INTEGER NOT NULL REFERENCES orcamentos(id) ON DELETE CASCADE,
    produto_id     INTEGER NOT NULL REFERENCES produtos(id),
    quantidade     REAL NOT NULL CHECK (quantidade > 0),
    preco_unitario REAL NOT NULL CHECK (preco_unitario > 0),
    subtotal       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS movimentos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id   INTEGER NOT NULL REFERENCES produtos(id),
    tipo         TEXT NOT NULL CHECK (tipo IN ('entrada', 'saida', 'ajuste')),
    quantidade   REAL NOT NULL,
    criado_em    TEXT NOT NULL,
    origem       TEXT NOT NULL DEFAULT 'manual',
    orcamento_id INTEGER REFERENCES orcamentos(id)
);
"""


def db_path() -> Path:
    return Path(os.environ.get("LOJA_DB", Path(__file__).resolve().parent.parent / "loja.db"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def reset_db() -> None:
    p = db_path()
    if p.exists():
        p.unlink()
    init_db()
