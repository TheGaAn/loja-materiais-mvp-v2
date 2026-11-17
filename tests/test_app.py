"""Testes do fluxo central do MVP.

Cobrem os requisitos obrigatorios da Experiencia Pratica 3:
RF01 cadastro, RF02 orcamento com preco do servidor, RF03 PDF, RF04 baixa de
estoque, RF05 alerta de minimo, RF06 relatorio, mais RNF01 de autenticacao e
permissao por perfil.
"""
from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOJA_DB", str(tmp_path / "teste.db"))
    from app import db, main, security

    importlib.reload(db)
    importlib.reload(security)
    importlib.reload(main)
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
            ("Sergio", "sergio", security.hash_senha("1234"), "dono"),
        )
        conn.execute(
            "INSERT INTO users (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?)",
            ("Balcao", "balcao", security.hash_senha("1234"), "atendente"),
        )
        conn.execute(
            """INSERT INTO produtos (nome, unidade, preco_custo, preco_venda, estoque_atual, estoque_minimo)
               VALUES ('Cimento CP II', 'saco', 32.0, 38.9, 18, 10)"""
        )
        conn.execute(
            """INSERT INTO produtos (nome, unidade, preco_custo, preco_venda, estoque_atual, estoque_minimo)
               VALUES ('Areia media', 'm3', 95.0, 129.0, 2, 3)"""
        )
        conn.execute(
            "INSERT INTO clientes (nome, telefone) VALUES ('Maria Souza', '(11) 9 9999-0000')"
        )
    with TestClient(main.app) as c:
        yield c


def login(client, usuario):
    return client.post("/login", data={"usuario": usuario, "senha": "1234"}, follow_redirects=False)


def test_rota_protegida_redireciona_para_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_invalido_retorna_401(client):
    r = client.post("/login", data={"usuario": "sergio", "senha": "errada"})
    assert r.status_code == 401


def test_senha_guardada_com_hash(client):
    from app import db

    with db.connect() as conn:
        h = conn.execute("SELECT senha_hash FROM users WHERE usuario = 'sergio'").fetchone()[0]
    assert h.startswith("pbkdf2_sha256$")
    assert "1234" not in h


