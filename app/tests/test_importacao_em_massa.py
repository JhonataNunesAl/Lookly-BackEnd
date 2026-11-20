"""Testes da importação/exportação/edição em massa de peças (2026-11-20).

Sem banco e sem rede: o acesso a dados do service (`_loja`, `_categorias`,
`_existentes`) é trocado por versões falsas, e a edição em massa é conferida
pela SQL que ela monta.

Roda com: cd app && python -m pytest tests/ -v
"""
import asyncio
import io
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from schemas.importacao import EdicaoEmMassa, ItemLote, LoteRequest
from service import importacao_service as svc


def run(coro):
    return asyncio.run(coro)


CAT_VESTIDOS = SimpleNamespace(id=uuid4(), name="Vestidos", slug="vestidos")
CAT_STREET = SimpleNamespace(id=uuid4(), name="Streetwear", slug="streetwear")
LOJA = SimpleNamespace(id=uuid4())
FOTO = "https://cdn.exemplo.com/a.jpg"


@pytest.fixture
def banco_falso(monkeypatch):
    """Loja logada, duas categorias e as peças `existentes` que o teste definir."""
    estado = SimpleNamespace(existentes=[])

    async def loja(db, user_id):
        return LOJA

    async def categorias(db):
        return [CAT_VESTIDOS, CAT_STREET]

    async def existentes(db, seller_id, ids, skus):
        return [l for l in estado.existentes if l.id in ids or (l.sku and l.sku in skus)]

    monkeypatch.setattr(svc, "_loja", loja)
    monkeypatch.setattr(svc, "_categorias", categorias)
    monkeypatch.setattr(svc, "_existentes", existentes)
    return estado


def csv_bytes(texto: str, codificacao="utf-8") -> bytes:
    return texto.replace("\n", "\r\n").encode(codificacao)


# ── conversão de células ──────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("89,90", "89.90"), ("89.90", "89.90"), ("R$ 1.299,00", "1299.00"), ("1,299.00", "1299.00"),
        ("1.500", "1500.00"), ("1.234.567", "1234567.00"), ("10", "10.00"), (89.9, "89.90"),
        (120, "120.00"), ("  ", None), (None, None), ("12.5", "12.50"),
    ],
)
def test_preco_aceita_formato_brasileiro_e_internacional(entrada, esperado):
    valor = svc.parse_preco(entrada)
    assert (str(valor) if valor is not None else None) == esperado


@pytest.mark.parametrize("entrada", ["abc", "-5", "1,2,3"])
def test_preco_invalido(entrada):
    with pytest.raises(ValueError):
        svc.parse_preco(entrada)


@pytest.mark.parametrize("entrada,esperado", [("3", 3), (3.0, 3), ("1.200", 1200), ("2,0", 2), ("", None)])
def test_estoque_inteiro(entrada, esperado):
    assert svc.parse_inteiro(entrada) == esperado


@pytest.mark.parametrize("entrada", ["2,5", 2.5, "dois"])
def test_estoque_nao_inteiro_e_erro(entrada):
    with pytest.raises(ValueError):
        svc.parse_inteiro(entrada)


@pytest.mark.parametrize(
    "entrada,esperado",
    [("P, M, G", ["P", "M", "G"]), ("g;p", ["P", "G"]), ("P M G", ["P", "M", "G"]),
     ("38/40", ["38", "40"]), ("unico", ["Único"]), ("Único", ["Único"])],
)
def test_tamanhos(entrada, esperado):
    assert svc.parse_tamanhos(entrada) == esperado


def test_tamanho_desconhecido_e_erro():
    with pytest.raises(ValueError):
        svc.parse_tamanhos("Médio")


def test_fotos_separa_links_e_arquivos():
    links, arquivos = svc.parse_fotos(
        "https://a.com/1.jpg | frente.JPG; https://a.com/2.jpg, https://a.com/3.jpg\ncostas.png"
    )
    assert links == ["https://a.com/1.jpg", "https://a.com/2.jpg", "https://a.com/3.jpg"]
    assert arquivos == ["frente.JPG", "costas.png"]


