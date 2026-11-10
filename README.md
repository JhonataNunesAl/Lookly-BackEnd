# Lucker — Backend (API)

Backend do **Lucker**, um app de moda no estilo Tinder: o usuário desliza por "looks"
(cards), curte/descarta, salva no armário e organiza em coleções. Este repositório contém a
**API em FastAPI**. A autenticação e o banco ficam no **Supabase**; o app (React Native) consome
esta API enviando o token do Supabase.

> Documento de visão do produto e requisitos: [`Requisitos.txt`](Requisitos.txt).

---

## Stack

| Camada        | Tecnologia                                   |
|---------------|----------------------------------------------|
| API           | FastAPI (assíncrono)                          |
| ORM / DB      | SQLAlchemy 2 (async) + asyncpg → PostgreSQL   |
| Auth          | Supabase Auth (JWT validado na API)           |
| Banco/Storage | Supabase (PostgreSQL + RLS)                   |
| Rate limit    | SlowAPI                                       |
| Validação     | Pydantic v2                                   |

---

## Arquitetura

A API segue uma arquitetura em camadas. Cada requisição percorre:

```
main.py            → cria o app, CORS, rate limit, monta as rotas sob /api
   │
routers.py         → agrega todos os controllers
   │
controller/*       → define as rotas HTTP e as dependências (auth, sessão de banco)
   │
service/*          → regras de negócio e queries assíncronas
   │
model/*  +  schemas/*   → ORM (tabelas) e contratos de entrada/saída (Pydantic)
```

Princípio central: **cada serviço filtra os dados pelo `user_id`** extraído do token. As políticas
RLS no banco (`schema.sql`) são uma segunda camada de proteção, caso o app acesse o Supabase
diretamente.

### Estrutura de pastas

```
.
├── Dockerfile              # imagem para o Render (copia o CONTEÚDO de app/ para /app)
├── iniciar.sh              # sobe a API local (cd app + uvicorn --host 0.0.0.0)
├── schema.sql / nem_schema.sql   # esquema do banco (rodar no Supabase) — fonte de verdade
├── migrations/ + alembic.ini     # histórico Alembic (o banco vivo tem mudanças fora dele — ver CLAUDE.md)
├── sql/                    # scripts avulsos para o SQL Editor do Supabase (partições de look_views, fotos de exemplo, `filtros_busca.sql` = coluna de tamanhos)
├── CART_ISSUES.md          # histórico dos problemas do carrinho (e o que foi resolvido)
└── app/                    # TODO o código roda de dentro daqui (imports absolutos)
    ├── main.py             # ponto de entrada (FastAPI app, CORS, rate limit, logging)
    ├── routers.py          # registra os controllers sob /api
    ├── requirements.txt
    ├── core/               # config.py (.env), security.py (JWT), crypto.py (cifra do documento),
    │                       # cnpj_lookup.py / document_validation.py (CPF/CNPJ), rate_limiter.py, logging_config.py,
    │                       # log_scrub.py (limpa segredos/dados pessoais de logs), body_limit.py, schema_guard.py
    ├── db/database.py      # engine async + get_db()
    ├── dependencies/auth.py# get_current_user_id
    ├── model/              # tabelas SQLAlchemy (profile, body_profile, seller, category, look, signal,
    │                       # saved_look, collection, report, cart, cart_items, orders, orders_items, address)
    ├── schemas/            # contratos Pydantic de entrada/saída
    ├── controller/         # rotas por domínio (profile, body_profile, seller, category, look, feed,
    │                       # swipe, wardrobe, report, cart, cart_items, upload)
    ├── service/            # regras de negócio e queries assíncronas
    └── tests/              # 176 testes, sem banco nem rede (cd app && python -m pytest tests -q)
```

---

## Autenticação

A API **não** faz cadastro/login nem guarda senhas — isso é responsabilidade do **Supabase Auth**.

