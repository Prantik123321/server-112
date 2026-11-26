import os
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
    )

    # Application
    APP_NAME: str = "NodeShare Backend"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Security & Tokens
    # 32+ byte secret string for JWT HS256 signing
    JWT_SECRET_KEY: str = "nodeshare-development-secret-key-must-be-changed-in-production-32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Supabase PostgreSQL & Storage
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_PUBLISHABLE_KEY: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_SECRET_KEY: str = ""
    SUPABASE_POSTGRES_URL: str = ""
    SUPABASE_STORAGE_BUCKET: str = "nodeshare-files"

    @property
    def effective_anon_key(self) -> str:
        return self.SUPABASE_ANON_KEY or self.SUPABASE_PUBLISHABLE_KEY

    @property
    def effective_service_role_key(self) -> str:
        return self.SUPABASE_SERVICE_ROLE_KEY or self.SUPABASE_SECRET_KEY

    # MongoDB Atlas
    MONGODB_URI: str = ""
    MONGODB_DATABASE: str = "nodeshare_db"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 120
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 10

    # File Storage Quotas & Limits (Bytes)
    MAX_FILE_SIZE_BYTES: int = 104857600  # 100 MB
    STORAGE_QUOTA_PER_USER_BYTES: int = 1073741824  # 1 GB


# Global singleton instance
settings = Settings()
