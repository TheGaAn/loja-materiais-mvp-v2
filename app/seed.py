"""Popula o banco com usuarios e dados de demonstracao ficticios.

Uso: python -m app.seed
"""
from __future__ import annotations

from datetime import datetime

from . import db, security

USUARIOS = [
    ("Sergio Luis da Silva", "sergio", "senha-dono", "dono"),
    ("Atendente do balcao", "balcao", "senha-balcao", "atendente"),
]

PRODUTOS = [
    ("Cimento CP II - saco 50 kg", "saco", 32.00, 38.90, 18, 10),
    ("Areia media - metro", "m3", 95.00, 129.00, 120, 30),
    ("Tijolo 8 furos - milheiro", "mil", 780.00, 900.00, 900, 500),
    ("Vergalhao 10 mm - barra", "bar", 41.00, 52.00, 40, 50),
    ("Brita 1 - metro", "m3", 88.00, 118.00, 60, 20),
]

CLIENTES = [
    ("Maria Souza", "(11) 9 9999-0000", "Jardim Aracy", "morador"),
    ("Joao Pedro", "(11) 9 8888-1111", "Jardim Aracy", "pedreiro"),
    ("Construtora Alfa", "(11) 4444-2222", "Maua", "empresa"),
]


def main() -> None:
    db.reset_db()
    with db.connect() as conn:
        for nome, usuario, senha, perfil in USUARIOS:
            conn.execute(
                "INSERT INTO users (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
                (nome, usuario, security.hash_senha(senha), perfil),
            )
        for nome, unidade, custo, venda, saldo, minimo in PRODUTOS:
            conn.execute(
                """INSERT INTO produtos (nome, unidade, preco_custo, preco_venda,
                                         estoque_atual, estoque_minimo)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (nome, unidade, custo, venda, saldo, minimo),
            )
        for nome, tel, bairro, tipo in CLIENTES:
            conn.execute(
                "INSERT INTO clientes (nome, telefone, bairro, tipo) VALUES (?, ?, ?, ?)",
                (nome, tel, bairro, tipo),
            )
        conn.execute(
            """INSERT INTO movimentos (produto_id, tipo, quantidade, criado_em, origem)
               VALUES (1, 'saida', 2, ?, 'venda')""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )
    print("banco populado:", db.db_path())


if __name__ == "__main__":
    main()
