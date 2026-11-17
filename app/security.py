"""Autenticacao e sessao.

Requisito RNF01 da Experiencia Pratica 2: senha com hash forte, sessao com
expiracao e perfil verificado no servidor em toda requisicao.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request, status

ITERACOES = 120_000
VALIDADE_SESSAO = 30 * 60  # 30 minutos


def hash_senha(senha: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${salt}${dk.hex()}"


def verifica_senha(senha: str, hash_guardado: str) -> bool:
    try:
        _, iteracoes, salt, esperado = hash_guardado.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt.encode(), int(iteracoes))
    return hmac.compare_digest(dk.hex(), esperado)


def _segredo() -> bytes:
    return os.environ.get("LOJA_SEGREDO", "segredo-de-desenvolvimento").encode()


def assina(valor: str) -> str:
    return hmac.new(_segredo(), valor.encode(), hashlib.sha256).hexdigest()


def cria_cookie(user_id: int, perfil: str) -> str:
    expira = int(time.time()) + VALIDADE_SESSAO
    corpo = f"{user_id}:{perfil}:{expira}"
    return f"{corpo}:{assina(corpo)}"


def le_cookie(valor: str | None) -> tuple[int, str] | None:
    if not valor:
        return None
    partes = valor.split(":")
    if len(partes) != 4:
        return None
    user_id, perfil, expira, mac = partes
    corpo = f"{user_id}:{perfil}:{expira}"
    if not hmac.compare_digest(mac, assina(corpo)):
        return None
    if int(expira) < time.time():
        return None
    return int(user_id), perfil


def usuario_atual(request: Request) -> tuple[int, str]:
    sessao = le_cookie(request.cookies.get("sessao"))
    if not sessao:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return sessao


def exige_dono(request: Request) -> tuple[int, str]:
    user_id, perfil = usuario_atual(request)
    if perfil != "dono":
        raise HTTPException(status_code=403, detail="Apenas o dono da loja pode executar esta acao.")
    return user_id, perfil
