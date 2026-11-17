"""MVP da loja de materiais de construcao.

Fluxo central: cadastro de produto -> orcamento no balcao -> PDF -> baixa de
estoque ao fechar a venda -> alerta de estoque minimo -> relatorio de giro.
Projeto de Software, Experiencia Pratica 3 (implementacao do MVP).
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from . import db, seed, security

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.filters["g"] = lambda v: ("%g" % float(v)) if v is not None else "-"

app = FastAPI(title="Materiais Sao Jose", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()
    seed.popular_se_vazio()


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ctx(request: Request, **extra):
    base = {"request": request, "perfil": None, "nome": None}
    sessao = security.le_cookie(request.cookies.get("sessao"))
    if sessao:
        user_id, perfil = sessao
        base["perfil"] = perfil
        with db.connect() as conn:
            row = conn.execute("SELECT nome FROM users WHERE id = ?", (user_id,)).fetchone()
            base["nome"] = row["nome"] if row else None
    base.update(extra)
    return base


# --------------------------------------------------------------------------- login


@app.get("/login", response_class=HTMLResponse)
def form_login(request: Request):
    return templates.TemplateResponse("login.html", ctx(request, erro=None))


@app.post("/login")
def login(request: Request, usuario: str = Form(...), senha: str = Form(...)):
    with db.connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE usuario = ? AND ativo = 1", (usuario.strip(),)
        ).fetchone()
    if not row or not security.verifica_senha(senha, row["senha_hash"]):
        return templates.TemplateResponse(
            "login.html", ctx(request, erro="Usuario ou senha invalidos."), status_code=401
        )
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        "sessao",
        security.cria_cookie(row["id"], row["perfil"]),
        httponly=True,
        samesite="lax",
        max_age=security.VALIDADE_SESSAO,
    )
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("sessao")
    return resp


# --------------------------------------------------------------------------- inicio


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, sessao=Depends(security.usuario_atual)):
    with db.connect() as conn:
        alertas = conn.execute(
            """SELECT * FROM produtos WHERE ativo = 1 AND estoque_atual <= estoque_minimo
               ORDER BY (estoque_atual - estoque_minimo) ASC"""
        ).fetchall()
        orcamentos = conn.execute(
            """SELECT o.*, c.nome AS cliente FROM orcamentos o
               JOIN clientes c ON c.id = o.cliente_id
               ORDER BY o.id DESC LIMIT 5"""
        ).fetchall()
    return templates.TemplateResponse(
        "inicio.html", ctx(request, alertas=alertas, orcamentos=orcamentos)
    )


# --------------------------------------------------------------------------- produtos


@app.get("/produtos", response_class=HTMLResponse)
def listar_produtos(request: Request, sessao=Depends(security.usuario_atual)):
    with db.connect() as conn:
        produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
    return templates.TemplateResponse("produtos.html", ctx(request, produtos=produtos, erro=None))


@app.post("/produtos")
def criar_produto(
    request: Request,
    nome: str = Form(...),
    unidade: str = Form("un"),
    preco_custo: float = Form(0),
    preco_venda: float = Form(...),
    estoque_atual: float = Form(0),
    estoque_minimo: float = Form(0),
    sessao=Depends(security.exige_dono),
):
    if preco_venda <= 0:
        raise HTTPException(400, "Preco de venda deve ser maior que zero.")
    try:
        with db.connect() as conn:
            conn.execute(
                """INSERT INTO produtos (nome, unidade, preco_custo, preco_venda,
                                         estoque_atual, estoque_minimo)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (nome.strip(), unidade.strip(), preco_custo, preco_venda, estoque_atual, estoque_minimo),
            )
    except Exception:
        with db.connect() as conn:
            produtos = conn.execute("SELECT * FROM produtos ORDER BY nome").fetchall()
        return templates.TemplateResponse(
            "produtos.html",
            ctx(request, produtos=produtos, erro="Produto ja cadastrado com essa unidade."),
            status_code=400,
        )
    return RedirectResponse("/produtos", status_code=303)


