-- =============================================================
-- LOOKLY — schema.sql
-- Postgres / Supabase
--
-- Consolida os dois arquivos anteriores. Fases 1 (segurança) e
-- 2 (fundação do CRUD) aplicadas. A camada de comércio — pedidos,
-- pagamentos, variantes com estoque, reviews — NÃO está aqui:
-- depende de decisões ainda em aberto (frete, split de repasse,
-- peça única vs. reposição, política de cancelamento).
--
-- PREMISSA DE SEGURANÇA
-- A anon key vai embutida no APK publicado e é extraível dele.
-- Com ela e a URL do projeto, qualquer cliente alcança o PostgREST
-- direto, sem passar pelo FastAPI. Toda policy abaixo é escrita
-- como se fosse o único controle existente — porque é.
--
-- ORDEM DE EXECUÇÃO
-- Rodar inteiro, de uma vez, no SQL editor do Supabase.
-- =============================================================

-- -------------------------------------------------------------
-- 0. Limpeza (apenas dev/MVP — apaga dados)
-- -------------------------------------------------------------
DROP TABLE IF EXISTS public.reports         CASCADE;
DROP TABLE IF EXISTS public.saved_looks     CASCADE;
DROP TABLE IF EXISTS public.look_views      CASCADE;
DROP TABLE IF EXISTS public.look_likes      CASCADE;
DROP TABLE IF EXISTS public.swipes          CASCADE;  -- substituída pelo par acima
DROP TABLE IF EXISTS public.collection_items CASCADE;
DROP TABLE IF EXISTS public.collections     CASCADE;
DROP TABLE IF EXISTS public.looks           CASCADE;
DROP TABLE IF EXISTS public.categories      CASCADE;
DROP TABLE IF EXISTS public.store_members   CASCADE;
DROP TABLE IF EXISTS public.sellers_private CASCADE;
DROP TABLE IF EXISTS public.sellers         CASCADE;
DROP TABLE IF EXISTS public.body_profiles   CASCADE;
DROP TABLE IF EXISTS public.profiles        CASCADE;

DROP TYPE IF EXISTS public.content_status  CASCADE;
DROP TYPE IF EXISTS public.account_status  CASCADE;
DROP TYPE IF EXISTS public.swipe_direction CASCADE;
DROP TYPE IF EXISTS public.report_target   CASCADE;
DROP TYPE IF EXISTS public.report_status   CASCADE;
DROP TYPE IF EXISTS public.store_role      CASCADE;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================
-- 1. TIPOS
--
-- ENUM em vez de TEXT + CHECK: valor inválido é rejeitado em
-- qualquer caminho de escrita, não só no que a API usa hoje.
-- =============================================================
CREATE TYPE public.content_status  AS ENUM ('draft', 'active', 'under_review', 'removed');
CREATE TYPE public.account_status  AS ENUM ('active', 'suspended', 'banned', 'deleted');
CREATE TYPE public.swipe_direction AS ENUM ('RIGHT', 'LEFT');
CREATE TYPE public.report_target   AS ENUM ('profile', 'seller', 'look');
CREATE TYPE public.report_status   AS ENUM ('open', 'reviewing', 'resolved', 'rejected');
CREATE TYPE public.store_role      AS ENUM ('owner', 'manager', 'staff');

-- =============================================================
-- 2. FUNÇÕES UTILITÁRIAS
-- =============================================================
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- =============================================================
-- 3. PROFILES — só dado público
--
-- FASE 1: peso, altura, medidas e foto de corpo SAÍRAM daqui.
-- A policy antiga `USING (true)` expunha tudo isso para qualquer
-- portador da anon key. RLS filtra LINHA, não COLUNA — separar a
-- tabela era a única forma de esconder aqueles campos.
--
-- FASE 2: `age INTEGER` virou `birth_date`. Idade guardada como
-- número não envelhece: quem entrou com 18 fica 18 para sempre.
-- =============================================================
CREATE TABLE public.profiles (
    id          UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username    TEXT NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.]{3,30}$'),
    full_name   TEXT,
    avatar_url  TEXT,
    bio         TEXT CHECK (char_length(bio) <= 300),
    birth_date  DATE NOT NULL CHECK (birth_date <= (CURRENT_DATE - INTERVAL '18 years')),
    status      public.account_status NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_profiles_username ON public.profiles (username);
