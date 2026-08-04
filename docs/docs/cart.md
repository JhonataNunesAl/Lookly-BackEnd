# Cart e CartItems

## Visão geral

O módulo de Carrinho permite consultar o carrinho de um usuário e gerenciar os looks adicionados a ele.

Existem dois grupos de rotas:

| Grupo | Prefixo | Responsabilidade |
| --- | --- | --- |
| `Cart` | `/api/cart` | Buscar o carrinho associado a um usuário. |
| `CartItems` | `/api/cart-items` | Adicionar, listar, incrementar, diminuir e remover looks do carrinho. |

As rotas são registradas com o prefixo global `/api`.

No estado atual da API, os endpoints de `Cart` e `CartItems` não usam dependência de autenticação. Nenhum deles recebe `Authorization Bearer` via `Depends(get_current_user_id)`. Por isso, o frontend precisa enviar os IDs necessários diretamente na URL ou no body, conforme cada operação.

## Fluxo Geral

O carrinho é encontrado sempre a partir de um identificador enviado pelo frontend. Para buscar o carrinho diretamente, a API recebe `user_id` na URL e procura um registro na tabela `cart` com `Cart.user_id == user_id`. Para operar itens em endpoints de incremento e decremento, a API recebe `cart_id` no body e procura o carrinho com `Cart.id == cart_id`.

Um item é criado pelo endpoint `POST /api/cart-items/`. O frontend envia `cart_id`, `look_id` e `quantity`. Antes de criar, a API procura se já existe algum registro em `cart_items` com o mesmo `look_id`. Essa busca não filtra por `cart_id`; portanto, no comportamento atual, um mesmo `look_id` não pode aparecer em mais de um item de carrinho. Se não existir item com esse `look_id`, a API cria um novo registro usando os três campos enviados.

A quantidade é alterada por dois endpoints separados. Para incrementar, o frontend chama `PUT /api/cart-items/add/{look_id}/` com `cart_id` e `quantity` no body. A API busca o carrinho, busca o item pelo par `cart_id` e `look_id`, soma a quantidade recebida e retorna o item atualizado. Para diminuir, o frontend chama `PUT /api/cart-items/remove/{look_id}/` com `cart_id` e `quantity` no body. A API busca o carrinho, busca o item, valida se a quantidade enviada não é maior do que a quantidade atual, subtrai e retorna o item atualizado. Se a quantidade final chegar exatamente a zero, a API remove o item do banco e retorna uma mensagem com status `200`.

Um item pode ser removido diretamente pelo endpoint `DELETE /api/cart-items/`. O frontend envia `user_id` e `look_id`. A API busca o carrinho pelo usuário e tenta remover o item encontrado. Esse endpoint não possui validações explícitas para carrinho inexistente ou item inexistente.

A consulta dos itens do carrinho acontece em `GET /api/cart-items/{user_id}/`. A API busca o carrinho do usuário, depois consulta os itens daquele carrinho com carregamento do relacionamento `look` via `joinedload`. Para cada item, calcula `price_quantity_total` multiplicando `item.look.price * item.quantity`. Também monta um `price_total`, somando `item.look.price` uma vez para cada item com preço. O `price_total` é retornado pelo controller, mas não está declarado no schema `ListCartItemResponse`.

## Observações importantes sobre a implementação atual

| Ponto | Comportamento atual |
| --- | --- |
| Autenticação | Nenhum endpoint de carrinho usa autenticação por dependência. |
| Prefixo global | Todas as URLs documentadas usam `/api`, definido em `main.py`. |
| Criação de item | `quantity` é obrigatório no schema e é persistido no model. |
| Duplicidade de look | O `POST` bloqueia qualquer `look_id` já existente em `cart_items`, independentemente do carrinho. |
| Total do carrinho | `price_total` soma o preço unitário de cada look, não `price_quantity_total`. |
| Schema de listagem | `price_total` é retornado no dict do controller, mas não existe em `ListCartItemResponse`. |
| Schema de carrinho | `CartUserResponse` declara `update_at`, enquanto o model `Cart` possui `updated_at`. |
| Remoção direta | O `DELETE` não trata explicitamente carrinho ou item inexistente. |

# Endpoints

## Buscar carrinho do usuário

### Método HTTP

`GET`

### URL

```text
/api/cart/{user_id}/
```

### Objetivo

Buscar o carrinho associado a um usuário específico.

### Descrição

