# Materiais Sao Jose - MVP de orcamento e estoque

MVP desenvolvido para o Projeto de Software (Experiencia Pratica 3), a partir do
diagnostico feito na Experiencia Pratica 1 com a loja de materiais de construcao
do Jardim Aracy, em Maua (SP).

O problema: o orcamento era anotado em caderno, o preco dependia da memoria ou de
ligar para o fornecedor e o estoque so era conferido quando faltava item na
prateleira. O MVP resolve o fluxo central do balcao: cadastrar produto, montar
orcamento com preco vindo do servidor, gerar PDF, fechar a venda baixando o
estoque e avisar quando o item cruza o minimo.

## Escopo entregue (RF da Experiencia Pratica 2)

- RF01 cadastro de produto com preco de custo, preco de venda, saldo e minimo
- RF02 orcamento com cliente, itens e quantidades, total calculado no servidor
- RF03 geracao do orcamento em PDF para envio ao cliente
- RF04 baixa automatica de estoque ao fechar a venda, com movimento registrado
- RF05 alerta de estoque minimo na tela inicial, no estoque e na listagem
- RF06 relatorio de itens mais vendidos e itens sem saida no periodo

Fora do escopo, como registrado na EP1: emissao fiscal, integracao com o sistema
do fornecedor, aplicativo nativo e controle de permissoes por loja.

## Requisitos nao funcionais cobertos

- RNF01 autenticacao por usuario, senha com PBKDF2-SHA256 (120 mil iteracoes),
  sessao assinada com HMAC e expiracao de 30 minutos, perfil verificado no
  servidor (atendente nao altera preco nem cadastra produto)
- RNF02 consultas parametrizadas em toda a camada de dados, validacao de entrada,
  preco e desconto recalculados no servidor, log sem dado pessoal
- RNF03 configuracao por variavel de ambiente (`LOJA_DB`, `LOJA_SEGREDO`), banco
  embarcado e instalacao documentada
- Acessibilidade: contraste AA, alvos de toque de 44 px, rotulo persistente em
  todo campo, status escrito em texto alem da cor, tabelas com cabecalho associado

## Stack

Python 3.11, FastAPI, SQLite (SQL padrao), Jinja2, Bootstrap 5 e ReportLab para o
PDF. A escolha de SQLite embarcado esta justificada na EP2: um ponto de venda,
volume baixo de escrita e migracao prevista para PostgreSQL quando houver mais de
uma loja.

## Como rodar

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.seed          # cria o banco com dados ficticios de demonstracao
uvicorn app.main:app --reload
```

Acesse http://127.0.0.1:8000 e entre com um dos usuarios de demonstracao:

- `sergio` / `senha-dono` (perfil dono)
- `balcao` / `senha-balcao` (perfil atendente)

As senhas acima existem apenas no seed de demonstracao. Em uso real, cadastre
usuarios com senha propria e defina `LOJA_SEGREDO` com um valor aleatorio.

## Backup

```bash
python -m app.backup /caminho/do/backup
```

Gera copia consistente com a API de backup do SQLite e mantem as 7 ultimas.

## Testes

```bash
python -m pytest -q
```

16 testes cobrem login, hash de senha, permissao por perfil, preco vindo do
servidor, limite de desconto, baixa de estoque, bloqueio de venda sem saldo,
fechamento duplicado, PDF, alerta de minimo, relatorio e entrada de estoque.

## Estrutura

```
app/db.py          esquema SQL e conexao
app/security.py    hash de senha, sessao assinada e perfil
app/main.py        rotas, regra de negocio e geracao de PDF
app/seed.py        dados ficticios de demonstracao
app/templates/     telas Jinja2 com Bootstrap
tests/test_app.py  testes do fluxo central
```

## Modelo de dados (EP2)

`users`, `produtos`, `clientes`, `orcamentos`, `itens_orcamento` e `movimentos`.
O preco e copiado do produto para o item no momento da inclusao, e o estoque e
recalculado por movimentos, o que permite auditar divergencia.

## Pendencias conhecidas

- Emissao fiscal e integracao com fornecedor ficaram fora do escopo do MVP.
- O teste de usabilidade com o representante externo (roteiro da EP2) ainda nao
  foi executado; os criterios de aceitacao estao definidos.