CREATE INDEX idx_profiles_status   ON public.profiles (status) WHERE status <> 'active';

CREATE TRIGGER trg_profiles_updated
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "profiles_select" ON public.profiles
    FOR SELECT TO anon, authenticated
    USING (status = 'active' OR id = (SELECT auth.uid()));

CREATE POLICY "profiles_insert_own" ON public.profiles
    FOR INSERT TO authenticated
    WITH CHECK (id = (SELECT auth.uid()));

CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE TO authenticated
    USING (id = (SELECT auth.uid()))
    WITH CHECK (id = (SELECT auth.uid()));

-- Privilégio de coluna.
-- Um REVOKE de coluna NÃO subtrai de um GRANT de tabela: é preciso
-- revogar o UPDATE inteiro e reconceder só as colunas permitidas.
-- Sem isso, o usuário se auto-desbane trocando `status`.
REVOKE UPDATE ON public.profiles FROM anon, authenticated;
GRANT  UPDATE (username, full_name, avatar_url, bio, birth_date)
    ON public.profiles TO authenticated;

-- Cria o profile no signup, em vez de depender de o cliente lembrar.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, username, full_name, birth_date)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'username', 'user_' || left(NEW.id::text, 8)),
        NEW.raw_user_meta_data->>'full_name',
        COALESCE((NEW.raw_user_meta_data->>'birth_date')::date,
                 CURRENT_DATE - INTERVAL '18 years')
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- =============================================================
-- 4. BODY_PROFILES — dado corporal
--
-- FASE 1. Regras:
--   * RLS só para o dono; `anon` não tem policy nenhuma aqui
--   * foto guardada como CHAVE de bucket PRIVADO, servida por
--     signed URL de curta duração — nunca URL pública
--   * consentimento de IA explícito, versionado e revogável (LGPD)
--
-- Cifrar na aplicação (envelope encryption com KMS) e gravar o
-- ciphertext aqui, para a chave não morar no mesmo banco.
-- =============================================================
CREATE TABLE public.body_profiles (
    profile_id            UUID PRIMARY KEY REFERENCES public.profiles(id) ON DELETE CASCADE,
    weight_kg_enc         TEXT,
    height_cm_enc         TEXT,
    measurements_enc      TEXT,
    body_photo_key        TEXT,
    ai_consent_at         TIMESTAMPTZ,
    ai_consent_revoked_at TIMESTAMPTZ,
    consent_version       TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_consent_order
        CHECK (ai_consent_revoked_at IS NULL OR ai_consent_revoked_at >= ai_consent_at)
);

CREATE TRIGGER trg_body_profiles_updated
    BEFORE UPDATE ON public.body_profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.body_profiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.body_profiles FROM anon;

CREATE POLICY "body_own" ON public.body_profiles
    FOR ALL TO authenticated
    USING (profile_id = (SELECT auth.uid()))
    WITH CHECK (profile_id = (SELECT auth.uid()));