O endpoint recebe `user_id` como parâmetro de rota e consulta a tabela `cart`. Se encontrar um carrinho cujo `user_id` seja igual ao valor enviado, retorna esse carrinho usando o schema `CartUserResponse`. Se não encontrar, retorna `404`.

### Fluxo interno

A API recebe o `user_id` pela URL. Em seguida, executa uma consulta em `Cart`, filtrando por `Cart.user_id == user_id`. Quando a consulta retorna um registro, esse objeto é retornado diretamente. Quando a consulta não retorna nenhum registro, a API interrompe o fluxo e lança uma `HTTPException` com status `404` e detail `Cart user not found`.

### Validações

Não existe validação manual no controller para o formato de `user_id`. O parâmetro é tipado como `str`, embora o model use UUID na coluna `user_id`.

### Request Body

Este endpoint não possui body.

### Parâmetros

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `user_id` | `str` | Sim | Identificador do usuário usado na busca do carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |

### Response

Schema declarado: `CartUserResponse`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador único do carrinho. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `user_id` | `UUID` | Sim | Identificador do usuário dono do carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |
| `created_at` | `datetime` | Sim | Data e hora de criação do carrinho. | `2026-08-04T12:30:00` |
| `update_at` | `datetime` | Sim | Campo declarado no schema de resposta. No model atual, o campo existente é `updated_at`. | `2026-08-04T12:45:00` |

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `200 OK` | Quando o carrinho é encontrado. |
| `404 Not Found` | Quando não existe carrinho para o `user_id` informado. |
| `500 Internal Server Error` | Quando ocorre erro não tratado, incluindo possível incompatibilidade entre `update_at` do schema e `updated_at` do model. |

### Possíveis erros

#### `404 Not Found`

```json
{
  "detail": "Cart user not found"
}
```

Motivo: nenhum registro foi encontrado na tabela `cart` para o `user_id` informado.

#### `500 Internal Server Error`

Motivo: erro não tratado pelo controller ou falha durante serialização da resposta.

### Exemplo completo de Request

```http
GET /api/cart/4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111/
```

### Exemplo completo de Response

```json
{
  "id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "user_id": "4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111",
  "created_at": "2026-08-04T12:30:00",
  "update_at": "2026-08-04T12:45:00"
}
```

## Adicionar look ao carrinho

### Método HTTP

`POST`

### URL

```text
/api/cart-items/
```

### Objetivo

Adicionar um novo look a um carrinho.

### Descrição

O endpoint recebe `cart_id`, `look_id` e `quantity` no body. A API verifica se já existe algum item de carrinho com o mesmo `look_id`. Se existir, retorna erro `400`. Se não existir, cria um novo registro em `cart_items` usando o `cart_id`, o `look_id` e a `quantity` enviados.

### Fluxo interno

A API valida o body usando o schema `CartItemsAdd`. Depois consulta `CartItems` filtrando por `CartItems.look_id == dados.look_id`. Se encontrar qualquer item com esse `look_id`, retorna erro.

Se não encontrar, instancia `CartItems` com `cart_id = dados.cart_id`, `look_id = dados.look_id` e `quantity = dados.quantity`. Em seguida, adiciona o objeto na sessão do banco, executa `commit`, faz `refresh` no objeto criado e retorna o item.

### Validações

| Validação | Comportamento |
| --- | --- |
| Body obrigatório | `cart_id`, `look_id` e `quantity` são obrigatórios pelo schema. |
| UUID válido | `cart_id` e `look_id` precisam ser UUIDs válidos. |
| Quantidade inteira | `quantity` precisa ser inteiro. |
| Duplicidade de `look_id` | Se existir item com o mesmo `look_id`, retorna `400`. |
| Existência de carrinho | Não há validação explícita antes do `commit`. |
| Existência de look | Não há validação explícita antes do `commit`. |
| Quantidade positiva | Não há restrição declarada no schema. |

### Request Body

Schema: `CartItemsAdd`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Identificador do carrinho onde o look será adicionado. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Identificador do look que será adicionado. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade inicial que será persistida no item do carrinho. | `2` |

### Response

Schema declarado: `CartItemsResponse`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador único do item do carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `cart_id` | `UUID` | Sim | Identificador do carrinho ao qual o item pertence. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Identificador do look adicionado. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade persistida para o item. | `2` |
| `created_at` | `datetime` | Sim | Data e hora de criação do item. | `2026-08-04T12:35:00` |

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `201 Created` | Quando o item é criado com sucesso. |
| `400 Bad Request` | Quando já existe item com o mesmo `look_id`. |
| `422 Unprocessable Entity` | Quando o body não respeita o schema. |
| `500 Internal Server Error` | Quando ocorre erro não tratado, como falha de chave estrangeira. |

