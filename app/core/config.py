import os 
from dotenv import load_dotenv

load_dotenv()

class Settings: 
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    ALGORITHM: str = "HS256"
    
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in the environment variables.")
    
settings = Settings()