-- =============================================================
-- 5. SELLERS — dado público da loja
--
-- FASE 1: `document_number` saiu daqui (ver sellers_private).
-- Estava sob USING(true): o CPF de todo vendedor era legível.
--
-- FASE 2: `owner_profile_id` separado do `id`. Antes a loja ERA o
-- usuário; separando, a loja ganha equipe e o dono pode transferir
-- a titularidade sem recriar o registro.
-- =============================================================
CREATE TABLE public.sellers (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_profile_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE RESTRICT,
    store_name       TEXT NOT NULL CHECK (char_length(store_name) BETWEEN 2 AND 80),
    store_slug       TEXT NOT NULL UNIQUE CHECK (store_slug ~ '^[a-z0-9-]{3,50}$'),
    store_logo_url   TEXT,
    description      TEXT,
    store_url        TEXT,
    rating           NUMERIC(3,2) NOT NULL DEFAULT 0.00 CHECK (rating BETWEEN 0 AND 5),
    total_reviews    INTEGER NOT NULL DEFAULT 0 CHECK (total_reviews >= 0),
    highlights       JSONB NOT NULL DEFAULT '[]'::jsonb,
    status           public.content_status NOT NULL DEFAULT 'active',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sellers_owner ON public.sellers (owner_profile_id);
CREATE INDEX idx_sellers_slug  ON public.sellers (store_slug);

CREATE TRIGGER trg_sellers_updated
    BEFORE UPDATE ON public.sellers
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.sellers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sellers_select" ON public.sellers
    FOR SELECT TO anon, authenticated
    USING (status = 'active' OR owner_profile_id = (SELECT auth.uid()));

CREATE POLICY "sellers_insert_own" ON public.sellers
    FOR INSERT TO authenticated
    WITH CHECK (owner_profile_id = (SELECT auth.uid()));

CREATE POLICY "sellers_update_own" ON public.sellers
    FOR UPDATE TO authenticated
    USING (owner_profile_id = (SELECT auth.uid()))
    WITH CHECK (owner_profile_id = (SELECT auth.uid()));

-- `rating`, `total_reviews` e `status` são cache/moderação:
-- a loja não edita a própria nota nem se tira da análise.
REVOKE UPDATE ON public.sellers FROM anon, authenticated;
GRANT  UPDATE (store_name, store_slug, store_logo_url, description, store_url, highlights)
    ON public.sellers TO authenticated;

-- =============================================================
-- 6. SELLERS_PRIVATE — documento fiscal
--
-- FASE 1. Ciphertext + hash. O hash responde "esse CNPJ já está
-- cadastrado?" sem nunca ler o valor em claro.
-- =============================================================
CREATE TABLE public.sellers_private (
    seller_id          UUID PRIMARY KEY REFERENCES public.sellers(id) ON DELETE CASCADE,
    document_enc       TEXT NOT NULL,
    document_hash      TEXT NOT NULL UNIQUE,
    document_type      TEXT NOT NULL CHECK (document_type IN ('CPF', 'CNPJ')),
    verified_at        TIMESTAMPTZ,
    payout_provider_id TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_sellers_private_updated
    BEFORE UPDATE ON public.sellers_private
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.sellers_private ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sellers_private FROM anon;

CREATE POLICY "seller_private_own" ON public.sellers_private
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.sellers s
        WHERE s.id = seller_id AND s.owner_profile_id = (SELECT auth.uid())
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.sellers s
        WHERE s.id = seller_id AND s.owner_profile_id = (SELECT auth.uid())
    ));