# ── leitura do arquivo ────────────────────────────────────────────────────────

def test_csv_com_ponto_e_virgula_e_acentos_do_excel():
    corpo = csv_bytes("codigo;nome;categoria;preço;estoque\nA1;Calça jeans;Vestidos;59,90;2\n", "cp1252")
    linhas, ignoradas = svc.separar_linhas(svc.ler_planilha("text/csv", corpo))
    assert ignoradas == []
    assert len(linhas) == 1 and linhas[0].numero == 2
    assert linhas[0].valores["name"] == "Calça jeans"
    assert linhas[0].valores["price"] == "59,90"


def test_csv_com_virgula_e_bom():
    corpo = "﻿nome,categoria,fotos\nBlusa,Vestidos,https://x.com/a.jpg\n".encode("utf-8")
    linhas, _ = svc.separar_linhas(svc.ler_planilha("text/csv", corpo))
    assert linhas[0].valores["photos"] == "https://x.com/a.jpg"


def test_cabecalho_com_apelidos_e_colunas_desconhecidas():
    corpo = csv_bytes("Produto*;Categoria;Qtd;Cor;situacao\nBlusa;Vestidos;3;azul;ativa\n")
    linhas, ignoradas = svc.separar_linhas(svc.ler_planilha("text/csv", corpo))
    assert linhas[0].valores == {"name": "Blusa", "category": "Vestidos", "stock_quantity": "3"}
    assert ignoradas == ["Cor"]  # "situacao" é da exportação: ignorada em silêncio


def test_pula_linhas_em_branco_e_de_exemplo():
    corpo = csv_bytes("codigo;nome\nEXEMPLO-001;Linha do modelo\n;\nB2;Saia\n")
    linhas, _ = svc.separar_linhas(svc.ler_planilha("text/csv", corpo))
    assert [l.valores["name"] for l in linhas] == ["Saia"]
    assert linhas[0].numero == 4


def test_sem_cabecalho_400():
    with pytest.raises(HTTPException) as e:
        svc.separar_linhas(svc.ler_planilha("text/csv", csv_bytes("a;b;c\n1;2;3\n")))
    assert e.value.status_code == 400


def test_arquivo_vazio_e_grande_demais():
    with pytest.raises(HTTPException) as e:
        svc.ler_planilha("text/csv", b"")
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        svc.ler_planilha("text/csv", b"x" * (svc.MAX_BYTES_PLANILHA + 1))
    assert e.value.status_code == 413


def test_linhas_demais_413(monkeypatch):
    monkeypatch.setattr(svc, "MAX_LINHAS", 3)
    corpo = csv_bytes("nome;categoria\n" + "".join(f"P{i};Vestidos\n" for i in range(5)))
    with pytest.raises(HTTPException) as e:
        svc.separar_linhas(svc.ler_planilha("text/csv", corpo))
    assert e.value.status_code == 413


def test_xlsx_pela_aba_produtos():
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "Instruções"
    wb.active.append(["leia-me"])
    ws = wb.create_sheet("Produtos")
    ws.append(["nome", "categoria", "preco", "estoque", "fotos"])
    ws.append(["Jaqueta", "Streetwear", 149.9, 4, FOTO])
    buf = io.BytesIO()
    wb.save(buf)
    linhas, _ = svc.separar_linhas(svc.ler_planilha(None, buf.getvalue()))  # detecta pelo "PK"
    assert linhas[0].valores["name"] == "Jaqueta"
    assert svc.parse_preco(linhas[0].valores["price"]) == Decimal("149.90")
    assert svc.parse_inteiro(linhas[0].valores["stock_quantity"]) == 4


def test_xlsx_corrompido_400():
    with pytest.raises(HTTPException) as e:
        svc.ler_planilha(svc.MIME_XLSX, b"PK\x03\x04lixo")
    assert e.value.status_code == 400


# ── prévia ────────────────────────────────────────────────────────────────────

