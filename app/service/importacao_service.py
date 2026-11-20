"""Importação, exportação e edição em massa de peças (looks) da loja.

Feito para brechós e lojas com centenas ou milhares de peças: hoje o app só
cadastra uma por vez. Ver `schemas/importacao.py` para o fluxo completo.

Decisões:
- A planilha é lida AQUI (CSV ou XLSX), não no app: uma regra só de colunas,
  números em formato brasileiro e tamanhos, e qualquer integração (ERP, script)
  pode usar a mesma API.
- A prévia não grava nada e não guarda estado no servidor (o Render pode ter
  várias instâncias e reinicia). Ela devolve as linhas já normalizadas; o app
  troca nomes de arquivo de foto pelos links enviados e grava com
  `POST /looks/bulk`, em lotes de até `MAX_ITENS_LOTE`.
- Linhas com erro não impedem as válidas: cada uma volta com a sua mensagem.
- A chave de atualização é o `id` (vem da exportação) ou o código da peça (`sku`).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from model.category import Category
from model.look import Look
from schemas.importacao import (
    CONDICOES,
    EdicaoEmMassa,
    EdicaoEmMassaResponse,
    ErroLote,
    ItemLote,
    LinhaPrevia,
    LoteRequest,
    LoteResponse,
    PreviaResponse,
)
from schemas.look import TAMANHOS_VALIDOS, normalizar_tamanhos
from service import inventory_service, seller_service

MAX_BYTES_PLANILHA = 5 * 1024 * 1024
MAX_LINHAS = 5000

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_CSV = "text/csv"

EXTENSOES_FOTO = (".jpg", ".jpeg", ".png", ".webp")
PREFIXO_EXEMPLO = "EXEMPLO"


# ── colunas ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Coluna:
    campo: str          # nome interno (ItemLote / Look)
    cabecalho: str      # como aparece no modelo
    apelidos: tuple     # outros nomes aceitos (já normalizados)
    descricao: str
    obrigatoria_ao_criar: bool = False
    # Campo do modelo `Look` que precisa existir para a coluna valer (as colunas da
    # gestão de estoque entram sozinhas quando o modelo passar a tê-las).
    requer_atributo: str | None = None


COLUNAS: list[Coluna] = [
    Coluna("id", "id", (), "Só na planilha exportada. Não altere: é o que liga a linha à peça já cadastrada."),
    Coluna("sku", "codigo", ("sku", "cod", "referencia", "ref", "codigodapeca", "codigointerno"),
           "Código da peça na sua loja (opcional, único). Reimportar com o mesmo código ATUALIZA a peça."),
    Coluna("name", "nome", ("produto", "titulo", "nomedapeca", "nomedoproduto"),
           "Nome da peça, de 2 a 120 letras.", obrigatoria_ao_criar=True),
    Coluna("category", "categoria", ("estilo",),
           "Nome da categoria (veja a aba Categorias).", obrigatoria_ao_criar=True),
    Coluna("price", "preco", ("valor", "precodevenda", "precovenda"),
           "Preço de venda. Aceita 89,90 ou 89.90 ou R$ 1.299,00. Vazio = sem preço."),
    Coluna("stock_quantity", "estoque", ("quantidade", "qtd", "qtde", "estoqueatual"),
           "Quantidade disponível (número inteiro). Vazio = 0 em peça nova."),
    Coluna("sizes", "tamanhos", ("tamanho", "tam", "grade"),
           "Tamanhos separados por vírgula. Ex.: P, M, G  ou  38, 40  ou  Único."),
    Coluna("photos", "fotos", ("foto", "imagens", "imagem", "urlfotos", "linksdasfotos"),
           "De 1 a 6 fotos separadas por | . Links https:// OU nomes de arquivo (ex.: vestido1.jpg) "
           "que você seleciona no app na hora de importar.", obrigatoria_ao_criar=True),
    Coluna("description", "descricao", ("detalhes", "observacoes"), "Descrição da peça (opcional)."),
    Coluna("buy_link", "link_compra", ("link", "linkdecompra", "linkcompra", "url"),
           "Link externo de compra (opcional)."),
    Coluna("brand", "marca", ("grife",), "Marca da peça (opcional).", requer_atributo="brand"),
    Coluna("condition", "condicao", ("estado", "conservacao"),
           f"Condição: {', '.join(CONDICOES)} (opcional).", requer_atributo="condition"),
    Coluna("cost_price", "custo", ("precodecusto", "precocusto", "custodapeca"),
           "Quanto a peça custou para você (opcional, não aparece para clientes).",
           requer_atributo="cost_price"),
]

# Colunas que a exportação escreve e a importação ignora sem avisar.
SOMENTE_LEITURA = {"situacao", "curtidas", "salvos", "criadoem"}


def _ativa(c: Coluna) -> bool:
    return c.requer_atributo is None or hasattr(Look, c.requer_atributo)


def colunas_ativas() -> list[Coluna]:
    return [c for c in COLUNAS if _ativa(c)]


def _norm(texto: str) -> str:
    """minúsculas, sem acento, só letras e números ("Preço*" → "preco")."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _mapa_cabecalhos() -> dict[str, Coluna]:
    mapa: dict[str, Coluna] = {}
    for c in colunas_ativas():
        for nome in (c.cabecalho, c.campo, *c.apelidos):
            mapa.setdefault(_norm(nome), c)
    return mapa