1. O app autentica o usuário no Supabase (e-mail/senha, Google, Apple, Facebook).
2. O Supabase devolve um **access token (JWT)**.
3. O app chama esta API com o header `Authorization: Bearer <jwt>`.
4. [`app/dependencies/auth.py`](app/dependencies/auth.py) → `get_current_user_id` valida o token
   ([`app/core/security.py`](app/core/security.py): assinatura **assimétrica (ES256/RS256) via JWKS** do
   projeto — o padrão dos projetos novos do Supabase — ou HS256 com o `SUPABASE_JWT_SECRET` legado;
   mais expiração e audience `authenticated`; biblioteca **PyJWT**, com a lista de algoritmos definida
   pelo tipo da chave e nunca pelo cabeçalho do token) e retorna o `id` do usuário (igual a `profiles.id`).

Requisições sem token, ou com token inválido/expirado, recebem **401** (versões antigas do FastAPI
davam 403 para token ausente).

---

## Endpoints

Todos sob o prefixo `/api`. 🔒 = exige token. **As rotas do carrinho terminam com `/`**
(sem a barra o FastAPI responde 307 e alguns clientes perdem o `Authorization`).

### Perfil
| Método | Rota                              | Descrição                                                        |
|--------|-----------------------------------|------------------------------------------------------------------|
| GET 🔒 | `/profiles/me`                    | Perfil do usuário + papel real (`is_seller`, `seller_id`)        |
| PUT 🔒 | `/profiles/me`                    | Atualiza username, nome, foto, bio, `birth_date` (18+)           |
| GET 🔒 | `/profiles/me/category-affinity`  | Afinidade por categoria (pontuada por triggers em curtir/salvar) |
| DELETE 🔒 | `/profiles/me`                 | **Exclui a conta** (LGPD / Play Store). Corpo `{"confirmacao": "EXCLUIR"}`; 204. Apaga loja, peças, dados, arquivos e o login; **409** se houver pedidos; 3/hora. Exige `SUPABASE_SERVICE_KEY` |

### Dados corporais (sensíveis — só o dono)
| Método  | Rota                      | Descrição                                                    |
|---------|---------------------------|--------------------------------------------------------------|
| GET 🔒  | `/body-profile/me`        | Peso/altura/medidas (texto; o servidor cifra em repouso) e chave da foto |
| PUT 🔒  | `/body-profile/me`        | Grava as medidas e `body_photo_key`                          |
| POST 🔒 | `/body-profile/me/consent`| Concede consentimento de IA (LGPD, versionado)               |
| DELETE🔒| `/body-profile/me/consent`| Revoga o consentimento                                       |

### Vendedores (lojas/marcas que postam looks)
| Método | Rota                       | Descrição                                                              |
|--------|----------------------------|------------------------------------------------------------------------|
| POST 🔒| `/sellers`                 | Cria a loja do usuário (`owner_profile_id`)                            |
| GET 🔒 | `/sellers/me`              | Dados da própria loja                                                  |
| PUT 🔒 | `/sellers/me`              | Atualiza a loja                                                        |
| POST 🔒| `/sellers/verify-document` | Prévia: valida CPF/CNPJ (dígitos + BrasilAPI) sem gravar               |
| PUT 🔒 | `/sellers/me/document`     | Grava o documento (recebe texto; o servidor valida, cifra e guarda hash) |
| GET    | `/sellers/search?q=&cursor=` | Busca lojas                                                          |
| GET    | `/sellers/{id}`            | Vitrine pública da loja                                                |
| GET    | `/sellers/{id}/looks`      | Looks ativos da loja (paginado)                                        |

### Categorias
| Método | Rota           | Descrição                       |
|--------|----------------|---------------------------------|
| GET    | `/categories`  | Lista categorias (público). Não há `POST`: criar categoria é feito direto no banco |