def test_atendente_nao_cadastra_produto(client):
    login(client, "balcao")
    r = client.post(
        "/produtos",
        data={"nome": "Brita", "unidade": "m3", "preco_custo": 80, "preco_venda": 110,
              "estoque_atual": 5, "estoque_minimo": 2},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_dono_cadastra_produto_e_preco_invalido_falha(client):
    login(client, "sergio")
    ok = client.post(
        "/produtos",
        data={"nome": "Brita", "unidade": "m3", "preco_custo": 80, "preco_venda": 110,
              "estoque_atual": 5, "estoque_minimo": 2},
        follow_redirects=False,
    )
    assert ok.status_code == 303
    ruim = client.post(
        "/produtos",
        data={"nome": "Gesso", "unidade": "saco", "preco_custo": 10, "preco_venda": 0,
              "estoque_atual": 1, "estoque_minimo": 0},
        follow_redirects=False,
    )
    assert ruim.status_code == 400


def test_orcamento_usa_preco_do_servidor(client):
    login(client, "balcao")
    r = client.post(
        "/orcamentos",
        data={"cliente_id": 1, "produto_id": ["1", "2"], "quantidade": ["10", "1"],
              "desconto": "0", "preco_unitario": "0.01"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    from app import db

    with db.connect() as conn:
        total = conn.execute("SELECT total FROM orcamentos ORDER BY id DESC LIMIT 1").fetchone()[0]
        itens = conn.execute("SELECT preco_unitario FROM itens_orcamento ORDER BY id").fetchall()
    assert total == pytest.approx(38.9 * 10 + 129.0)
    assert [i[0] for i in itens] == [38.9, 129.0]


def test_desconto_acima_do_limite_bloqueado(client):
    login(client, "sergio")
    r = client.post(
        "/orcamentos",
        data={"cliente_id": 1, "produto_id": ["1"], "quantidade": ["1"], "desconto": "100"},
        follow_redirects=False,
    )
    assert r.status_code == 403


def test_fechar_venda_baixa_estoque_e_gera_movimento(client):
    login(client, "balcao")
    client.post("/orcamentos", data={"cliente_id": 1, "produto_id": ["1"], "quantidade": ["3"],
                                     "desconto": "0"}, follow_redirects=False)
    r = client.post("/orcamentos/1/fechar", follow_redirects=False)
    assert r.status_code == 303
    from app import db

    with db.connect() as conn:
        saldo = conn.execute("SELECT estoque_atual FROM produtos WHERE id = 1").fetchone()[0]
        mov = conn.execute(
            "SELECT tipo, quantidade, origem FROM movimentos WHERE orcamento_id = 1"
        ).fetchone()
        status = conn.execute("SELECT status FROM orcamentos WHERE id = 1").fetchone()[0]
    assert saldo == pytest.approx(15)
    assert tuple(mov) == ("saida", 3.0, "venda")
    assert status == "fechado"


def test_fechar_sem_estoque_nao_baixa_nada(client):
    login(client, "balcao")
    client.post("/orcamentos", data={"cliente_id": 1, "produto_id": ["2"], "quantidade": ["10"],
                                     "desconto": "0"}, follow_redirects=False)
    r = client.post("/orcamentos/1/fechar", follow_redirects=False)
    assert r.status_code == 400
    assert "Estoque insuficiente" in r.text
    from app import db

    with db.connect() as conn:
        saldo = conn.execute("SELECT estoque_atual FROM produtos WHERE id = 2").fetchone()[0]
        status = conn.execute("SELECT status FROM orcamentos WHERE id = 1").fetchone()[0]
    assert saldo == pytest.approx(2)
    assert status == "aberto"


def test_fechar_duas_vezes_bloqueado(client):
    login(client, "balcao")
    client.post("/orcamentos", data={"cliente_id": 1, "produto_id": ["1"], "quantidade": ["1"],
                                     "desconto": "0"}, follow_redirects=False)
    client.post("/orcamentos/1/fechar", follow_redirects=False)
    r = client.post("/orcamentos/1/fechar", follow_redirects=False)
    assert r.status_code == 400


def test_pdf_do_orcamento(client):
    login(client, "balcao")
    client.post("/orcamentos", data={"cliente_id": 1, "produto_id": ["1"], "quantidade": ["2"],
                                     "desconto": "0"}, follow_redirects=False)
    r = client.get("/orcamentos/1/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1000


def test_alerta_de_estoque_minimo_na_tela_inicial(client):
    login(client, "sergio")
    html = client.get("/").text
    assert "Areia media" in html
    assert "estoque minimo" in html


def test_relatorio_lista_vendidos_e_parados(client):
    login(client, "sergio")
    client.post("/orcamentos", data={"cliente_id": 1, "produto_id": ["1"], "quantidade": ["4"],
                                     "desconto": "0"}, follow_redirects=False)
    client.post("/orcamentos/1/fechar", follow_redirects=False)
    html = client.get("/relatorio").text
    assert "Cimento CP II" in html
    assert "Areia media" in html
    assert "sem saida" in html.lower() or "sem saída" in html.lower()


def test_entrada_de_estoque_registra_movimento(client):
    login(client, "sergio")
    client.post("/produtos/2/entrada", data={"quantidade": "5"}, follow_redirects=False)
    from app import db

    with db.connect() as conn:
        saldo = conn.execute("SELECT estoque_atual FROM produtos WHERE id = 2").fetchone()[0]
        mov = conn.execute("SELECT tipo, quantidade FROM movimentos WHERE produto_id = 2").fetchone()
    assert saldo == pytest.approx(7)
    assert tuple(mov) == ("entrada", 5.0)


def test_logout_encerra_sessao(client):
    login(client, "sergio")
    client.post("/logout", follow_redirects=False)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
