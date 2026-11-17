"""Backup diario do banco SQLite.

Fecha a pendencia registrada no README: copia o arquivo do banco com a API de
backup do proprio SQLite (segura com o banco em uso) e mantem as ultimas copias.
Uso: python -m app.backup [destino]
"""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from . import db

MANTER = 7


def faz_backup(destino: Path | None = None) -> Path:
    origem = db.db_path()
    destino = destino or Path(os.environ.get("LOJA_BACKUP_DIR", origem.parent / "backups"))
    destino.mkdir(parents=True, exist_ok=True)
    base = f"loja-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    saida = destino / f"{base}.db"
    contador = 1
    while saida.exists():
        saida = destino / f"{base}-{contador}.db"
        contador += 1
    with sqlite3.connect(origem) as src, sqlite3.connect(saida) as dst:
        src.backup(dst)
    antigos = sorted(destino.glob("loja-*.db"))[:-MANTER]
    for velho in antigos:
        velho.unlink(missing_ok=True)
    return saida


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print("backup em:", faz_backup(destino))


if __name__ == "__main__":
    main()