def previa(texto: str):
    return run(svc.gerar_previa(None, uuid4(), "text/csv", csv_bytes(texto)))


def test_previa_linha_valida_vira_criar(banco_falso):
    r = previa(f"nome;categoria;preco;estoque;tamanhos;fotos\nVestido;vestidos;89,90;2;P,M;{FOTO}\n")
    assert (r.total_linhas, r.validas, r.a_criar, r.a_atualizar) == (1, 1, 1, 0)
    linha = r.linhas[0]
    assert linha.acao == "criar" and linha.erros == []
    assert linha.dados == {
        "name": "Vestido", "category_id": str(CAT_VESTIDOS.id), "price": "89.90",
        "stock_quantity": 2, "sizes": ["P", "M"], "photos": [FOTO],
    }
    # a prévia gera exatamente o que o POST /looks/bulk aceita
    ItemLote.model_validate(linha.dados)


def test_previa_aponta_erros_por_linha(banco_falso):
    r = previa(
        "nome;categoria;preco;estoque;tamanhos;fotos\n"
        f"Vestido;Inexistente;abc;2,5;XXL;{FOTO}\n"
        "X;Vestidos;;;;\n"
        f"Camisa;Vestidos;10;1;;http://inseguro.com/a.jpg\n"
    )
    assert r.validas == 0 and r.com_erro == 3
    e1, e2, e3 = (l.erros for l in r.linhas)
    assert any("categoria" in e and "Inexistente" in e for e in e1)
    assert any(e.startswith("preco:") for e in e1)
    assert any(e.startswith("estoque:") for e in e1)
    assert any(e.startswith("tamanhos:") for e in e1)
    assert any("obrigatório" in e and "fotos" in e for e in e2)
    assert any(e.startswith("nome:") for e in e2)  # menos de 2 letras
    assert any("https" in e for e in e3)
    assert [l.linha for l in r.linhas] == [2, 3, 4]


def test_previa_fotos_por_nome_de_arquivo_ficam_pendentes(banco_falso):
    r = previa(f"nome;categoria;fotos\nSaia;Vestidos;saia1.jpg | {FOTO}\nBlusa;Vestidos;blusa.png\nTop;Vestidos;doc.pdf\n")
    saia, blusa, top = r.linhas
    assert saia.erros == [] and saia.fotos_pendentes == ["saia1.jpg"] and saia.dados["photos"] == [FOTO]
    assert saia.fotos == ["saia1.jpg", FOTO]  # ordem da planilha: a primeira é a capa
    assert blusa.erros == [] and "photos" not in blusa.dados and blusa.fotos_pendentes == ["blusa.png"]
    assert top.erros  # .pdf não é foto
    assert r.arquivos_de_foto == ["saia1.jpg", "blusa.png"]


def test_previa_codigo_existente_vira_atualizar_e_campos_vazios_ficam(banco_falso):
    existente = SimpleNamespace(id=uuid4(), sku="BR-01")
    banco_falso.existentes = [existente]
    r = previa("codigo;nome;categoria;preco;estoque;fotos\nBR-01;;;45,00;0;\nBR-02;Nova;Vestidos;;;" + FOTO + "\n")
    atualiza, cria = r.linhas
    assert atualiza.acao == "atualizar" and atualiza.erros == []
    assert atualiza.dados == {"sku": "BR-01", "price": "45.00", "stock_quantity": 0, "id": str(existente.id)}
    assert cria.acao == "criar" and cria.erros == []
    assert (r.a_criar, r.a_atualizar) == (1, 1)


def test_previa_codigo_repetido_e_id_de_outra_loja(banco_falso):
    r = previa(
        f"id;codigo;nome;categoria;fotos\n;A;Um;Vestidos;{FOTO}\n;A;Dois;Vestidos;{FOTO}\n{uuid4()};;;;\n"
    )
    assert r.linhas[0].erros == []
    assert any("repetido" in e and "linha 2" in e for e in r.linhas[1].erros)
    assert any("não encontrada" in e for e in r.linhas[2].erros)