@app.post("/produtos/{produto_id}/inativar")
def inativar_produto(produto_id: int, sessao=Depends(security.exige_dono)):
    with db.connect() as conn:
        conn.execute("UPDATE produtos SET ativo = 0 WHERE id = ?", (produto_id,))
    return RedirectResponse("/produtos", status_code=303)


@app.post("/produtos/{produto_id}/entrada")
def entrada_estoque(produto_id: int, quantidade: float = Form(...), sessao=Depends(security.usuario_atual)):
    if quantidade <= 0:
        raise HTTPException(400, "Quantidade de entrada deve ser positiva.")
    user_id, _ = sessao
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO movimentos (produto_id, tipo, quantidade, criado_em, origem)
               VALUES (?, 'entrada', ?, ?, 'compra')""",
            (produto_id, quantidade, agora()),
        )
        conn.execute(
            "UPDATE produtos SET estoque_atual = estoque_atual + ? WHERE id = ?",
            (quantidade, produto_id),
        )
    return RedirectResponse("/estoque", status_code=303)


# --------------------------------------------------------------------------- estoque


@app.get("/estoque", response_class=HTMLResponse)
def estoque(request: Request, situacao: str = "todos", sessao=Depends(security.usuario_atual)):
    filtros = {
        "todos": "1 = 1",
        "minimo": "estoque_atual <= estoque_minimo",
        "sem_saida": """id NOT IN (SELECT produto_id FROM movimentos
                                    WHERE tipo = 'saida' AND criado_em >= date('now', '-30 day'))""",
    }
    where = filtros.get(situacao, filtros["todos"])
    with db.connect() as conn:
        produtos = conn.execute(
            f"""SELECT p.*, (SELECT MAX(criado_em) FROM movimentos m
                              WHERE m.produto_id = p.id AND m.tipo = 'saida') AS ultima_saida
                FROM produtos p WHERE p.ativo = 1 AND {where} ORDER BY p.nome"""
        ).fetchall()
        criticos = conn.execute(
            "SELECT COUNT(*) FROM produtos WHERE ativo = 1 AND estoque_atual <= estoque_minimo"
        ).fetchone()[0]
        sem_saida = conn.execute(
            f"SELECT COUNT(*) FROM produtos WHERE ativo = 1 AND {filtros['sem_saida']}"
        ).fetchone()[0]
    return templates.TemplateResponse(
        "estoque.html",
        ctx(request, produtos=produtos, situacao=situacao, criticos=criticos, sem_saida=sem_saida),
    )


# --------------------------------------------------------------------------- orcamentos


@app.get("/orcamentos/novo", response_class=HTMLResponse)
def form_orcamento(request: Request, sessao=Depends(security.usuario_atual)):
    with db.connect() as conn:
        produtos = conn.execute(
            "SELECT * FROM produtos WHERE ativo = 1 ORDER BY nome"
        ).fetchall()
        clientes = conn.execute("SELECT * FROM clientes WHERE ativo = 1 ORDER BY nome").fetchall()
    return templates.TemplateResponse(
        "orcamento.html", ctx(request, produtos=produtos, clientes=clientes, erro=None)
    )


@app.post("/orcamentos")
def criar_orcamento(
    request: Request,
    cliente_id: int = Form(...),
    produto_id: list[int] = Form(...),
    quantidade: list[float] = Form(...),
    desconto: float = Form(0),
    observacao: str = Form(""),
    sessao=Depends(security.usuario_atual),
):
    user_id, perfil = sessao
    if desconto < 0:
        raise HTTPException(400, "Desconto nao pode ser negativo.")
    with db.connect() as conn:
        total_bruto = 0.0
        itens = []
        for pid, qtd in zip(produto_id, quantidade):
            if qtd <= 0:
                continue
            prod = conn.execute("SELECT * FROM produtos WHERE id = ? AND ativo = 1", (pid,)).fetchone()
            if not prod:
                raise HTTPException(400, f"Produto {pid} inexistente ou inativo.")
            # preco vem do servidor, nunca do navegador
            preco = float(prod["preco_venda"])
            subtotal = round(preco * qtd, 2)
            itens.append((pid, qtd, preco, subtotal))
            total_bruto += subtotal
        if not itens:
            raise HTTPException(400, "Orcamento precisa de pelo menos um item.")
        if desconto > total_bruto * 0.10 or (desconto > 0 and perfil != "dono"):
            raise HTTPException(403, "Desconto acima do permitido ou perfil sem permissao.")
        total = round(total_bruto - desconto, 2)
        cur = conn.execute(
            """INSERT INTO orcamentos (cliente_id, criado_em, status, desconto, total, observacao, criado_por)
               VALUES (?, ?, 'aberto', ?, ?, ?, ?)""",
            (cliente_id, agora(), desconto, total, observacao.strip() or None, user_id),
        )
        orcamento_id = cur.lastrowid
        for item in itens:
            conn.execute(
                """INSERT INTO itens_orcamento (orcamento_id, produto_id, quantidade, preco_unitario, subtotal)
                   VALUES (?, ?, ?, ?, ?)""",
                (orcamento_id, *item),
            )
    return RedirectResponse(f"/orcamentos/{orcamento_id}", status_code=303)


@app.get("/orcamentos/{orcamento_id}", response_class=HTMLResponse)
def detalhe_orcamento(orcamento_id: int, request: Request, sessao=Depends(security.usuario_atual)):
    with db.connect() as conn:
        orc = conn.execute(
            """SELECT o.*, c.nome AS cliente, c.telefone FROM orcamentos o
               JOIN clientes c ON c.id = o.cliente_id WHERE o.id = ?""",
            (orcamento_id,),
        ).fetchone()
        if not orc:
            raise HTTPException(404, "Orcamento nao encontrado.")
        itens = conn.execute(
            """SELECT i.*, p.nome, p.unidade FROM itens_orcamento i
               JOIN produtos p ON p.id = i.produto_id WHERE i.orcamento_id = ?""",
            (orcamento_id,),
        ).fetchall()
    return templates.TemplateResponse("orcamento_detalhe.html", ctx(request, orc=orc, itens=itens, erro=None))


@app.post("/orcamentos/{orcamento_id}/fechar")
def fechar_venda(orcamento_id: int, request: Request, sessao=Depends(security.usuario_atual)):
    user_id, _ = sessao
    with db.connect() as conn:
        orc = conn.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,)).fetchone()
        if not orc:
            raise HTTPException(404, "Orcamento nao encontrado.")
        if orc["status"] == "fechado":
            raise HTTPException(400, "Orcamento ja fechado.")
        itens = conn.execute(
            "SELECT * FROM itens_orcamento WHERE orcamento_id = ?", (orcamento_id,)
        ).fetchall()
        # 1) valida estoque de todos os itens antes de qualquer baixa
        for item in itens:
            prod = conn.execute("SELECT * FROM produtos WHERE id = ?", (item["produto_id"],)).fetchone()
            if prod["estoque_atual"] < item["quantidade"]:
                return templates.TemplateResponse(
                    "orcamento_detalhe.html",
                    ctx(
                        request,
                        orc=orc,
                        itens=itens,
                        erro=f"Estoque insuficiente para {prod['nome']}: saldo {prod['estoque_atual']}.",
                    ),
                    status_code=400,
                )
        # 2) baixa e movimentos na mesma transacao
        for item in itens:
            conn.execute(
                "UPDATE produtos SET estoque_atual = estoque_atual - ? WHERE id = ?",
                (item["quantidade"], item["produto_id"]),
            )
            conn.execute(
                """INSERT INTO movimentos (produto_id, tipo, quantidade, criado_em, origem, orcamento_id)
                   VALUES (?, 'saida', ?, ?, 'venda', ?)""",
                (item["produto_id"], item["quantidade"], agora(), orcamento_id),
            )
        conn.execute("UPDATE orcamentos SET status = 'fechado' WHERE id = ?", (orcamento_id,))
        orc = conn.execute("SELECT * FROM orcamentos WHERE id = ?", (orcamento_id,)).fetchone()
    return RedirectResponse(f"/orcamentos/{orcamento_id}", status_code=303)


@app.get("/orcamentos/{orcamento_id}/pdf")
def pdf_orcamento(orcamento_id: int, sessao=Depends(security.usuario_atual)):
    with db.connect() as conn:
        orc = conn.execute(
            """SELECT o.*, c.nome AS cliente, c.telefone FROM orcamentos o
               JOIN clientes c ON c.id = o.cliente_id WHERE o.id = ?""",
            (orcamento_id,),
        ).fetchone()
        if not orc:
            raise HTTPException(404, "Orcamento nao encontrado.")
        itens = conn.execute(
            """SELECT i.*, p.nome, p.unidade FROM itens_orcamento i
               JOIN produtos p ON p.id = i.produto_id WHERE i.orcamento_id = ?""",
            (orcamento_id,),
        ).fetchall()

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    largura, altura = A4
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(20 * mm, altura - 20 * mm, "Materiais Sao Jose")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(20 * mm, altura - 26 * mm, "Rua principal do comercio, s/n - Jardim Aracy - Maua/SP")
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(20 * mm, altura - 40 * mm, f"Orcamento #{orc['id']}")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(20 * mm, altura - 48 * mm, f"Cliente: {orc['cliente']}")
    pdf.drawString(20 * mm, altura - 54 * mm, f"Data: {orc['criado_em']}")
    y = altura - 70 * mm
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(20 * mm, y, "Item")
    pdf.drawString(105 * mm, y, "Qtd")
    pdf.drawString(130 * mm, y, "Preco un.")
    pdf.drawString(160 * mm, y, "Subtotal")
    pdf.setFont("Helvetica", 10)
    y -= 7 * mm
    for item in itens:
        pdf.drawString(20 * mm, y, f"{item['nome']} ({item['unidade']})")
        pdf.drawString(105 * mm, y, f"{item['quantidade']:g}")
        pdf.drawString(130 * mm, y, f"R$ {item['preco_unitario']:.2f}")
        pdf.drawString(160 * mm, y, f"R$ {item['subtotal']:.2f}")
        y -= 6 * mm
        if y < 40 * mm:
            pdf.showPage()
            y = altura - 30 * mm
    y -= 4 * mm
    pdf.setStrokeColor(colors.grey)
    pdf.line(20 * mm, y, 190 * mm, y)
    y -= 8 * mm
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(130 * mm, y, "Total")
    pdf.drawString(160 * mm, y, f"R$ {orc['total']:.2f}")
    pdf.setFont("Helvetica", 8)
    pdf.drawString(20 * mm, 20 * mm, "Orcamento valido por 7 dias. Preco sujeito a conferencia de estoque.")
    pdf.showPage()
    pdf.save()
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="orcamento-{orcamento_id}.pdf"'},
    )


# --------------------------------------------------------------------------- relatorio


@app.get("/relatorio", response_class=HTMLResponse)
def relatorio(request: Request, dias: int = 30, sessao=Depends(security.usuario_atual)):
    desde = (datetime.now() - timedelta(days=dias)).strftime("%Y-%m-%d %H:%M:%S")
    with db.connect() as conn:
        vendidos = conn.execute(
            """SELECT p.nome, SUM(i.quantidade) AS qtd, SUM(i.subtotal) AS valor
               FROM itens_orcamento i
               JOIN orcamentos o ON o.id = i.orcamento_id
               JOIN produtos p ON p.id = i.produto_id
               WHERE o.status = 'fechado' AND o.criado_em >= ?
               GROUP BY p.id ORDER BY qtd DESC""",
            (desde,),
        ).fetchall()
        parados = conn.execute(
            """SELECT p.nome, p.estoque_atual FROM produtos p
               WHERE p.ativo = 1 AND p.id NOT IN (
                   SELECT i.produto_id FROM itens_orcamento i
                   JOIN orcamentos o ON o.id = i.orcamento_id
                   WHERE o.status = 'fechado' AND o.criado_em >= ?)
               ORDER BY p.nome""",
            (desde,),
        ).fetchall()
    return templates.TemplateResponse(
        "relatorio.html", ctx(request, vendidos=vendidos, parados=parados, dias=dias)
    )


@app.get("/health")
def health():
    return {"status": "ok", "hora": agora()}