### Possíveis erros

#### `400 Bad Request`

```json
{
  "detail": "Look already exists in Cart of User"
}
```

Motivo: já existe um registro em `cart_items` com o mesmo `look_id`.

#### `422 Unprocessable Entity`

Motivo: o body enviado não contém todos os campos obrigatórios ou contém tipos inválidos.

#### `500 Internal Server Error`

Motivo: erro não tratado pelo controller, por exemplo se `cart_id` ou `look_id` não existirem e o banco rejeitar a inserção.

### Exemplo completo de Request

```http
POST /api/cart-items/
Content-Type: application/json
```

```json
{
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "look_id": "1b54d322-5810-4092-b8dd-72f0c1b33333",
  "quantity": 2
}
```

### Exemplo completo de Response

```json
{
  "id": "7e89581f-1c8f-4c6f-9a57-a15af8944444",
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "look_id": "1b54d322-5810-4092-b8dd-72f0c1b33333",
  "quantity": 2,
  "created_at": "2026-08-04T12:35:00"
}
```

## Listar looks do carrinho de um usuário

### Método HTTP

`GET`

### URL

```text
/api/cart-items/{user_id}/
```

### Objetivo

Retornar todos os looks que estão no carrinho de um usuário específico.

### Descrição

O endpoint recebe `user_id` na URL, busca o carrinho associado ao usuário e lista todos os itens vinculados ao `cart_id` encontrado. Cada item é retornado com os dados básicos do look relacionado.

### Fluxo interno

A API busca primeiro o carrinho com `Cart.user_id == user_id`. Se não encontrar, retorna `404` com a mensagem `Carrinho não encontrado.`.

Se o carrinho existir, consulta `CartItems` filtrando por `CartItems.cart_id == cart_user.id`. A consulta usa `joinedload(CartItems.look)`, então o relacionamento `look` é carregado junto com cada item.

Depois, a API percorre todos os itens encontrados. Para cada item, cria dinamicamente o atributo `price_quantity_total`, calculado como `item.look.price * item.quantity`. Em seguida, se `item.look.price` existir, soma esse preço unitário ao acumulador `price_total`.

Ao final, o controller retorna um dicionário com `looks` e `price_total`. Entretanto, o schema declarado `ListCartItemResponse` possui apenas `looks`. Assim, `price_total` é um campo produzido pelo controller, mas não faz parte do schema Pydantic declarado.

### Validações

| Validação | Comportamento |
| --- | --- |
| Carrinho existente | Se não existir carrinho para o `user_id`, retorna `404`. |
| Itens existentes | Se o carrinho existir e não houver itens, retorna lista vazia. |
| Relacionamento `look` | Não há validação explícita para `look` ausente. |
| Preço nulo | O cálculo de `price_quantity_total` usa `item.look.price * item.quantity` antes de verificar se o preço existe. |

### Request Body

Este endpoint não possui body.

### Parâmetros

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `user_id` | `str` | Sim | Identificador do usuário usado para localizar o carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |

### Response

Schema declarado: `ListCartItemResponse`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `looks` | `list[CartItemLookResponse]` | Sim | Lista de itens encontrados no carrinho. | `[]` |

Campos de cada item em `looks`:

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do item do carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `quantity` | `int` | Sim | Quantidade do look no carrinho. | `2` |
| `price_quantity_total` | `Decimal` | Sim | Subtotal calculado como `look.price * quantity`. | `199.80` |
| `look` | `LookResponse` | Sim | Dados do look relacionado ao item. | `{...}` |
| `created_at` | `datetime` | Sim | Data e hora de criação do item. | `2026-08-04T12:35:00` |

Campos de `look`:

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do look. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `name` | `str` | Sim | Nome do look. | `Look Casual` |
| `price` | `Decimal | None` | Sim | Preço unitário do look, podendo ser nulo. | `99.90` |
| `photos` | `list[str]` | Sim | Lista de fotos do look. | `["https://example.com/look.jpg"]` |

Campo retornado pelo controller, mas não declarado no schema:

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `price_total` | `Decimal` | Não declarado no schema | Total calculado somando `look.price` uma vez por item com preço. Não multiplica pela quantidade. | `99.90` |

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `200 OK` | Quando o carrinho existe e a resposta é montada. |
| `404 Not Found` | Quando o carrinho do usuário não é encontrado. |
| `500 Internal Server Error` | Quando ocorre erro não tratado durante consulta, cálculo ou serialização. |