def test_previa_so_para_vendedor():
    with pytest.raises(HTTPException) as e:
        async def sem_loja(db, uid):
            return None
        sessao = SimpleNamespace()
        original = svc.seller_service.get_seller_by_owner
        svc.seller_service.get_seller_by_owner = sem_loja
        try:
            run(svc.gerar_previa(sessao, uuid4(), "text/csv", b"nome\nx\n"))
        finally:
            svc.seller_service.get_seller_by_owner = original
    assert e.value.status_code == 403


# ── gravação em lote ──────────────────────────────────────────────────────────

class SessaoLote:
    def __init__(self, categorias_validas, falhar_commit=False):
        self.categorias_validas = categorias_validas
        self.adicionados = []
        self.commits = 0
        self.rollbacks = 0
        self.falhar_commit = falhar_commit

    async def execute(self, query):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self.categorias_validas)))

    def add_all(self, objs):
        self.adicionados.extend(objs)

    async def flush(self):
        for o in self.adicionados:
            o.id = o.id or uuid4()

    async def commit(self):
        if self.falhar_commit:
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("x", {}, Exception("duplicate key"))
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def test_lote_cria_atualiza_e_devolve_erros_sem_travar_as_validas(banco_falso):
    existente = SimpleNamespace(id=uuid4(), sku="BR-01", price=Decimal("10"), stock_quantity=3, name="Antiga",
                                reserved_quantity=2, seller_id=LOJA.id, cost_price=None)
    banco_falso.existentes = [existente]
    db = SessaoLote([CAT_VESTIDOS.id])
    pedido = LoteRequest(status="draft", itens=[
        {"linha": 2, "name": "Nova", "category_id": str(CAT_VESTIDOS.id), "photos": [FOTO], "sku": "BR-02",
         "price": "89.90", "stock_quantity": 1, "sizes": ["m"]},
        {"linha": 3, "sku": "BR-01", "price": "45.00", "stock_quantity": 0},
        {"linha": 4, "name": "Sem foto", "category_id": str(CAT_VESTIDOS.id)},
        {"linha": 5, "name": "Cat errada", "category_id": str(uuid4()), "photos": [FOTO]},
        {"linha": 6, "name": "Preço ruim", "price": "-1"},
        {"linha": 7, "id": str(uuid4()), "price": "1"},
        {"linha": 8, "name": "Repete", "category_id": str(CAT_VESTIDOS.id), "photos": [FOTO], "sku": "BR-02"},
    ])
    r = run(svc.gravar_lote(db, uuid4(), pedido))
    assert (r.criados, r.atualizados) == (1, 1)
    assert [e.linha for e in r.erros] == [4, 5, 6, 7, 8]
    novo = db.adicionados[0]
    assert novo.seller_id == LOJA.id and novo.status == "draft" and novo.sizes == ["M"] and novo.sku == "BR-02"
    assert existente.price == Decimal("45.00") and existente.stock_quantity == 0
    assert existente.name == "Antiga"  # campo não enviado não muda
    assert db.commits == 1
    assert set(r.ids) == {novo.id, existente.id}
    # histórico de estoque: entrada da peça nova e ajuste da existente (reserva cortada)
    from model.stock_movement import StockMovement
    movs = [o for o in db.adicionados if isinstance(o, StockMovement)]
    assert sorted((m.kind, m.quantity) for m in movs) == [("ajuste", -3), ("entrada", 1)]
    assert existente.reserved_quantity == 0


def test_lote_da_um_created_at_diferente_para_cada_peca(banco_falso):
    """A paginação por data (`created_at < cursor`) perderia peças empatadas."""
    db = SessaoLote([CAT_VESTIDOS.id])
    itens = [{"name": f"Peça {i}", "category_id": str(CAT_VESTIDOS.id), "photos": [FOTO]} for i in range(50)]
    run(svc.gravar_lote(db, uuid4(), LoteRequest(itens=itens)))
    from model.look import Look
    datas = [l.created_at for l in db.adicionados if isinstance(l, Look)]
    assert len(set(datas)) == 50
    assert datas == sorted(datas, reverse=True)  # 1ª linha = mais recente


