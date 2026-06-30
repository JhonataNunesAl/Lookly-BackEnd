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
│   ├── profile.py  seller.py  category.py
│   ├── look.py  swipe.py  saved_look.py  collection.py
├── schemas/                # modelos Pydantic (entrada/saída + validações)
│   ├── profile.py  seller.py  category.py
│   ├── look.py  swipe.py  collection.py
├── controller/             # rotas por domínio
│   ├── profile_controller.py  seller_controller.py
│   ├── category_controller.py  look_controller.py
│   ├── feed_controller.py  swipe_controller.py
│   └── wardrobe_controller.py
└── service/                # lógica de negócio por domínio
    ├── profile_service.py  seller_service.py
    ├── category_service.py  look_service.py
    ├── feed_service.py  swipe_service.py
    └── wardrobe_service.py
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
| Método | Rota                  | Descrição                                 |
|--------|-----------------------|-------------------------------------------|
| GET 🔒 | `/profiles/me`        | Retorna o perfil do usuário logado        |
| PUT 🔒 | `/profiles/me`        | Atualiza nome, foto, medidas, estilos…    |

### Vendedores (lojas/marcas que postam looks)
| Método | Rota             | Descrição                          |
|--------|------------------|------------------------------------|
| POST 🔒| `/sellers`       | Torna o usuário um vendedor        |
| GET 🔒 | `/sellers/me`    | Dados da própria loja              |
| PUT 🔒 | `/sellers/me`    | Atualiza a loja                    |

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
| Método | Rota                                       | Descrição                                                              |
|--------|--------------------------------------------|------------------------------------------------------------------------|
| GET 🔒 | `/feed?category=<slug>&limit=&cursor=`     | Looks da categoria que o usuário **ainda não** deu swipe (paginado)    |

### Swipe
| Método | Rota       | Descrição                                                                 |
|--------|------------|---------------------------------------------------------------------------|
| POST 🔒| `/swipes`  | Registra swipe. `RIGHT` curte e salva no armário; `LEFT` descarta         |

### Armário e coleções
| Método  | Rota                                                | Descrição                          |
|---------|-----------------------------------------------------|------------------------------------|
| GET 🔒  | `/saved-looks`                                      | Looks curtidos/salvos              |
| DELETE🔒| `/saved-looks/{look_id}`                            | Remove do armário                  |
| GET 🔒  | `/collections`                                      | Lista coleções (pastas)            |
| POST 🔒 | `/collections`                                      | Cria coleção                       |
| GET 🔒  | `/collections/{id}/looks`                           | Looks de uma coleção               |
| POST 🔒 | `/collections/{id}/looks`                           | Adiciona look à coleção            |
| DELETE🔒| `/collections/{id}/looks/{look_id}`                 | Remove look da coleção             |

A documentação interativa (Swagger) fica em **`/docs`** com a API rodando.

---

## Regras de negócio (validadas em `schemas/`)

- Um **look** precisa pertencer a uma categoria e ter **de 1 a 6 fotos** e **no máximo 2 vídeos**
  ([`schemas/look.py`](schemas/look.py)).
- **Swipe**: `direction` é o enum `RIGHT`/`LEFT` ([`schemas/swipe.py`](schemas/swipe.py)).
  `RIGHT` = curtir/salvar. Há trava de unicidade: um usuário só dá swipe uma vez por look.
- Só **vendedores** criam looks; um look só é editado/removido pelo seu criador.

---

## Banco de dados

O esquema é definido em [`schema.sql`](schema.sql) e deve ser executado no **SQL Editor do
Supabase**. A API **não** cria tabelas automaticamente — o `schema.sql` é a fonte de verdade
(precisa de `auth.users`, extensão UUID e das políticas RLS).

Tabelas principais: `profiles`, `sellers`, `categories`, `looks`, `swipes`, `saved_looks`
(as coleções usam `collections` e `collection_items`).

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

- **Provador Virtual com IA**: mesclar a foto do look com `full_body_photo_url` + `body_measurements`.
- **Recomendação/ML**: calibrar o feed pelos estilos preferidos do usuário.
- **Chat interno** para enviar look a um amigo.
- **Moderação de conteúdo** (denúncias) e **exclusão de conta** (LGPD).
- **Storage/CDN** para fotos e vídeos.