### Possíveis erros

#### `404 Not Found`

```json
{
  "detail": "Carrinho não encontrado."
}
```

Motivo: a API não encontrou carrinho com `Cart.user_id == user_id`.

#### `500 Internal Server Error`

Motivo: erro não tratado, como relacionamento `look` ausente ou tentativa de multiplicar `None` por `quantity` caso `look.price` seja nulo.

### Exemplo completo de Request

```http
GET /api/cart-items/4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111/
```

### Exemplo completo de Response

```json
{
  "looks": [
    {
      "id": "7e89581f-1c8f-4c6f-9a57-a15af8944444",
      "quantity": 2,
      "price_quantity_total": "199.80",
      "look": {
        "id": "1b54d322-5810-4092-b8dd-72f0c1b33333",
        "name": "Look Casual",
        "price": "99.90",
        "photos": [
          "https://example.com/look-casual-1.jpg"
        ]
      },
      "created_at": "2026-08-04T12:35:00"
    }
  ],
  "price_total": "99.90"
}
```

## Remover look do carrinho

### Método HTTP

`DELETE`

### URL

```text
/api/cart-items/
```

### Objetivo

Excluir um look do carrinho de um usuário específico.

### Descrição

O endpoint recebe `user_id` e `look_id` no body. Primeiro busca o carrinho associado ao usuário. Depois tenta buscar o item correspondente ao look e ao carrinho encontrado. Em seguida, remove o item e confirma a transação.

O retorno configurado é `204 No Content`, portanto uma remoção bem-sucedida não retorna body.

### Fluxo interno

A API valida o body usando o schema `DeleteLookCartItemUser`. Depois busca `Cart` com `Cart.user_id == dados.user_id`. Com o carrinho encontrado, tenta buscar `CartItems` usando uma expressão com `CartItems.look_id == dados.look_id and CartItems.cart_id == cart_user.id`.

No código atual, essa busca usa o operador Python `and`, não o operador SQLAlchemy `&`. Isso é relevante porque pode afetar a construção real do filtro SQL. A documentação não assume correção diferente da implementação.

Após obter o valor de `look`, o endpoint executa `db.delete(look)` e `commit`. Não existem `HTTPException` explícitas para carrinho inexistente ou item inexistente.

### Validações

| Validação | Comportamento |
| --- | --- |
| Body obrigatório | `user_id` e `look_id` são obrigatórios pelo schema. |
| UUID válido | Ambos os campos precisam ser UUIDs válidos. |
| Carrinho existente | Não há validação explícita. |
| Item existente | Não há validação explícita. |
| Pertencimento do item ao carrinho | A intenção do filtro envolve `look_id` e `cart_id`, mas a implementação usa `and` de Python. |

### Request Body

Schema: `DeleteLookCartItemUser`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `user_id` | `UUID` | Sim | Identificador do usuário dono do carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |
| `look_id` | `UUID` | Sim | Identificador do look que deve ser removido. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |

### Response

Em sucesso, não há body.

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `204 No Content` | Quando o fluxo de remoção conclui com sucesso. |
| `422 Unprocessable Entity` | Quando o body não respeita o schema. |
| `500 Internal Server Error` | Quando ocorre erro não tratado, como carrinho inexistente ou item inexistente. |

### Possíveis erros

#### `422 Unprocessable Entity`

Motivo: `user_id` ou `look_id` ausente ou inválido.

#### `500 Internal Server Error`

Motivo: o controller tenta acessar `cart_user.id` sem validar se `cart_user` existe e tenta deletar `look` sem validar se o item foi encontrado.

### Exemplo completo de Request

```http
DELETE /api/cart-items/
Content-Type: application/json
```

```json
{
  "user_id": "4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111",
  "look_id": "1b54d322-5810-4092-b8dd-72f0c1b33333"
}
```

### Exemplo completo de Response

```http
HTTP/1.1 204 No Content
```

## Diminuir quantidade de um look

### Método HTTP

`PUT`

### URL

```text
/api/cart-items/remove/{look_id}/
```

### Objetivo

Diminuir a quantidade de um look específico no carrinho.

### Descrição

O endpoint recebe o `look_id` na URL e `cart_id` com `quantity` no body. Ele busca o carrinho pelo `cart_id`, busca o item pelo par `cart_id` e `look_id`, valida se a quantidade enviada não é maior que a quantidade atual, subtrai o valor e persiste a alteração.