def test_lote_conflito_no_banco_nao_grava_nada(banco_falso):
    db = SessaoLote([CAT_VESTIDOS.id], falhar_commit=True)
    pedido = LoteRequest(itens=[{"name": "Nova", "category_id": str(CAT_VESTIDOS.id), "photos": [FOTO]}])
    with pytest.raises(HTTPException) as e:
        run(svc.gravar_lote(db, uuid4(), pedido))
    assert e.value.status_code == 400 and db.rollbacks == 1


def test_lote_tem_teto_de_itens():
    with pytest.raises(ValidationError):
        LoteRequest(itens=[{}] * 1001)


def test_campos_da_gestao_de_estoque_so_gravam_se_o_modelo_tiver(banco_falso):
    item = ItemLote(name="Peça", brand="Farm", condition="Seminovo", cost_price="10")
    campos = svc._campos_gravaveis(item)
    from model.look import Look
    for campo in ("brand", "condition", "cost_price"):
        assert (campo in campos) == hasattr(Look, campo)
    assert item.condition == "seminovo"


# ── edição em massa ───────────────────────────────────────────────────────────

class SessaoEdicao:
    """Devolve as peças "da loja" para o SELECT ... FOR UPDATE e guarda o resto."""

    def __init__(self, looks):
        self.looks = looks
        self.query = None
        self.adicionados = []
        self.commits = 0

    async def execute(self, query):
        self.query = query
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self.looks)))

    def add(self, obj):
        self.adicionados.append(obj)

    async def commit(self):
        self.commits += 1


def sql(q) -> str:
    from sqlalchemy.dialects import postgresql
    return str(q.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def peca(**kw):
    base = dict(id=uuid4(), seller_id=LOJA.id, name="Peça", price=Decimal("100.00"), stock_quantity=5,
                reserved_quantity=0, cost_price=None, status="active", category_id=CAT_VESTIDOS.id)
    return SimpleNamespace(**(base | kw))


def test_edicao_em_massa_reajuste_e_soma_de_estoque(banco_falso):
    a, b = peca(price=Decimal("89.90"), stock_quantity=5, reserved_quantity=4), peca(price=None, stock_quantity=1)
    db = SessaoEdicao([a, b])
    r = run(svc.editar_em_massa(db, uuid4(), EdicaoEmMassa(ids=[a.id, b.id, uuid4()], price_percent=Decimal("-20"), stock_delta=-3)))
    texto = sql(db.query)
    assert f"looks.seller_id = '{LOJA.id}'" in texto  # só peças da própria loja
    assert "looks.status IN ('active', 'draft')" in texto  # moderação não é mexida
    assert "FOR UPDATE" in texto
    assert a.price == Decimal("71.92") and b.price is None
    assert (a.stock_quantity, a.reserved_quantity) == (2, 2)  # reserva cortada
    assert b.stock_quantity == 0  # nunca abaixo de zero
    assert sorted((m.kind, m.quantity) for m in db.adicionados) == [("ajuste", -3), ("ajuste", -1)]
    assert (r.atualizados, r.ignorados) == (2, 1) and db.commits == 1


def test_edicao_em_massa_valores_fixos(banco_falso):
    a = peca(stock_quantity=7)
    db = SessaoEdicao([a])
    run(svc.editar_em_massa(db, uuid4(), EdicaoEmMassa(ids=[a.id], price=Decimal("50"), stock_quantity=7, status="draft")))
    assert a.price == Decimal("50") and a.status == "draft"
    assert db.adicionados == []  # estoque igual: nada no histórico


@pytest.mark.parametrize(
    "dados",
    [
        {"ids": []},
        {"ids": ["00000000-0000-0000-0000-000000000001"]},  # nada para alterar
        {"ids": ["00000000-0000-0000-0000-000000000001"], "price": 1, "price_percent": 10},
        {"ids": ["00000000-0000-0000-0000-000000000001"], "stock_quantity": 1, "stock_delta": 1},
        {"ids": ["00000000-0000-0000-0000-000000000001"], "status": "removed"},
        {"ids": ["00000000-0000-0000-0000-000000000001"], "price_percent": -95},
    ],
)
def test_edicao_em_massa_rejeita_pedidos_incoerentes(dados):
    with pytest.raises(ValidationError):
        EdicaoEmMassa(**dados)


# ── modelo e exportação ───────────────────────────────────────────────────────

def test_modelo_xlsx_tem_abas_e_reimporta_vazio(banco_falso):
    from openpyxl import load_workbook

    corpo, tipo, nome = run(svc.gerar_modelo(None, "xlsx"))
    assert tipo == svc.MIME_XLSX and nome.endswith(".xlsx")
    wb = load_workbook(io.BytesIO(corpo))
    assert {"Instruções", "Produtos", "Categorias", "Exemplo"} <= set(wb.sheetnames)
    assert [c.value for c in wb["Categorias"]["A"]][1:] == ["Vestidos", "Streetwear"]
    # o modelo sem preencher importa sem erro e sem linhas
    r = run(svc.gerar_previa(None, uuid4(), tipo, corpo))
    assert r.total_linhas == 0


def test_modelo_csv_linha_de_exemplo_e_ignorada(banco_falso):
    corpo, tipo, _ = run(svc.gerar_modelo(None, "csv"))
    assert corpo.startswith(b"\xef\xbb\xbf")  # BOM para o Excel
    assert b"EXEMPLO-001" in corpo
    assert run(svc.gerar_previa(None, uuid4(), tipo, corpo)).total_linhas == 0


class SessaoExport:
    def __init__(self, looks):
        self.looks = looks

    async def execute(self, query):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(self.looks)))


