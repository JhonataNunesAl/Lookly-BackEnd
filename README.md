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
├── main.py                 # ponto de entrada (FastAPI app)
├── routers.py              # registra os controllers
├── schema.sql              # esquema do banco (rodar no Supabase) — fonte de verdade
├── requirements.txt
│
├── core/
│   ├── config.py           # settings carregadas do .env
│   ├── security.py         # verify_supabase_token (valida o JWT)
│   └── rate_limiter.py     # instância do SlowAPI
├── db/
│   └── database.py         # engine async + get_db() (AsyncSession)
├── dependencies/
│   └── auth.py             # get_current_user_id (dependência de auth)
├── model/                  # tabelas SQLAlchemy
│   ├── base.py
│   ├── profile.py  body_profile.py  seller.py  category.py
│   ├── look.py  signal.py (look_likes/look_views)  saved_look.py
│   ├── collection.py  report.py
├── schemas/                # modelos Pydantic (entrada/saída + validações)
│   ├── profile.py  body_profile.py  seller.py  category.py
│   ├── look.py  swipe.py  collection.py  report.py
├── controller/             # rotas por domínio
│   ├── profile_controller.py  body_profile_controller.py
│   ├── seller_controller.py  category_controller.py  look_controller.py
│   ├── feed_controller.py  swipe_controller.py
│   ├── wardrobe_controller.py  report_controller.py
└── service/                # lógica de negócio por domínio
    ├── profile_service.py  body_profile_service.py  seller_service.py
    ├── category_service.py  look_service.py  feed_service.py
    ├── swipe_service.py  wardrobe_service.py  report_service.py
```

---

## Autenticação

A API **não** faz cadastro/login nem guarda senhas — isso é responsabilidade do **Supabase Auth**.

1. O app autentica o usuário no Supabase (e-mail/senha, Google, Apple, Facebook).
2. O Supabase devolve um **access token (JWT)**.
3. O app chama esta API com o header `Authorization: Bearer <jwt>`.
4. [`dependencies/auth.py`](dependencies/auth.py) → `get_current_user_id` valida o token
   (assinatura HS256 com o `SUPABASE_JWT_SECRET`, expiração e audience `authenticated`) e
   retorna o `id` do usuário (igual a `profiles.id`).

Requisições sem token, ou com token inválido/expirado, recebem **401**.

---

## Endpoints

Todos sob o prefixo `/api`. 🔒 = exige token.

### Perfil
| Método | Rota                  | Descrição                                                        |
|--------|-----------------------|------------------------------------------------------------------|
| GET 🔒 | `/profiles/me`        | Perfil do usuário + papel real (`is_seller`, `seller_id`)        |
| PUT 🔒 | `/profiles/me`        | Atualiza username, nome, foto, bio, `birth_date` (18+)           |

### Dados corporais (sensíveis — só o dono)
| Método  | Rota                      | Descrição                                                    |
|---------|---------------------------|--------------------------------------------------------------|
| GET 🔒  | `/body-profile/me`        | Medidas (ciphertext) e chave da foto de corpo                |
| PUT 🔒  | `/body-profile/me`        | Grava medidas (já cifradas) e `body_photo_key`               |
| POST 🔒 | `/body-profile/me/consent`| Concede consentimento de IA (LGPD, versionado)               |
| DELETE🔒| `/body-profile/me/consent`| Revoga o consentimento                                       |

### Vendedores (lojas/marcas que postam looks)
| Método | Rota                    | Descrição                                          |
|--------|-------------------------|----------------------------------------------------|
| POST 🔒| `/sellers`              | Cria a loja do usuário (`owner_profile_id`)        |
| GET 🔒 | `/sellers/me`           | Dados da própria loja                              |
| PUT 🔒 | `/sellers/me`           | Atualiza a loja                                    |
| PUT 🔒 | `/sellers/me/document`  | Documento fiscal (ciphertext + hash) em `sellers_private` |

### Categorias
| Método | Rota           | Descrição                       |
|--------|----------------|---------------------------------|
| GET    | `/categories`  | Lista categorias (público)      |
| POST 🔒| `/categories`  | Cria categoria                  |

### Looks
| Método | Rota                  | Descrição                                            |
|--------|-----------------------|------------------------------------------------------|
| POST 🔒| `/looks`              | Cria look (só vendedores; valida fotos/vídeos)       |
| GET    | `/looks/{id}`         | Detalhe do look                                      |
| PUT 🔒 | `/looks/{id}`         | Atualiza (só o dono)                                 |
| DELETE🔒| `/looks/{id}`        | Remove (só o dono)                                   |
| GET    | `/looks/{id}/share`   | Payload de compartilhamento (link/WhatsApp)          |

### Feed (funcionalidade central)
| Método | Rota                                       | Descrição                                                                     |
|--------|--------------------------------------------|-------------------------------------------------------------------------------|
| GET 🔒 | `/feed?category=<slug>&limit=&cursor=`     | Looks ativos que o usuário **ainda não** viu (paginado). `category` é **opcional** |

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
`collections`, `collection_items`, `reports`. Dados sensíveis (medidas, documento fiscal) ficam em
tabelas próprias com RLS restrita ao dono; toda policy é escrita como se fosse o único controle,
pois a anon key é pública. `look_views` precisa de partições futuras (via `pg_cron`).

---

## Como rodar localmente

### 1. Pré-requisitos
- Python 3.11+
- Um projeto no Supabase com o `schema.sql` aplicado

### 2. Dependências
```bash
pip install -r requirements.txt
```

### 3. Variáveis de ambiente
Copie [`.env.example`](.env.example) para `.env` e preencha:

```env
DATABASE_URL=postgresql+asyncpg://postgres:<senha>@db.<projeto>.supabase.co:5432/postgres
SUPABASE_URL=https://<projeto>.supabase.co
SUPABASE_JWT_SECRET=<jwt-secret>        # Project Settings > API > JWT Settings
SUPABASE_SERVICE_KEY=<service-role-key>
CORS_ORIGINS=http://localhost:3000,http://localhost:8081
```

> ⚠️ `SUPABASE_JWT_SECRET` é o **segredo de assinatura do JWT**, não a service key (`sb_secret_...`).
> A API não sobe sem `DATABASE_URL` e `SUPABASE_JWT_SECRET`.

### 4. Subir a API
```bash
uvicorn main:app --reload      # http://localhost:8000  |  docs em /docs
```

### 5. Testar com autenticação
Crie um usuário no Supabase Auth, obtenha o access token e use-o nas chamadas:
```bash
curl -H "Authorization: Bearer <jwt>" http://localhost:8000/api/profiles/me
```

---

## Roadmap (ainda não implementado)

- **Provador Virtual com IA**: mesclar a foto do look com os dados de `body_profiles` (checando o
  consentimento LGPD no momento da leitura).
- **Cifragem real** dos campos `*_enc` (envelope encryption com KMS) — hoje a API só persiste o
  ciphertext que o cliente envia.
- **Camada de comércio**: pedidos, pagamentos (Mercado Pago), variantes com estoque, reviews.
- **Ranqueamento do feed**: capturar sinal (dwell time, completion) em `look_views` e ranquear.
- **Chat interno** para enviar look a um amigo.
- **Exclusão de conta** (LGPD) com limpeza explícita de `look_views` (sem FK).
- **Storage/CDN** e signed URLs para a foto de corpo (bucket privado).