Se a quantidade final ficar igual a zero, o item é removido do banco e a API retorna uma mensagem com status `200`.

### Fluxo interno

A API valida `look_id` como UUID e o body com o schema `CartItemsDelete`. Em seguida, busca `Cart` com `Cart.id == dados.cart_id`. Se não encontrar, retorna `404`.

Depois busca `CartItems` com `CartItems.cart_id == cart_user.id` e `CartItems.look_id == look_id`. Se o item não existir, retorna `404`.

Quando o item existe, compara `dados.quantity` com `look.quantity`. Se `dados.quantity` for maior, retorna `400`. Caso contrário, executa `look.quantity -= dados.quantity`.

Se `look.quantity` ficar igual a zero, remove o item com `db.delete(look)`, executa `commit` e lança `HTTPException` com status `200` e detail informando que o item foi removido. Se a quantidade final não for zero, executa `commit` e retorna o item atualizado.

### Validações

| Validação | Comportamento |
| --- | --- |
| `look_id` válido | Precisa ser UUID válido. |
| `cart_id` válido | Precisa ser UUID válido no body. |
| `quantity` inteira | Precisa ser inteiro no body. |
| Carrinho existente | Se não existir, retorna `404`. |
| Item existente | Se não existir, retorna `404`. |
| Quantidade maior que a atual | Se for maior, retorna `400`. |
| Quantidade positiva | Não há restrição declarada no schema. |

### Request Body

Schema: `CartItemsDelete`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Identificador do carrinho que contém o item. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `quantity` | `int` | Sim | Quantidade que será subtraída do item. | `1` |

### Response

Quando a quantidade final continua diferente de zero, o schema declarado é `CartItemsResponse`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do item do carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `cart_id` | `UUID` | Sim | Identificador do carrinho. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Identificador do look. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade após a subtração. | `1` |
| `created_at` | `datetime` | Sim | Data e hora de criação do item. | `2026-08-04T12:35:00` |

Quando a quantidade final fica igual a zero, o item é removido e a resposta é:

```json
{
  "detail": "The quantity of the item look is equal to zero. We removed it from the cart."
}
```

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `200 OK` | Quando a quantidade é diminuída ou quando o item é removido por chegar a zero. |
| `400 Bad Request` | Quando a quantidade enviada é maior que a quantidade atual. |
| `404 Not Found` | Quando o carrinho ou o item não são encontrados. |
| `422 Unprocessable Entity` | Quando path param ou body não respeitam os tipos esperados. |
| `500 Internal Server Error` | Quando ocorre erro não tratado. |

### Possíveis erros

#### `400 Bad Request`

```json
{
  "detail": "The quantity sent for removal cannot be greater than the current quantity."
}
```

Motivo: a API impede que a subtração deixe a quantidade negativa.

#### `404 Not Found`

```json
{
  "detail": "Cart User not found"
}
```

Motivo: não existe carrinho com o `cart_id` informado.

#### `404 Not Found`

```json
{
  "detail": "Look not found in Cart of user"
}
```

Motivo: não existe item para o par `cart_id` e `look_id`.

#### `422 Unprocessable Entity`

Motivo: `look_id`, `cart_id` ou `quantity` inválidos ou ausentes.

### Exemplo completo de Request

```http
PUT /api/cart-items/remove/1b54d322-5810-4092-b8dd-72f0c1b33333/
Content-Type: application/json
```

```json
{
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "quantity": 1
}
```

### Exemplo completo de Response

```json
{
  "id": "7e89581f-1c8f-4c6f-9a57-a15af8944444",
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "look_id": "1b54d322-5810-4092-b8dd-72f0c1b33333",
  "quantity": 1,
  "created_at": "2026-08-04T12:35:00"
}
```

## Incrementar quantidade de um look

### Método HTTP

`PUT`

### URL

```text
/api/cart-items/add/{look_id}/
```

### Objetivo

Aumentar a quantidade de um look específico no carrinho.

### Descrição

O endpoint recebe `look_id` na URL e `cart_id` com `quantity` no body. Ele busca o carrinho pelo `cart_id`, busca o item pelo par `cart_id` e `look_id`, soma a quantidade enviada à quantidade atual, persiste e retorna o item atualizado.

### Fluxo interno

