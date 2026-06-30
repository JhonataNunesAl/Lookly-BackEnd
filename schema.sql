-- Limpeza do banco de dados (útil durante o desenvolvimento/MVP para re-rodar o script)
DROP TABLE IF EXISTS public.saved_looks CASCADE;
DROP TABLE IF EXISTS public.swipes CASCADE;
DROP TABLE IF EXISTS public.looks CASCADE;
DROP TABLE IF EXISTS public.sellers CASCADE;
DROP TABLE IF EXISTS public.categories CASCADE;
DROP TABLE IF EXISTS public.profiles CASCADE;

-- Habilitar a extensão UUID (Normalmente já habilitada no Supabase)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- 1. Tabela de Profiles (Perfis)
-- Se conecta com a tabela de autenticação interna do Supabase (auth.users)
CREATE TABLE public.profiles (
    id UUID REFERENCES auth.users(id) ON DELETE CASCADE PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT,
    avatar_url TEXT,
    full_body_photo_url TEXT,
    age INTEGER CHECK (age >= 18),
    weight_kg DECIMAL(5,2),
    height_cm INTEGER,
    body_measurements JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Perfis são visíveis para todos" ON public.profiles FOR SELECT USING (true);
CREATE POLICY "Usuários podem inserir seu próprio perfil" ON public.profiles FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "Usuários podem atualizar seu próprio perfil" ON public.profiles FOR UPDATE USING (auth.uid() = id);

-- 1.5 Tabela de Vendedores / Revendedores (Sellers)
-- Extensão do perfil para usuários que postam roupas para vender
CREATE TABLE public.sellers (
    id UUID REFERENCES public.profiles(id) ON DELETE CASCADE PRIMARY KEY,
    store_name TEXT NOT NULL,
    store_logo_url TEXT,
    description TEXT,
    store_url TEXT,
    document_number TEXT, -- CPF ou CNPJ para repasse financeiro/verificação
    rating DECIMAL(3,2) DEFAULT 0.00 CHECK (rating >= 0 AND rating <= 5), -- Avaliação de 0 a 5
    total_reviews INTEGER DEFAULT 0,
    highlights JSONB, -- Dados da aba de destaques (títulos e links das fotos)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.sellers ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Lojas são visíveis para todos" ON public.sellers FOR SELECT USING (true);
CREATE POLICY "Usuários podem virar vendedores" ON public.sellers FOR INSERT WITH CHECK (auth.uid() = id);
CREATE POLICY "Vendedores atualizam sua loja" ON public.sellers FOR UPDATE USING (auth.uid() = id);

-- 2. Tabela de Categories (Categorias de Moda)
CREATE TABLE public.categories (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Categorias são visíveis para todos" ON public.categories FOR SELECT USING (true);

-- 3. Tabela de Looks (O conteúdo do feed)
CREATE TABLE public.looks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    category_id UUID REFERENCES public.categories(id) ON DELETE CASCADE NOT NULL,
    creator_id UUID REFERENCES public.sellers(id) ON DELETE CASCADE, -- SOMENTE vendedores postam looks
    photos TEXT[] NOT NULL, -- Pela regra de negócio, limite de 6 (validado na API)
    videos TEXT[], -- Pela regra de negócio, limite de 2 (validado na API)
    description TEXT,
    buy_link TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

ALTER TABLE public.looks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Looks são visíveis para todos" ON public.looks FOR SELECT USING (true);
CREATE POLICY "Usuários logados podem criar looks" ON public.looks FOR INSERT WITH CHECK (auth.uid() = creator_id);
CREATE POLICY "Usuários podem atualizar próprios looks" ON public.looks FOR UPDATE USING (auth.uid() = creator_id);
CREATE POLICY "Usuários podem deletar próprios looks" ON public.looks FOR DELETE USING (auth.uid() = creator_id);

-- 4. Tabela de Swipes (Motor do App)
CREATE TABLE public.swipes (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    look_id UUID REFERENCES public.looks(id) ON DELETE CASCADE NOT NULL,
    direction TEXT CHECK (direction IN ('RIGHT', 'LEFT')) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_id, look_id) -- Trava: O usuário só pode dar swipe num look UMA VEZ
);

ALTER TABLE public.swipes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuários veem os próprios swipes" ON public.swipes FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Usuários criam os próprios swipes" ON public.swipes FOR INSERT WITH CHECK (auth.uid() = user_id);

-- 5. Tabela de Saved_Looks (Guarda-Roupa)
CREATE TABLE public.saved_looks (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    user_id UUID REFERENCES public.profiles(id) ON DELETE CASCADE NOT NULL,
    look_id UUID REFERENCES public.looks(id) ON DELETE CASCADE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    UNIQUE(user_id, look_id) -- Trava: O usuário só pode favoritar o mesmo look UMA VEZ
);

ALTER TABLE public.saved_looks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuários veem próprios salvamentos" ON public.saved_looks FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Usuários inserem próprios salvamentos" ON public.saved_looks FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Usuários deletam próprios salvamentos" ON public.saved_looks FOR DELETE USING (auth.uid() = user_id);
