import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")

    # Supabase
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    # Segredo de assinatura do JWT do Supabase (HS256).
    # ATENÇÃO: não é a service key (sb_secret_...). Pegue em
    # Project Settings > API > JWT Settings > JWT Secret no painel do Supabase.
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET")
    # Service role key, usada apenas em operações administrativas server-side.
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY")

    # O Supabase assina os access tokens com aud="authenticated".
    JWT_ALGORITHM: str = "HS256"
    JWT_AUDIENCE: str = "authenticated"

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the environment variables.")

    if not SUPABASE_JWT_SECRET:
        raise ValueError("SUPABASE_JWT_SECRET is not set in the environment variables.")


settings = Settings()