A API valida `look_id` como UUID e o body com `CartItemsAddQuantity`. Depois busca `Cart` com `Cart.id == dados.cart_id`. Em seguida, usa `cart_user.id` para buscar `CartItems` com o mesmo `cart_id` e o `look_id` da URL.

Quando o item é encontrado, executa `look.quantity += dados.quantity`, faz `commit`, executa `refresh` e retorna o item atualizado.

O endpoint não possui validações explícitas para carrinho inexistente, item inexistente ou quantidade positiva.

### Validações

| Validação | Comportamento |
| --- | --- |
| `look_id` válido | Precisa ser UUID válido. |
| `cart_id` válido | Precisa ser UUID válido no body. |
| `quantity` inteira | Precisa ser inteiro no body. |
| Carrinho existente | Não há validação explícita. |
| Item existente | Não há validação explícita. |
| Quantidade positiva | Não há restrição declarada no schema. |

### Request Body

Schema: `CartItemsAddQuantity`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Identificador do carrinho onde o item será incrementado. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `quantity` | `int` | Sim | Quantidade que será somada à quantidade atual do item. | `1` |

### Response

Schema declarado: `CartItemsResponse`.

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do item do carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `cart_id` | `UUID` | Sim | Identificador do carrinho. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Identificador do look. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade após o incremento. | `3` |
| `created_at` | `datetime` | Sim | Data e hora de criação do item. | `2026-08-04T12:35:00` |

### Status HTTP possíveis

| Status | Quando acontece |
| --- | --- |
| `200 OK` | Quando o item é encontrado, atualizado e retornado. |
| `422 Unprocessable Entity` | Quando path param ou body não respeitam os tipos esperados. |
| `500 Internal Server Error` | Quando ocorre erro não tratado, como carrinho ou item inexistente. |

### Possíveis erros

#### `422 Unprocessable Entity`

Motivo: `look_id`, `cart_id` ou `quantity` inválidos ou ausentes.

#### `500 Internal Server Error`

Motivo: o controller acessa `cart_user.id` e `look.quantity` sem validar se esses objetos existem.

### Exemplo completo de Request

```http
PUT /api/cart-items/add/1b54d322-5810-4092-b8dd-72f0c1b33333/
Content-Type: application/json
```

```json
{
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "quantity": 1
}
```

### Exemplo completo de Response

```json
{
  "id": "7e89581f-1c8f-4c6f-9a57-a15af8944444",
  "cart_id": "0f59fa5d-22c6-4db5-9317-7e12f3a22222",
  "look_id": "1b54d322-5810-4092-b8dd-72f0c1b33333",
  "quantity": 3,
  "created_at": "2026-08-04T12:35:00"
}
```

# Fluxos detalhados

## Adicionar Look

1. O frontend obtém ou já possui o `cart_id` do usuário.
2. O frontend envia `POST /api/cart-items/` com `cart_id`, `look_id` e `quantity`.
3. A API valida o body com `CartItemsAdd`.
4. A API procura em `cart_items` se já existe um item com o mesmo `look_id`.
5. Se encontrar, retorna `400` com `Look already exists in Cart of User`.
6. Se não encontrar, cria `CartItems` com os valores enviados.
7. A API executa `commit`, faz `refresh` e retorna o item criado com `201 Created`.

## Incrementar quantidade

1. O frontend envia `PUT /api/cart-items/add/{look_id}/`.
2. O `look_id` vai na URL.
3. O `cart_id` e a `quantity` a incrementar vão no body.
4. A API busca o carrinho por `Cart.id == dados.cart_id`.
5. A API busca o item por `cart_id` e `look_id`.
6. A API soma `dados.quantity` em `look.quantity`.
7. A API persiste com `commit`, recarrega com `refresh` e retorna `CartItemsResponse`.

No comportamento atual, se o carrinho ou o item não forem encontrados, o endpoint tende a gerar erro interno, pois não há validação explícita para esses casos.

## Diminuir quantidade

1. O frontend envia `PUT /api/cart-items/remove/{look_id}/`.
2. O `look_id` vai na URL.
3. O `cart_id` e a `quantity` a subtrair vão no body.
4. A API busca o carrinho por `Cart.id == dados.cart_id`.
5. Se o carrinho não existir, retorna `404`.
6. A API busca o item pelo par `cart_id` e `look_id`.
7. Se o item não existir, retorna `404`.
8. A API compara a quantidade enviada com a quantidade atual.
9. Se a quantidade enviada for maior, retorna `400`.
10. Se a quantidade enviada for válida, subtrai de `look.quantity`.
11. Se a quantidade final for zero, remove o item e retorna `200` com mensagem.
12. Se a quantidade final não for zero, retorna o item atualizado.