-- =============================================================
-- 7. STORE_MEMBERS — equipe da loja
--
-- Substitui a ideia de "senha da loja" do diagrama original.
-- Login continua sendo um só; acesso à loja é um papel.
-- =============================================================
CREATE TABLE public.store_members (
    seller_id  UUID NOT NULL REFERENCES public.sellers(id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    role       public.store_role NOT NULL DEFAULT 'staff',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (seller_id, profile_id)
);

CREATE INDEX idx_store_members_profile ON public.store_members (profile_id);

-- SECURITY DEFINER evita recursão: a policy de store_members não
-- pode consultar store_members através da própria RLS.
CREATE OR REPLACE FUNCTION public.can_manage_store(p_seller_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER SET search_path = public
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.sellers s
        WHERE s.id = p_seller_id AND s.owner_profile_id = auth.uid()
    ) OR EXISTS (
        SELECT 1 FROM public.store_members m
        WHERE m.seller_id = p_seller_id
          AND m.profile_id = auth.uid()
          AND m.role IN ('owner', 'manager')
    );
$$;

ALTER TABLE public.store_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.store_members FROM anon;

CREATE POLICY "store_members_read" ON public.store_members
    FOR SELECT TO authenticated
    USING (profile_id = (SELECT auth.uid()) OR public.can_manage_store(seller_id));

CREATE POLICY "store_members_manage" ON public.store_members
    FOR ALL TO authenticated
    USING (public.can_manage_store(seller_id))
    WITH CHECK (public.can_manage_store(seller_id));

-- =============================================================
-- 8. CATEGORIES
-- =============================================================
CREATE TABLE public.categories (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name       TEXT NOT NULL,
    slug       TEXT NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9-]+$'),
    image_url  TEXT,
    is_active  BOOLEAN NOT NULL DEFAULT true,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY "categories_select" ON public.categories
    FOR SELECT TO anon, authenticated USING (is_active);

-- Escrita só via service_role (painel admin). Ausência de policy
-- de INSERT/UPDATE já basta, mas o REVOKE deixa explícito.
REVOKE INSERT, UPDATE, DELETE ON public.categories FROM anon, authenticated;

-- =============================================================
-- 9. LOOKS — o conteúdo do feed E o produto
--
-- Post e look são a mesma entidade: quem publica é a loja e o
-- conteúdo É o catálogo. `post_looks` com coordenadas X,Y do
-- diagrama original foi descartado — servia para criador marcando
-- produto de terceiro, que não é o modelo do Lookly.
--
-- FASE 2:
--   * `creator_id` nullable -> `seller_id NOT NULL` (produto órfão)
--   * categoria CASCADE -> RESTRICT (apagar categoria apagava tudo)
--   * limites de mídia viraram CHECK, não só validação no Pydantic
-- =============================================================
CREATE TABLE public.looks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seller_id   UUID NOT NULL REFERENCES public.sellers(id) ON DELETE CASCADE,
    category_id UUID NOT NULL REFERENCES public.categories(id) ON DELETE RESTRICT,
    name        TEXT NOT NULL CHECK (char_length(name) BETWEEN 2 AND 120),
    description TEXT,
    photos      TEXT[] NOT NULL CHECK (array_length(photos, 1) BETWEEN 1 AND 6),
    videos      TEXT[] NOT NULL DEFAULT '{}'
                CHECK (COALESCE(array_length(videos, 1), 0) <= 2),
    price       NUMERIC(10,2) CHECK (price IS NULL OR price >= 0),
    buy_link    TEXT,
    likes_count INTEGER NOT NULL DEFAULT 0 CHECK (likes_count >= 0),
    saves_count INTEGER NOT NULL DEFAULT 0 CHECK (saves_count >= 0),
    status      public.content_status NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FASE 2: o schema anterior não tinha índice nenhum.
CREATE INDEX idx_looks_seller   ON public.looks (seller_id);
CREATE INDEX idx_looks_category ON public.looks (category_id, created_at DESC)
    WHERE status = 'active';
CREATE INDEX idx_looks_feed     ON public.looks (created_at DESC)
    WHERE status = 'active';

CREATE TRIGGER trg_looks_updated
    BEFORE UPDATE ON public.looks
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.looks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "looks_select" ON public.looks
    FOR SELECT TO anon, authenticated
    USING (status = 'active' OR public.can_manage_store(seller_id));

CREATE POLICY "looks_write_store" ON public.looks
    FOR ALL TO authenticated
    USING (public.can_manage_store(seller_id))
    WITH CHECK (public.can_manage_store(seller_id));

REVOKE UPDATE ON public.looks FROM anon, authenticated;
GRANT  UPDATE (name, description, photos, videos, price, buy_link, category_id)
    ON public.looks TO authenticated;

-- =============================================================
-- 10. SINAL — LOOK_LIKES e LOOK_VIEWS
--
-- FASE 2. A tabela `swipes` foi dividida em duas porque os dois
-- dados têm ciclo de vida oposto:
--
--   look_likes  — só RIGHT. Volume baixo, valor permanente.
--   look_views  — todo swipe. Volume enorme, valor efêmero.
--
-- look_views é particionada por mês. Retenção é DROP da partição
-- antiga: instantâneo. Um DELETE de milhões de linhas deixaria a
-- tabela inchada e o autovacuum sofrendo.
--
-- Nem Tinder nem TikTok resolvem o "já vi isso" com NOT IN contra
-- uma tabela dessas. Quando o feed pesar, o dedupe migra para um
-- set em Redis e nada aqui precisa mudar.
-- =============================================================
CREATE TABLE public.look_likes (
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    look_id    UUID NOT NULL REFERENCES public.looks(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, look_id)
);

CREATE INDEX idx_look_likes_look   ON public.look_likes (look_id);
CREATE INDEX idx_look_likes_recent ON public.look_likes (user_id, created_at DESC);

ALTER TABLE public.look_likes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.look_likes FROM anon;

CREATE POLICY "likes_own" ON public.look_likes
    FOR ALL TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

-- Particionamento exige a chave de partição na PK.
CREATE TABLE public.look_views (
    user_id    UUID NOT NULL,
    look_id    UUID NOT NULL,
    direction  public.swipe_direction NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, look_id, created_at)
) PARTITION BY RANGE (created_at);