### Looks
| Método | Rota                          | Descrição                                                    |
|--------|-------------------------------|--------------------------------------------------------------|
| POST 🔒| `/looks`                      | Cria look (só vendedores; categoria + 1–6 fotos, ≤ 2 vídeos; `stock_quantity` opcional) |
| GET    | `/looks/search` | Busca looks ativos (não exclui os já vistos). Parâmetros: `q`, `category`, `price_min`, `price_max`, `sizes` (repetido: `sizes=P&sizes=M`), `in_stock`, `sort` (`recent`\|`price_asc`\|`price_desc`\|`popular`), `limit`, `cursor` |
| GET 🔒 | `/looks/mine`                 | Todos os looks da própria loja, de qualquer `status`         |
| GET    | `/looks/{id}`                 | Detalhe do look                                              |
| PUT 🔒 | `/looks/{id}`                 | Atualiza (só quem gerencia a loja) — inclusive `stock_quantity` |
| DELETE🔒| `/looks/{id}`                | Remove (só quem gerencia a loja)                             |
| GET    | `/looks/{id}/share`           | Payload de compartilhamento (link/WhatsApp)                  |

### Feed (funcionalidade central)
| Método | Rota                                       | Descrição                                                                     |
|--------|--------------------------------------------|-------------------------------------------------------------------------------|
| GET 🔒 | `/feed?category=<slug>&limit=&cursor=`     | Looks ativos que o usuário **ainda não** viu (paginado, por `created_at`). `category` é **opcional** |

### Swipe
| Método | Rota       | Descrição                                                                          |
|--------|------------|------------------------------------------------------------------------------------|
| POST 🔒| `/swipes`  | Registra swipe (`look_views`). `RIGHT` curte (`look_likes`); **não** salva no armário |

### Armário e coleções
| Método  | Rota                                                | Descrição                                       |
|---------|-----------------------------------------------------|-------------------------------------------------|
| POST 🔒 | `/saved-looks`                                      | Salva um look (gesto deliberado, `{look_id}`)   |
| GET 🔒  | `/saved-looks`                                      | Lista o armário                                 |
| DELETE🔒| `/saved-looks/{look_id}`                            | Remove do armário                               |
| GET 🔒  | `/collections`                                      | Lista coleções (pastas)                         |
| POST 🔒 | `/collections`                                      | Cria coleção                                    |
| GET 🔒  | `/collections/{id}/looks`                           | Looks de uma coleção                            |
| POST 🔒 | `/collections/{id}/looks`                           | Adiciona look à coleção                         |
| DELETE🔒| `/collections/{id}/looks/{look_id}`                 | Remove look da coleção                          |

### Carrinho
O registro `Cart` do usuário é criado por um **trigger do Supabase** (não por esta API); as
rotas assumem que ele existe. A quantidade é **por delta** (não há "definir N").

| Método  | Rota                              | Descrição                                                                 |
|---------|-----------------------------------|---------------------------------------------------------------------------|
| GET 🔒  | `/cart/user/`                     | Carrinho do usuário                                                       |
| POST 🔒 | `/cart-items/`                    | Adiciona um look (400 se já está no carrinho — para somar use `add`; 400 se sem estoque) |
| GET 🔒  | `/cart-items/user/`               | Itens do carrinho (com os looks)                                          |
| PUT 🔒  | `/cart-items/add/{look_id}/`      | Soma `quantity` ao item (400 "Estoque insuficiente" se passar do estoque) |
| PUT 🔒  | `/cart-items/remove/{look_id}/`   | Subtrai `quantity`. **Chegar a zero dá 500** (ver `CART_ISSUES.md`) — para remover use o `DELETE` |
| DELETE🔒| `/cart-items/user/`               | Remove um item (corpo JSON `{look_id}`)                                   |

Pedidos e pagamento ainda **não** existem (há os modelos `orders`/`orders_items`/`address`,
sem rotas).