## Remover item

1. O frontend envia `DELETE /api/cart-items/` com `user_id` e `look_id`.
2. A API valida o body com `DeleteLookCartItemUser`.
3. A API busca o carrinho com `Cart.user_id == dados.user_id`.
4. A API tenta buscar o item pelo look e pelo carrinho encontrado.
5. A API chama `delete` para o item retornado e executa `commit`.
6. Em sucesso, retorna `204 No Content`.

As validações explícitas desse endpoint são apenas as do schema. Não há `404` manual para carrinho inexistente nem para item inexistente.

## Buscar carrinho

Para obter os dados básicos do carrinho, o frontend chama `GET /api/cart/{user_id}/`. A API busca `Cart.user_id == user_id` e retorna o carrinho encontrado ou `404`.

Para obter os itens do carrinho, o frontend chama `GET /api/cart-items/{user_id}/`. A API busca primeiro o carrinho pelo usuário. Com o `cart_id` encontrado, consulta `cart_items` e carrega o relacionamento `look` via `joinedload`.

A resposta é construída percorrendo os itens encontrados. Cada item recebe `price_quantity_total`, calculado como `look.price * quantity`. O controller também calcula `price_total`, mas soma apenas o preço unitário de cada look com preço definido. O schema declarado para esse endpoint contém `looks`; `price_total` é retornado pelo controller, mas não está no schema.

# Orientação para o Frontend

## Qual endpoint chamar primeiro

O primeiro endpoint recomendado é:

```http
GET /api/cart/{user_id}/
```

Ele permite obter o `cart_id`, que é necessário para adicionar, incrementar e diminuir itens.

Para renderizar a tela do carrinho, use:

```http
GET /api/cart-items/{user_id}/
```

Esse endpoint retorna a lista de looks do carrinho e os dados básicos de cada look.

## IDs que precisam ser armazenados

O frontend deve armazenar ou manter disponíveis:

| ID | Uso |
| --- | --- |
| `user_id` | Buscar carrinho, listar itens e remover item diretamente. |
| `cart_id` | Adicionar item, incrementar quantidade e diminuir quantidade. |
| `look_id` | Identificar qual look será adicionado, incrementado, decrementado ou removido. |
| `cart_item.id` | Identificar localmente o item retornado pela API, se a interface precisar controlar a linha do carrinho. |

## Dados enviados em cada operação

| Operação | Endpoint | Dados necessários |
| --- | --- | --- |
| Buscar carrinho | `GET /api/cart/{user_id}/` | `user_id` na URL. |
| Listar itens | `GET /api/cart-items/{user_id}/` | `user_id` na URL. |
| Adicionar look | `POST /api/cart-items/` | `cart_id`, `look_id`, `quantity` no body. |
| Incrementar quantidade | `PUT /api/cart-items/add/{look_id}/` | `look_id` na URL; `cart_id`, `quantity` no body. |
| Diminuir quantidade | `PUT /api/cart-items/remove/{look_id}/` | `look_id` na URL; `cart_id`, `quantity` no body. |
| Remover item | `DELETE /api/cart-items/` | `user_id`, `look_id` no body. |

## Quando atualizar a interface

Após `POST /api/cart-items/`, a interface pode adicionar o item retornado ao estado local. Como o endpoint agora persiste a `quantity` enviada, a quantidade retornada deve refletir a quantidade criada.

Após `PUT /api/cart-items/add/{look_id}/`, atualize a quantidade local usando o `quantity` retornado.

Após `PUT /api/cart-items/remove/{look_id}/`, verifique o formato da resposta. Se a resposta contiver os campos do item, atualize a quantidade local. Se a resposta contiver `detail` com a mensagem de remoção por quantidade zero, remova o item da interface.

Após `DELETE /api/cart-items/`, remova o item da interface somente se receber `204 No Content`.

Para manter totais e subtotais sincronizados com o backend, recarregue o carrinho com `GET /api/cart-items/{user_id}/` depois de operações que alteram itens.

## Como interpretar as respostas