-- Sem FK: em tabela particionada de alto volume o custo de escrita
-- não compensa, e o dado é descartável. Consequência: apagar um
-- usuário NÃO limpa aqui — a rotina de exclusão LGPD precisa
-- fazer isso explicitamente.

CREATE TABLE public.look_views_2026_07 PARTITION OF public.look_views
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
CREATE TABLE public.look_views_2026_08 PARTITION OF public.look_views
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
CREATE TABLE public.look_views_2026_09 PARTITION OF public.look_views
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
-- Criar as próximas via pg_cron. Retenção sugerida: 6 meses.
-- Escrita SEM partição correspondente FALHA. Manter o job vivo.

ALTER TABLE public.look_views ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.look_views FROM anon;

CREATE POLICY "views_own" ON public.look_views
    FOR ALL TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

-- Registrar um swipe: uma chamada, as duas tabelas.
CREATE OR REPLACE FUNCTION public.record_swipe(
    p_look_id   UUID,
    p_direction public.swipe_direction
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
    v_user     UUID := auth.uid();
    v_inserted INTEGER;
BEGIN
    IF v_user IS NULL THEN
        RAISE EXCEPTION 'não autenticado';
    END IF;

    INSERT INTO public.look_views (user_id, look_id, direction)
    VALUES (v_user, p_look_id, p_direction)
    ON CONFLICT DO NOTHING;

    IF p_direction = 'RIGHT' THEN
        INSERT INTO public.look_likes (user_id, look_id)
        VALUES (v_user, p_look_id)
        ON CONFLICT DO NOTHING;

        GET DIAGNOSTICS v_inserted = ROW_COUNT;
        IF v_inserted > 0 THEN
            UPDATE public.looks
               SET likes_count = likes_count + 1
             WHERE id = p_look_id;
        END IF;
    END IF;
END;
$$;

-- NOTA DE ESCALA: esse UPDATE serializa na linha do look. Em
-- conteúdo viral vira gargalo. Nesse ponto: remover o UPDATE daqui
-- e recalcular likes_count por job a partir de look_likes.

-- NOTA DE PRODUTO: `record_swipe` deliberadamente NÃO salva no
-- guarda-roupa. Antes, RIGHT curtia e salvava no mesmo gesto, o
-- que fazia de saved_looks uma cópia dos likes e apagava o sinal
-- de intenção de compra — justamente o que interessa às lojas.
-- Curtir é barato e frequente; salvar é raro e significa intenção.

-- =============================================================
-- 11. SAVED_LOOKS — guarda-roupa (gesto deliberado)
-- =============================================================
CREATE TABLE public.saved_looks (
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    look_id    UUID NOT NULL REFERENCES public.looks(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, look_id)
);

CREATE INDEX idx_saved_looks_recent ON public.saved_looks (user_id, created_at DESC);
CREATE INDEX idx_saved_looks_look   ON public.saved_looks (look_id);

ALTER TABLE public.saved_looks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.saved_looks FROM anon;

CREATE POLICY "saved_own" ON public.saved_looks
    FOR ALL TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE OR REPLACE FUNCTION public.sync_save_count()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE public.looks SET saves_count = saves_count + 1 WHERE id = NEW.look_id;
    ELSE
        UPDATE public.looks SET saves_count = GREATEST(saves_count - 1, 0) WHERE id = OLD.look_id;
    END IF;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_saved_count
    AFTER INSERT OR DELETE ON public.saved_looks
    FOR EACH ROW EXECUTE FUNCTION public.sync_save_count();

-- =============================================================
-- 12. COLLECTIONS — pastas dentro do guarda-roupa
-- =============================================================
CREATE TABLE public.collections (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id    UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    name       TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 60),
    cover_url  TEXT,
    is_public  BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE INDEX idx_collections_user ON public.collections (user_id);

CREATE TRIGGER trg_collections_updated
    BEFORE UPDATE ON public.collections
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.collections ENABLE ROW LEVEL SECURITY;

CREATE POLICY "collections_select" ON public.collections
    FOR SELECT TO anon, authenticated
    USING (is_public OR user_id = (SELECT auth.uid()));

CREATE POLICY "collections_write_own" ON public.collections
    FOR ALL TO authenticated
    USING (user_id = (SELECT auth.uid()))
    WITH CHECK (user_id = (SELECT auth.uid()));

CREATE TABLE public.collection_items (
    collection_id UUID NOT NULL REFERENCES public.collections(id) ON DELETE CASCADE,
    look_id       UUID NOT NULL REFERENCES public.looks(id) ON DELETE CASCADE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, look_id)
);