@pytest.mark.parametrize("formato", ["csv", "xlsx"])
def test_exportar_e_reimportar_atualiza_a_mesma_peca(banco_falso, formato):
    look = SimpleNamespace(
        id=uuid4(), sku=None, name="=HYPERLINK(\"x\")", category_id=CAT_VESTIDOS.id, price=Decimal("1299.5"),
        stock_quantity=3, sizes=["P", "M"], photos=[FOTO, "https://cdn.exemplo.com/b.jpg"],
        description=None, buy_link=None, status="active", likes_count=4, saves_count=1,
        created_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    banco_falso.existentes = [look]
    corpo, tipo, nome = run(svc.exportar_catalogo(SessaoExport([look]), uuid4(), formato))
    assert nome.endswith(formato)
    if formato == "csv":
        assert b"'=HYPERLINK" in corpo  # não vira fórmula no Excel
        assert b"1299,50" in corpo
    r = run(svc.gerar_previa(None, uuid4(), tipo, corpo))
    assert r.colunas_ignoradas == []
    linha = r.linhas[0]
    assert linha.erros == [] and linha.acao == "atualizar" and linha.look_id == look.id
    assert linha.dados["name"] == "=HYPERLINK(\"x\")"
    assert linha.dados["price"] == "1299.50" and linha.dados["stock_quantity"] == 3
    assert linha.dados["photos"] == look.photos and linha.dados["sizes"] == ["P", "M"]


# ── rotas ─────────────────────────────────────────────────────────────────────

def test_rotas_de_massa_vem_antes_de_look_id():
    """Se `GET /looks/{look_id}` viesse antes, "export" seria lido como id (422).
    Com a ordem certa, a rota de exportação responde e pede login (401)."""
    from fastapi.testclient import TestClient
    import main

    cliente = TestClient(main.app)  # sem `with`: não roda o lifespan (sem banco)
    assert cliente.get("/api/looks/export").status_code == 401
    assert cliente.post("/api/looks/import/preview", content=b"x").status_code == 401
    assert cliente.patch("/api/looks/bulk", json={}).status_code in (401, 422)