| Resposta | Interpretação |
| --- | --- |
| `201 Created` em `POST /api/cart-items/` | O item foi criado com a quantidade enviada. |
| `200 OK` em incremento | A quantidade foi somada e o item atualizado foi retornado. |
| `200 OK` em decremento com item | A quantidade foi subtraída e o item atualizado foi retornado. |
| `200 OK` em decremento com `detail` | A quantidade chegou a zero e o item foi removido. |
| `204 No Content` em remoção direta | O fluxo de remoção concluiu sem body. |
| `400 Bad Request` | Regra de negócio bloqueou a operação. |
| `404 Not Found` | Um recurso não foi encontrado em endpoints que tratam esse caso explicitamente. |
| `422 Unprocessable Entity` | Algum campo obrigatório faltou ou foi enviado com tipo inválido. |
| `500 Internal Server Error` | Erro inesperado ou caso não tratado pelo controller. |

## Boas práticas para integração

Sempre use os valores retornados pela API como fonte final após uma operação. Para telas com total, subtotal ou lista de itens, prefira recarregar `GET /api/cart-items/{user_id}/` depois de adicionar, incrementar, diminuir ou remover.

Antes de chamar endpoints de item, garanta que o frontend possui `cart_id`. O `cart_id` não é inferido pela API nos endpoints de criação, incremento e decremento.

Trate `400` como erro de regra de negócio e exiba uma mensagem adequada ao usuário. Trate `404` como recurso inexistente e considere recarregar os dados. Trate `422` como erro de payload enviado pelo frontend. Trate `500` como falha inesperada e evite atualizar a interface como se a operação tivesse sido concluída.

Ao calcular totais no frontend, observe que o backend calcula `price_quantity_total` por item como preço vezes quantidade, mas o `price_total` montado no controller soma apenas o preço unitário de cada look. Se a UI precisar de total considerando quantidade, use os subtotais por item retornados em `price_quantity_total`.

# Schemas Pydantic envolvidos

## `CartUserResponse`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do carrinho. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `user_id` | `UUID` | Sim | Identificador do usuário dono do carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |
| `created_at` | `datetime` | Sim | Data de criação do carrinho. | `2026-08-04T12:30:00` |
| `update_at` | `datetime` | Sim | Campo declarado no schema; o model usa `updated_at`. | `2026-08-04T12:45:00` |

## `CartItemsAdd`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Carrinho onde o look será adicionado. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Look que será adicionado. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade inicial que será persistida no item. | `2` |

## `CartItemsAddQuantity`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Carrinho onde o item será incrementado. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `quantity` | `int` | Sim | Quantidade que será somada ao item. | `1` |

## `CartItemsDelete`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `cart_id` | `UUID` | Sim | Carrinho onde o item será decrementado. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `quantity` | `int` | Sim | Quantidade que será subtraída do item. | `1` |

## `CartItemsResponse`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do item no carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `cart_id` | `UUID` | Sim | Identificador do carrinho. | `0f59fa5d-22c6-4db5-9317-7e12f3a22222` |
| `look_id` | `UUID` | Sim | Identificador do look. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `quantity` | `int` | Sim | Quantidade persistida no item. | `2` |
| `created_at` | `datetime` | Sim | Data de criação do item. | `2026-08-04T12:35:00` |

## `LookResponse`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do look. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
| `name` | `str` | Sim | Nome do look. | `Look Casual` |
| `price` | `Decimal | None` | Sim | Preço unitário do look, podendo ser nulo. | `99.90` |
| `photos` | `list[str]` | Sim | Lista de fotos do look. | `["https://example.com/look.jpg"]` |

## `CartItemLookResponse`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | Sim | Identificador do item no carrinho. | `7e89581f-1c8f-4c6f-9a57-a15af8944444` |
| `quantity` | `int` | Sim | Quantidade do look no carrinho. | `2` |
| `price_quantity_total` | `Decimal` | Sim | Subtotal do item calculado como `look.price * quantity`. | `199.80` |
| `look` | `LookResponse` | Sim | Dados do look relacionado. | `{...}` |
| `created_at` | `datetime` | Sim | Data de criação do item. | `2026-08-04T12:35:00` |

## `ListCartItemResponse`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `looks` | `list[CartItemLookResponse]` | Sim | Lista de itens do carrinho com dados dos looks. | `[]` |

## `DeleteLookCartItemUser`

| Campo | Tipo | Obrigatório | Descrição | Exemplo |
| --- | --- | --- | --- | --- |
| `user_id` | `UUID` | Sim | Usuário dono do carrinho. | `4d3f4c8d-9a63-4b43-8e0f-7e9f7f0a1111` |
| `look_id` | `UUID` | Sim | Look que será removido do carrinho. | `1b54d322-5810-4092-b8dd-72f0c1b33333` |