# ── leitura do arquivo ────────────────────────────────────────────────────────

def _eh_xlsx(content_type: str | None, corpo: bytes) -> bool:
    tipo = (content_type or "").split(";")[0].strip().lower()
    return corpo[:4] == b"PK\x03\x04" or tipo == MIME_XLSX


def _ler_csv(corpo: bytes) -> list[list]:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = corpo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    primeira = texto.split("\n", 1)[0]
    # Excel em português salva com ";" (a vírgula é o separador decimal).
    separador = max([";", ",", "\t"], key=primeira.count)
    linhas = []
    for i, linha in enumerate(csv.reader(io.StringIO(texto), delimiter=separador)):
        if i > MAX_LINHAS + 10:
            _muitas_linhas()
        linhas.append(linha)
    return linhas


def _ler_xlsx(corpo: bytes) -> list[list]:
    from openpyxl import load_workbook  # import tardio: só quem importa paga o custo

    try:
        wb = load_workbook(io.BytesIO(corpo), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 — arquivo corrompido/zip inválido
        raise HTTPException(status_code=400, detail="Não consegui abrir a planilha. Salve como .xlsx ou .csv e tente de novo.")
    try:
        planilha = None
        for ws in wb.worksheets:
            if _norm(ws.title) in ("produtos", "pecas", "itens"):
                planilha = ws
                break
        planilha = planilha or wb.worksheets[0]
        linhas = []
        for i, linha in enumerate(planilha.iter_rows(values_only=True)):
            if i > MAX_LINHAS + 10:
                _muitas_linhas()
            linhas.append(list(linha))
        return linhas
    finally:
        wb.close()


def _muitas_linhas():
    raise HTTPException(
        status_code=413,
        detail=f"Planilha com mais de {MAX_LINHAS} linhas. Divida em arquivos menores e importe um de cada vez.",
    )


def ler_planilha(content_type: str | None, corpo: bytes) -> list[list]:
    if not corpo:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(corpo) > MAX_BYTES_PLANILHA:
        raise HTTPException(status_code=413, detail="Planilha grande demais (máximo de 5 MB).")
    return _ler_xlsx(corpo) if _eh_xlsx(content_type, corpo) else _ler_csv(corpo)


def _celula_texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    texto = str(v).strip()
    # A exportação protege textos que começam com = + - @ (ver _seguro); desfaz aqui.
    if len(texto) > 1 and texto[0] == "'" and texto[1] in "=+-@":
        texto = texto[1:]
    return texto


@dataclass
class LinhaBruta:
    numero: int  # número da linha como a pessoa vê na planilha (1 = cabeçalho)
    valores: dict = field(default_factory=dict)  # campo -> valor cru da célula


def separar_linhas(tabela: list[list]) -> tuple[list[LinhaBruta], list[str]]:
    """Acha o cabeçalho (nas 10 primeiras linhas) e devolve as linhas de dados
    com os valores por campo, mais as colunas que não reconhecemos."""
    mapa = _mapa_cabecalhos()
    inicio, indices = None, {}
    for i, linha in enumerate(tabela[:10]):
        achados = {}
        for j, cel in enumerate(linha):
            col = mapa.get(_norm(_celula_texto(cel)))
            if col and col.campo not in achados.values():
                achados[j] = col.campo
        if "name" in achados.values() or len(achados) >= 3:
            inicio, indices = i, achados
            break
    if inicio is None:
        raise HTTPException(
            status_code=400,
            detail="Não encontrei o cabeçalho da planilha. Use o modelo: a primeira linha precisa ter "
                   "as colunas nome, categoria e fotos.",
        )
    ignoradas = []
    for j, cel in enumerate(tabela[inicio]):
        nome = _celula_texto(cel)
        if nome and j not in indices and _norm(nome) not in SOMENTE_LEITURA:
            ignoradas.append(nome)

    linhas = []
    for k, linha in enumerate(tabela[inicio + 1:], start=inicio + 2):
        valores = {campo: linha[j] for j, campo in indices.items() if j < len(linha)}
        if all(_celula_texto(v) == "" for v in valores.values()):
            continue  # linha em branco
        if _celula_texto(valores.get("sku")).upper().startswith(PREFIXO_EXEMPLO):
            continue  # linha de exemplo do modelo
        linhas.append(LinhaBruta(numero=k, valores=valores))
        if len(linhas) > MAX_LINHAS:
            _muitas_linhas()
    return linhas, ignoradas


# ── conversão de células ──────────────────────────────────────────────────────

def parse_preco(v) -> Decimal | None:
    """Número em formato brasileiro ou internacional. Vazio → None."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        valor = Decimal(str(v))
    else:
        texto = re.sub(r"[^\d,.\-]", "", str(v))
        if not texto or texto in "-.,":
            raise ValueError(f"valor inválido: {str(v)!r}")
        if "," in texto and "." in texto:
            # o último separador é o decimal: 1.234,56 ou 1,234.56
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            if texto.count(",") > 1:
                raise ValueError(f"valor inválido: {str(v)!r}")
            texto = texto.replace(",", ".")
        elif texto.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", texto):
            # 1.234.567 ou 1.500 (milhar no formato brasileiro)
            texto = texto.replace(".", "")
        try:
            valor = Decimal(texto)
        except InvalidOperation:
            raise ValueError(f"valor inválido: {str(v)!r}")
    if valor < 0:
        raise ValueError("não pode ser negativo")
    return valor.quantize(Decimal("0.01"))


def parse_inteiro(v) -> int | None:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        if Decimal(str(v)) != Decimal(str(v)).to_integral_value():
            raise ValueError(f"precisa ser um número inteiro (recebido {v})")
        return int(v)
    texto = str(v).strip().replace(".", "")
    texto = re.sub(r",0+$", "", texto)
    if not re.fullmatch(r"-?\d+", texto):
        raise ValueError(f"precisa ser um número inteiro (recebido {str(v)!r})")
    return int(texto)


def parse_tamanhos(v) -> list[str]:
    partes = [p for p in re.split(r"[,;/|\n]+", _celula_texto(v)) if p.strip()]
    if len(partes) == 1 and " " in partes[0].strip() and _norm(partes[0]) != "unico":
        partes = partes[0].split()  # "P M G"
    return normalizar_tamanhos(partes) or []


def parse_fotos_em_ordem(v) -> list[str]:
    """Fotos da célula, na ordem. Separadores: | ; quebra de linha, ou
    vírgula/espaço antes de outro link."""
    partes = re.split(r"[|;\n]+|[,\s]+(?=https?://)", _celula_texto(v))
    return [p.strip() for p in partes if p.strip()]


def parse_fotos(v) -> tuple[list[str], list[str]]:
    """Devolve (links, nomes de arquivo)."""
    links, arquivos = [], []
    for p in parse_fotos_em_ordem(v):
        if re.match(r"https?://", p, re.I):
            links.append(p)
        else:
            arquivos.append(p)
    return links, arquivos


def _nome_arquivo_valido(nome: str) -> bool:
    return nome.lower().endswith(EXTENSOES_FOTO) and "/" not in nome and "\\" not in nome


# ── prévia ────────────────────────────────────────────────────────────────────

async def _loja(db: AsyncSession, user_id: UUID):
    seller = await seller_service.get_seller_by_owner(db, user_id)
    if not seller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas vendedores podem importar ou editar peças em massa",
        )
    return seller


async def _categorias(db: AsyncSession) -> list[Category]:
    res = await db.execute(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name)
    )
    return list(res.scalars().all())


def _indice_categorias(categorias: list[Category]) -> dict[str, Category]:
    indice = {}
    for c in categorias:
        indice.setdefault(_norm(c.name), c)
        indice.setdefault(_norm(c.slug), c)
        indice.setdefault(str(c.id), c)
    return indice


async def _existentes(db: AsyncSession, seller_id: UUID, ids: set, skus: set) -> list[Look]:
    if not ids and not skus:
        return []
    condicoes = []
    if ids:
        condicoes.append(Look.id.in_(list(ids)))
    if skus:
        condicoes.append(Look.sku.in_(list(skus)))
    res = await db.execute(select(Look).where(Look.seller_id == seller_id, or_(*condicoes)))
    return list(res.scalars().all())


_ROTULO = {c.campo: c.cabecalho for c in COLUNAS} | {"category_id": "categoria"}


def _mensagem_validacao(e: ValidationError) -> list[str]:
    msgs = []
    for erro in e.errors(include_url=False, include_context=False, include_input=False):
        campo = erro["loc"][0] if erro["loc"] else ""
        texto = erro["msg"].removeprefix("Value error, ")
        rotulo = _ROTULO.get(str(campo))
        msgs.append(f"{rotulo}: {texto}" if rotulo else texto)
    return msgs


def _uuid_ou_none(v) -> UUID | None:
    texto = _celula_texto(v)
    if not texto:
        return None
    try:
        return UUID(texto)
    except ValueError:
        raise ValueError("id inválido (use a planilha exportada sem alterar esta coluna)")


async def gerar_previa(db: AsyncSession, user_id: UUID, content_type: str | None, corpo: bytes) -> PreviaResponse:
    seller = await _loja(db, user_id)
    tabela = ler_planilha(content_type, corpo)
    brutas, ignoradas = separar_linhas(tabela)

    categorias = _indice_categorias(await _categorias(db))

    # 1ª passada: converte as células (sem banco)
    convertidas = []  # (bruta, dados, erros, arquivos, look_id)
    ids, skus = set(), set()
    for bruta in brutas:
        v, dados, erros, arquivos, look_id = bruta.valores, {}, [], [], None

        def tentar(rotulo, fn, *args):
            try:
                return fn(*args)
            except ValueError as ex:
                erros.append(f"{rotulo}: {str(ex).removeprefix('Value error, ')}")
                return None

        look_id = tentar("id", _uuid_ou_none, v.get("id"))
        sku = _celula_texto(v.get("sku"))
        if sku:
            dados["sku"] = sku
        for campo in ("name", "description", "buy_link", "brand"):
            texto = _celula_texto(v.get(campo))
            if texto:
                dados[campo] = texto
        cond = _celula_texto(v.get("condition"))
        if cond:
            dados["condition"] = _norm(cond)
        cat = _celula_texto(v.get("category"))
        if cat:
            achada = categorias.get(_norm(cat)) or categorias.get(cat)
            if achada:
                dados["category_id"] = str(achada.id)
            else:
                erros.append(f"categoria: {cat!r} não existe. Veja a aba Categorias do modelo.")
        for campo, rotulo in (("price", "preco"), ("cost_price", "custo")):
            if campo in v:
                preco = tentar(rotulo, parse_preco, v.get(campo))
                if preco is not None:
                    dados[campo] = str(preco)
        if "stock_quantity" in v:
            estoque = tentar("estoque", parse_inteiro, v.get("stock_quantity"))
            if estoque is not None:
                dados["stock_quantity"] = estoque
        if _celula_texto(v.get("sizes")):
            tamanhos = tentar("tamanhos", parse_tamanhos, v.get("sizes"))
            if tamanhos is not None:
                dados["sizes"] = tamanhos
        ordem = []
        if _celula_texto(v.get("photos")):
            links, arquivos = parse_fotos(v.get("photos"))
            ordem = [p for p in parse_fotos_em_ordem(v.get("photos")) if p in links or _nome_arquivo_valido(p)]
            for a in arquivos:
                if not _nome_arquivo_valido(a):
                    erros.append(f"fotos: {a!r} não é um link https:// nem um arquivo .jpg/.png/.webp")
            arquivos = [a for a in arquivos if _nome_arquivo_valido(a)]
            if links:
                dados["photos"] = links
            if len(links) + len(arquivos) > 6:
                erros.append("fotos: no máximo 6 por peça")

        if look_id:
            ids.add(look_id)
        if sku:
            skus.add(sku)
        convertidas.append((bruta, dados, erros, arquivos, look_id, ordem))

    existentes = await _existentes(db, seller.id, ids, skus)
    por_id = {l.id: l for l in existentes}
    por_sku = {l.sku: l for l in existentes if l.sku}

    # 2ª passada: decide criar/atualizar e valida as regras
    linhas, vistos_sku, todos_arquivos = [], {}, []
    for bruta, dados, erros, arquivos, look_id, ordem in convertidas:
        alvo = None
        if look_id:
            alvo = por_id.get(look_id)
            if alvo is None:
                erros.append("id: peça não encontrada na sua loja")
        elif dados.get("sku"):
            alvo = por_sku.get(dados["sku"])
        sku = dados.get("sku")
        if sku:
            if sku in vistos_sku:
                erros.append(f"codigo: {sku!r} repetido (já está na linha {vistos_sku[sku]})")
            else:
                vistos_sku[sku] = bruta.numero
            dono = por_sku.get(sku)
            if alvo is not None and dono is not None and dono.id != alvo.id:
                erros.append(f"codigo: {sku!r} já é de outra peça da loja")

        acao = "atualizar" if alvo is not None or look_id else "criar"
        if acao == "criar":
            faltando = [rot for campo, rot in (("name", "nome"), ("category_id", "categoria")) if campo not in dados]
            if "photos" not in dados and not arquivos:
                faltando.append("fotos")
            # categoria inválida já gerou erro próprio
            faltando = [f for f in faltando if not (f == "categoria" and _celula_texto(bruta.valores.get("category")))]
            if faltando:
                erros.append(f"obrigatório para peça nova: {', '.join(faltando)}")

        # valida o resto pelas mesmas regras de `POST /looks/bulk` (fotos pendentes à parte)
        checagem = {k: v for k, v in dados.items() if k != "photos" or not arquivos}
        try:
            ItemLote.model_validate(checagem)
        except ValidationError as ex:
            erros.extend(_mensagem_validacao(ex))

        if alvo is not None:
            dados["id"] = str(alvo.id)
        todos_arquivos.extend(a for a in arquivos if a not in todos_arquivos)
        linhas.append(LinhaPrevia(
            linha=bruta.numero,
            acao=acao,
            look_id=alvo.id if alvo is not None else None,
            dados=dados,
            fotos=ordem,
            fotos_pendentes=arquivos,
            erros=list(dict.fromkeys(erros)),
        ))

    validas = [l for l in linhas if not l.erros]
    return PreviaResponse(
        total_linhas=len(linhas),
        validas=len(validas),
        com_erro=len(linhas) - len(validas),
        a_criar=sum(1 for l in validas if l.acao == "criar"),
        a_atualizar=sum(1 for l in validas if l.acao == "atualizar"),
        arquivos_de_foto=todos_arquivos,
        colunas_ignoradas=ignoradas,
        linhas=linhas,
    )


# ── gravação em lote ──────────────────────────────────────────────────────────

# Campos que não podem virar NULL numa atualização (o banco exige valor).
_OBRIGATORIOS = {"name", "category_id", "photos", "stock_quantity", "sizes"}


def _campos_gravaveis(item: ItemLote) -> dict:
    campos = item.model_dump(exclude_unset=True, exclude={"linha", "id"})
    return {
        k: v for k, v in campos.items()
        if hasattr(Look, k) and not (v is None and k in _OBRIGATORIOS)
    }


async def gravar_lote(db: AsyncSession, user_id: UUID, pedido: LoteRequest) -> LoteResponse:
    seller = await _loja(db, user_id)

    erros: list[ErroLote] = []
    itens: list[tuple[int, ItemLote]] = []
    for i, bruto in enumerate(pedido.itens):
        linha = bruto.get("linha") if isinstance(bruto, dict) else None
        try:
            itens.append((i, ItemLote.model_validate(bruto)))
        except ValidationError as ex:
            erros.append(ErroLote(indice=i, linha=linha if isinstance(linha, int) else None,
                                  mensagem="; ".join(_mensagem_validacao(ex))))

    ids = {it.id for _, it in itens if it.id}
    skus = {it.sku for _, it in itens if it.sku}
    existentes = await _existentes(db, seller.id, ids, skus)
    por_id = {l.id: l for l in existentes}
    por_sku = {l.sku: l for l in existentes if l.sku}

    cat_ids = {it.category_id for _, it in itens if it.category_id}
    validas = set()
    if cat_ids:
        res = await db.execute(select(Category.id).where(Category.id.in_(list(cat_ids))))
        validas = {UUID(str(c)) for c in res.scalars().all()}

    novos: list[Look] = []
    atualizados: list[Look] = []
    movimentos: list = []
    skus_no_lote: set[str] = set()
    for i, it in itens:
        def falha(msg):
            erros.append(ErroLote(indice=i, linha=it.linha, mensagem=msg))

        alvo = por_id.get(it.id) if it.id else por_sku.get(it.sku) if it.sku else None
        if it.id and alvo is None:
            falha("Peça não encontrada na sua loja.")
            continue
        if it.category_id and it.category_id not in validas:
            falha("Categoria inexistente.")
            continue
        if it.sku:
            if it.sku in skus_no_lote:
                falha(f"Código {it.sku!r} repetido no mesmo envio.")
                continue
            dono = por_sku.get(it.sku)
            if dono is not None and alvo is not None and dono.id != alvo.id:
                falha(f"Código {it.sku!r} já é de outra peça da loja.")
                continue

        campos = _campos_gravaveis(it)
        if alvo is not None:
            estoque_antes = alvo.stock_quantity or 0
            for k, v in campos.items():
                setattr(alvo, k, v)
            if "stock_quantity" in campos and campos["stock_quantity"] != estoque_antes:
                # Mesma regra da edição da peça: reserva nunca maior que o estoque,
                # e a mudança entra no histórico de movimentações.
                alvo.reserved_quantity = min(alvo.reserved_quantity or 0, alvo.stock_quantity)
                movimentos.append(inventory_service.novo_movimento(
                    alvo, "ajuste", alvo.stock_quantity - estoque_antes, user_id=user_id,
                    note="Importação por planilha",
                ))
            atualizados.append(alvo)
        else:
            faltando = [rot for k, rot in (("name", "nome"), ("category_id", "categoria"), ("photos", "fotos"))
                        if not campos.get(k)]
            if faltando:
                falha(f"Obrigatório para peça nova: {', '.join(faltando)}.")
                continue
            look = Look(seller_id=seller.id, status=pedido.status, **campos)
            novos.append(look)
        if it.sku:
            skus_no_lote.add(it.sku)

    if novos or atualizados:
        # Um `created_at` diferente por peça: com o `now()` do banco, o lote inteiro
        # teria o MESMO instante, e a paginação por data (feed, `/looks/mine`) usa
        # `created_at < cursor` — as peças empatadas depois da 1ª página sumiriam.
        # A 1ª linha da planilha fica como a mais recente (aparece primeiro).
        agora = datetime.now(timezone.utc)
        for k, look in enumerate(novos):
            look.created_at = agora - timedelta(microseconds=k)
        db.add_all(novos)
        try:
            await db.flush()  # gera os ids das peças novas (o histórico aponta para elas)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível salvar este lote (algum código de peça pode já estar em uso). "
                       "Nada deste lote foi gravado.",
            )
        for look in novos:
            if look.stock_quantity:
                movimentos.append(inventory_service.novo_movimento(
                    look, "entrada", look.stock_quantity, user_id=user_id, note="Importação por planilha",
                ))
        db.add_all(movimentos)
        try:
            await db.flush()
            ids_ok = [l.id for l in novos] + [l.id for l in atualizados]
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Não foi possível salvar este lote (algum código de peça pode já estar em uso). "
                       "Nada deste lote foi gravado.",
            )
    else:
        ids_ok = []

    erros.sort(key=lambda e: e.indice)
    return LoteResponse(criados=len(novos), atualizados=len(atualizados), ids=ids_ok, erros=erros)


# ── edição em massa ───────────────────────────────────────────────────────────

async def editar_em_massa(db: AsyncSession, user_id: UUID, dados: EdicaoEmMassa) -> EdicaoEmMassaResponse:
    """Aplica o mesmo ajuste em várias peças da loja (até 500), numa transação.
    Só mexe em peças `active`/`draft` da própria loja: as que estão em moderação
    (`under_review`/`removed`) ou são de outra loja são contadas como ignoradas.
    Mudança de estoque entra no histórico (`stock_movements`, tipo ajuste) e a
    reserva é cortada se ficar maior que o estoque — a mesma regra da edição."""
    seller = await _loja(db, user_id)
    ids = list(dict.fromkeys(dados.ids))

    if dados.category_id is not None:
        cat = await db.execute(select(Category.id).where(Category.id == dados.category_id))
        if cat.scalar_one_or_none() is None:
            raise HTTPException(status_code=400, detail="Categoria inexistente")

    res = await db.execute(
        select(Look)
        .where(Look.seller_id == seller.id, Look.id.in_(ids), Look.status.in_(["active", "draft"]))
        .with_for_update()
    )
    looks = list(res.scalars().all())

    fator = None
    if dados.price_percent is not None:
        fator = (Decimal(100) + dados.price_percent) / Decimal(100)
    for look in looks:
        if dados.price is not None:
            look.price = dados.price
        if fator is not None and look.price is not None:  # sem preço continua sem
            look.price = (Decimal(look.price) * fator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if dados.status is not None:
            look.status = dados.status
        if dados.category_id is not None:
            look.category_id = dados.category_id
        if dados.stock_quantity is not None or dados.stock_delta is not None:
            antes = look.stock_quantity or 0
            novo = dados.stock_quantity if dados.stock_quantity is not None else max(antes + dados.stock_delta, 0)
            if novo != antes:
                look.stock_quantity = novo
                look.reserved_quantity = min(look.reserved_quantity or 0, novo)
                db.add(inventory_service.novo_movimento(
                    look, "ajuste", novo - antes, user_id=user_id, note="Edição em massa",
                ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Não foi possível aplicar a alteração — confira os valores.")
    return EdicaoEmMassaResponse(atualizados=len(looks), ignorados=len(ids) - len(looks))


# ── modelo e exportação ───────────────────────────────────────────────────────

def _seguro(v):
    """Texto que começa com = + - @ vira fórmula no Excel (injeção de fórmula).
    Prefixa com apóstrofo; a importação tira o apóstrofo de volta."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _exemplo(categoria: str) -> dict:
    return {
        "sku": f"{PREFIXO_EXEMPLO}-001",
        "name": "Vestido midi floral (linha de exemplo, é ignorada)",
        "category": categoria,
        "price": "89,90",
        "stock_quantity": "1",
        "sizes": "M",
        "photos": "https://exemplo.com/vestido-frente.jpg | vestido-costas.jpg",
        "description": "Viscose, forro inteiro. Pequeno desgaste na barra.",
        "buy_link": "",
        "brand": "Farm",
        "condition": "seminovo",
        "cost_price": "25,00",
    }


def _csv_bytes(cabecalhos: list[str], linhas: list[list]) -> bytes:
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(cabecalhos)
    for linha in linhas:
        w.writerow(["" if v is None else _seguro(v) for v in linha])
    return saida.getvalue().encode("utf-8-sig")  # BOM: o Excel abre com acentos certos


def _xlsx_bytes(cabecalhos: list[str], linhas: list[list], categorias: list[Category],
                instrucoes: bool, colunas: list[Coluna]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Produtos"
    ws.append(cabecalhos)
    negrito = Font(bold=True)
    fundo = PatternFill("solid", fgColor="F3E9D2")
    for cel in ws[1]:
        cel.font = negrito
        cel.fill = fundo
    for linha in linhas:
        ws.append([_seguro(v) for v in linha])
    larguras = {"nome": 40, "fotos": 60, "descricao": 40, "categoria": 18, "id": 38, "link_compra": 30}
    for j, cab in enumerate(cabecalhos, start=1):
        ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = larguras.get(cab, 14)
    ws.freeze_panes = "A2"

    cats = wb.create_sheet("Categorias")
    cats.append(["categoria"])
    cats["A1"].font = negrito
    for c in categorias:
        cats.append([c.name])
    cats.column_dimensions["A"].width = 30
    if categorias and "categoria" in cabecalhos:
        col = ws.cell(row=1, column=cabecalhos.index("categoria") + 1).column_letter
        dv = DataValidation(type="list", formula1=f"=Categorias!$A$2:$A${len(categorias) + 1}", allow_blank=True)
        dv.error = "Escolha uma categoria da lista"
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{MAX_LINHAS + 1}")

    if instrucoes:
        ins = wb.create_sheet("Instruções", 0)
        ins.append(["Como preencher"])
        ins["A1"].font = Font(bold=True, size=14)
        ins.append(["Preencha a aba Produtos: uma peça por linha. Linhas em branco são ignoradas."])
        ins.append(["Até 5.000 peças por arquivo. Depois, no app: Itens > Importar planilha."])
        ins.append([])
        ins.append(["coluna", "obrigatória?", "o que colocar"])
        for cel in ins[5]:
            cel.font = negrito
        for c in colunas:
            if c.campo == "id":
                continue
            ins.append([c.cabecalho, "sim, em peça nova" if c.obrigatoria_ao_criar else "não", c.descricao])
        ins.append([])
        ins.append(["Tamanhos aceitos:", ", ".join(TAMANHOS_VALIDOS)])
        ins.append(["Fotos por nome de arquivo:", "no app você escolhe as imagens; elas são ligadas pelo nome exato do arquivo."])
        ins.append(["Atualizar peças:", "exporte o catálogo (Itens > Exportar), altere preço/estoque e importe de novo."])
        ins.column_dimensions["A"].width = 26
        ins.column_dimensions["B"].width = 18
        ins.column_dimensions["C"].width = 100

        ex = wb.create_sheet("Exemplo")
        ex.append(cabecalhos)
        for cel in ex[1]:
            cel.font = negrito
        exemplo = _exemplo(categorias[0].name if categorias else "Casual")
        ex.append([_seguro(exemplo.get(c.campo, "")) for c in colunas if c.campo != "id"])
        wb.active = 1  # abre na aba Produtos

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def gerar_modelo(db: AsyncSession, formato: str) -> tuple[bytes, str, str]:
    colunas = [c for c in colunas_ativas() if c.campo != "id"]
    cabecalhos = [c.cabecalho for c in colunas]
    categorias = await _categorias(db)
    if formato == "csv":
        exemplo = _exemplo(categorias[0].name if categorias else "Casual")
        corpo = _csv_bytes(cabecalhos, [[exemplo.get(c.campo, "") for c in colunas]])
        return corpo, MIME_CSV + "; charset=utf-8", "modelo-importacao-lookly.csv"
    corpo = _xlsx_bytes(cabecalhos, [], categorias, instrucoes=True, colunas=colunas)
    return corpo, MIME_XLSX, "modelo-importacao-lookly.xlsx"


_SITUACAO = {"active": "ativa", "draft": "rascunho", "under_review": "em revisão", "removed": "removida"}


async def exportar_catalogo(db: AsyncSession, user_id: UUID, formato: str) -> tuple[bytes, str, str]:
    """Catálogo inteiro da loja na mesma planilha da importação (com `id`), para
    editar preço/estoque em massa no Excel e importar de volta."""
    seller = await _loja(db, user_id)
    categorias = await _categorias(db)
    nomes_cat = {c.id: c.name for c in categorias}
    res = await db.execute(
        select(Look).where(Look.seller_id == seller.id).order_by(Look.created_at.desc())
    )
    looks = list(res.scalars().all())
    # categorias inativas também precisam de nome na exportação
    faltam = {l.category_id for l in looks} - set(nomes_cat)
    if faltam:
        extra = await db.execute(select(Category).where(Category.id.in_(list(faltam))))
        nomes_cat |= {c.id: c.name for c in extra.scalars().all()}

    colunas = colunas_ativas()
    cabecalhos = [c.cabecalho for c in colunas] + ["situacao", "curtidas", "salvos", "criado_em"]
    xlsx = formato != "csv"

    def preco(v):
        if v is None:
            return None if xlsx else ""
        return float(v) if xlsx else f"{Decimal(v):.2f}".replace(".", ",")

    linhas = []
    for l in looks:
        valores = {
            "id": str(l.id),
            "sku": l.sku or "",
            "name": l.name,
            "category": nomes_cat.get(l.category_id, ""),
            "price": preco(l.price),
            "stock_quantity": l.stock_quantity,
            "sizes": ", ".join(l.sizes or []),
            "photos": " | ".join(l.photos or []),
            "description": l.description or "",
            "buy_link": l.buy_link or "",
            "brand": getattr(l, "brand", None) or "",
            "condition": getattr(l, "condition", None) or "",
            "cost_price": preco(getattr(l, "cost_price", None)),
        }
        criado = l.created_at.strftime("%d/%m/%Y") if l.created_at else ""
        linhas.append([valores[c.campo] for c in colunas]
                      + [_SITUACAO.get(str(l.status), str(l.status)), l.likes_count, l.saves_count, criado])

    hoje = date.today().isoformat()
    if not xlsx:
        return _csv_bytes(cabecalhos, linhas), MIME_CSV + "; charset=utf-8", f"catalogo-lookly-{hoje}.csv"
    corpo = _xlsx_bytes(cabecalhos, linhas, categorias, instrucoes=False, colunas=colunas)
    return corpo, MIME_XLSX, f"catalogo-lookly-{hoje}.xlsx"