ALTER TABLE public.collection_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "collection_items_select" ON public.collection_items
    FOR SELECT TO anon, authenticated
    USING (EXISTS (
        SELECT 1 FROM public.collections c
        WHERE c.id = collection_id
          AND (c.is_public OR c.user_id = (SELECT auth.uid()))
    ));

CREATE POLICY "collection_items_write" ON public.collection_items
    FOR ALL TO authenticated
    USING (EXISTS (
        SELECT 1 FROM public.collections c
        WHERE c.id = collection_id AND c.user_id = (SELECT auth.uid())
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM public.collections c
        WHERE c.id = collection_id AND c.user_id = (SELECT auth.uid())
    ));

-- =============================================================
-- 13. REPORTS — denúncia e moderação
--
-- FASE 2. Faltava por completo. Sem isso, tirar conteúdo do ar
-- só apagando — e perdendo a prova junto.
-- =============================================================
CREATE TABLE public.reports (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    reporter_id   UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    target_type   public.report_target NOT NULL,
    target_id     UUID NOT NULL,
    reason        TEXT NOT NULL,
    description   TEXT,
    contact_email TEXT,
    status        public.report_status NOT NULL DEFAULT 'open',
    resolved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (reporter_id, target_type, target_id)
);

CREATE INDEX idx_reports_target ON public.reports (target_type, target_id);
CREATE INDEX idx_reports_open   ON public.reports (created_at) WHERE status = 'open';

ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.reports FROM anon;

CREATE POLICY "reports_insert_own" ON public.reports
    FOR INSERT TO authenticated
    WITH CHECK (reporter_id = (SELECT auth.uid()));

CREATE POLICY "reports_select_own" ON public.reports
    FOR SELECT TO authenticated
    USING (reporter_id = (SELECT auth.uid()));

-- Leitura e gestão pela moderação: service_role apenas.
REVOKE UPDATE, DELETE ON public.reports FROM authenticated;

-- =============================================================
-- 14. HIGIENE DE PRIVILÉGIOS
--
-- Postgres concede EXECUTE em função para PUBLIC por padrão.
-- Função SECURITY DEFINER precisa ser fechada explicitamente,
-- ou vira um caminho para contornar a RLS.
-- =============================================================
REVOKE EXECUTE ON FUNCTION public.handle_new_user()  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.sync_save_count()  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.can_manage_store(UUID) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.can_manage_store(UUID) TO authenticated;
REVOKE EXECUTE ON FUNCTION public.record_swipe(UUID, public.swipe_direction)
    FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.record_swipe(UUID, public.swipe_direction)
    TO authenticated;

-- =============================================================
-- 15. VERIFICAÇÃO — rodar depois de aplicar
-- =============================================================

-- Nenhuma tabela em `public` pode ficar sem RLS.
-- Resultado esperado: zero linhas.
--
-- SELECT tablename
--   FROM pg_tables
--  WHERE schemaname = 'public'
--    AND rowsecurity = false;

-- Nenhuma policy pode ser permissiva demais.
-- Procurar por `true` sozinho na coluna qual.
--
-- SELECT tablename, policyname, roles, cmd, qual
--   FROM pg_policies
--  WHERE schemaname = 'public'
--  ORDER BY tablename;

-- Teste real: com a ANON KEY (não a service key), bater no
-- PostgREST e confirmar que cada uma destas responde vazia ou 401.
--
--   GET /rest/v1/body_profiles?select=*
--   GET /rest/v1/sellers_private?select=*
--   GET /rest/v1/look_likes?select=*
--   GET /rest/v1/reports?select=*
--
-- Se qualquer uma devolver linhas, a fase 1 não está concluída.