### Uploads
| Método  | Rota             | Descrição                                                                                   |
|---------|------------------|---------------------------------------------------------------------------------------------|
| POST 🔒 | `/uploads/image` | Corpo = bytes crus da imagem (`Content-Type: image/jpeg\|png\|webp`, máx. 5 MB). Devolve `{url}` pública para usar em `photos`, `avatar_url` ou `store_logo_url`. Valida o tipo pelos bytes; grava em `<user_id>/<uuid>.<ext>` |

### Logs de erro do app
| Método | Rota           | Descrição                                                                                      |
|--------|----------------|------------------------------------------------------------------------------------------------|
| POST   | `/logs/client` | O app envia lotes (1–20) de erros/exceções; viram uma linha JSON por entrada no log do servidor (logger `client`). Token opcional (sem token, sem id de usuário). Máx. 64 KB, 30/min; segredos e dados pessoais são removidos antes de gravar |

### Denúncias (moderação)
| Método | Rota        | Descrição                                          |
|--------|-------------|----------------------------------------------------|
| POST 🔒| `/reports`  | Denuncia um perfil, loja ou look                   |
| GET 🔒 | `/reports`  | Lista as próprias denúncias                        |

A documentação interativa (Swagger) fica em **`/docs`** com a API rodando.

---

## Regras de negócio (validadas em `schemas/`)

- Um **look** precisa pertencer a uma categoria e ter **de 1 a 6 fotos** e **no máximo 2 vídeos**
  ([`schemas/look.py`](schemas/look.py)).
- **Curtir ≠ salvar.** `RIGHT` registra uma curtida (sinal barato e frequente); salvar no armário é
  um gesto **separado e deliberato** (`POST /saved-looks`) que preserva o sinal de intenção de compra.
- **Idade**: 18+, derivada de `birth_date` — nunca guardada como número.
- **Papel vem do servidor**: `is_seller`/`seller_id` são resolvidos em `/profiles/me`; a escolha de
  tela no cliente não autoriza nada.
- Só quem tem loja cria looks; editar/remover exige gerenciar a loja (`can_manage_store`).

---

## Banco de dados

O esquema é definido em [`schema.sql`](schema.sql) e deve ser executado no **SQL Editor do
Supabase**. A API **não** cria tabelas automaticamente — o `schema.sql` é a fonte de verdade
(precisa de `auth.users`, extensão UUID e das políticas RLS).

Tabelas: `profiles`, `body_profiles`, `sellers`, `sellers_private`, `store_members`,
`categories`, `looks`, `look_likes`, `look_views` (particionada por mês), `saved_looks`,
`collections`, `collection_items`, `reports`, `user_category_affinity`, `cart`, `cart_items`
(+ `orders`/`orders_items`/`addresses`, ainda sem rotas). Dados sensíveis (medidas, documento fiscal) ficam em
tabelas próprias com RLS restrita ao dono; toda policy é escrita como se fosse o único controle,
pois a anon key é pública. `look_views` precisa de partições futuras: o banco vivo tem partições mensais **até 2026-12** mais uma partição `DEFAULT`; depois disso os registros caem na `DEFAULT` até alguém criar as próximas (idealmente um job `pg_cron` mensal).

---

## Como rodar localmente

### 1. Pré-requisitos
- Python 3.11+ (a imagem Docker usa 3.12)
- Um projeto no Supabase com o `schema.sql` aplicado

### 2. Dependências
```bash
pip install -r app/requirements.txt
```

### 3. Variáveis de ambiente
Copie [`app/.env.example`](app/.env.example) para `app/.env` e preencha:

```env
# Session Pooler do Supabase (IPv4), com a senha URL-encoded — a conexão direta
# (db.<projeto>.supabase.co) é IPv6-only e não funciona no Render.
DATABASE_URL=postgresql+asyncpg://postgres.<projeto>:<senha>@aws-0-<regiao>.pooler.supabase.com:5432/postgres
SUPABASE_URL=https://<projeto>.supabase.co
SUPABASE_JWT_SECRET=<opcional>          # só para projetos com o segredo HS256 legado
SUPABASE_SERVICE_KEY=<service-role-key> # só no servidor, nunca no app
DOCUMENT_ENCRYPTION_KEY=<base64 AES-256> # cifra o CPF/CNPJ (PUT /sellers/me/document)
SCHEMA_GUARD=1                          # opcional; 0 desliga a checagem da coluna looks.sizes na subida
STORAGE_BUCKET=lookly-media             # opcional; bucket público (leitura) das imagens enviadas
CORS_ORIGINS=http://localhost:3000,http://localhost:8081
```

> A API não sobe sem `DATABASE_URL` e sem `SUPABASE_URL` (ou `SUPABASE_JWT_SECRET`).
> `DOCUMENT_ENCRYPTION_KEY` só é exigida na hora de gravar o documento fiscal. A
> `SUPABASE_SERVICE_KEY` é necessária para o upload de imagens e para excluir a conta.
>
> Na subida a API confere se `looks.sizes` existe e, se não, cria (idempotente). Se o banco estiver
> pausado/indisponível ela sobe mesmo assim e as rotas que usam o banco respondem 500 — é o que
> acontece no Render quando o projeto do Supabase está pausado.

### 4. Subir a API
```bash
bash iniciar.sh                # http://localhost:8000  |  docs em /docs
# ou, de dentro de app/:
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
O `--host 0.0.0.0` é necessário para o emulador/aparelho alcançar a API (o emulador Android
usa `10.0.2.2`; um aparelho físico usa o IP da máquina na rede).

### 5. Testar com autenticação
Crie um usuário no Supabase Auth, obtenha o access token e use-o nas chamadas:
```bash
curl -H "Authorization: Bearer <jwt>" http://localhost:8000/api/profiles/me
```

### 6. Deploy (Render, via Docker)
O [`Dockerfile`](Dockerfile) copia o conteúdo de `app/` para `/app` e sobe
`uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}`. No Render: serviço **Docker**, raiz do
repositório, e as mesmas variáveis do `.env` configuradas no painel. No plano gratuito o serviço
dorme quando ocioso e a primeira requisição depois disso pode levar de 15 a 50 s.

---

## Roadmap (ainda não implementado)

- **Mídia**: o upload de **imagens** existe (`POST /uploads/image`). Faltam vídeos, limpeza de
  arquivos órfãos no Storage, miniaturas e URLs assinadas (foto de corpo, bucket privado).
- **Camada de comércio**: rotas de pedidos e pagamento (Mercado Pago) sobre os modelos
  `orders`/`orders_items`/`address` que já existem, estoque validado no carrinho
  (`TODO(estoque)` em `cart_items_service.py`), reviews.
- **Métricas da loja**: o app mostra dashboard/insights com dados de exemplo; falta o agregado real.
- **Mais filtros na busca**: cor, marca e estilo (hoje só preço, tamanho, estoque e ordem) — pedem
  uma decisão de modelagem (tags livres, atributos fechados ou embeddings).
- **Ranqueamento do feed**: o feed ordena só por `created_at`; usar a afinidade por categoria e
  capturar sinal (dwell time, completion) em `look_views`.
- **Provador Virtual com IA**: mesclar a foto do look com os dados de `body_profiles` (checando o
  consentimento LGPD no momento da leitura).
- **Partições de `look_views`**: job `pg_cron` mensal (as partições existentes vão até 2026-12).
- **Chat interno** para enviar look a um amigo.
- **Signed URLs** para a foto de corpo (bucket privado).
- **Exclusão de conta com pedidos**: hoje devolve 409 (pedido é registro fiscal); falta o fluxo de
  anonimização para esse caso.
- **Teste real das novas rotas** (exclusão de conta, log) contra o banco vivo, com conta descartável.
