"""
ATLAS CERTIFICATION HEADER
name=config.py
Version: 3.3.0
Change Log:
- Added BROKER_TRADING_ENABLED setting to centralised configuration (default False).
- This makes trading opt-in via settings or environment variable and supports validation at startup.

Production Certification: Phase 3.3
"""

# config.py
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str
    API_VERSION: str
    LOG_LEVEL: str = "INFO"
    AUTH_TOKEN: str
    REQUEST_TIMEOUT: int = 30

    # MT5 specific
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None
    MT5_TERMINAL_PATH: Optional[str] = None
    MT5_TIMEOUT: int = 30000
    MT5_CONNECTION_TIMEOUT: int = 30000
    MT5_RETRY_BASE_DELAY: float = 1.0
    MT5_RETRY_MAX_DELAY: float = 60.0
    MT5_MAX_RETRIES: int = 10

    # Operational flags
    BROKER_TRADING_ENABLED: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @field_validator("ENVIRONMENT")
    def validate_env(cls, v):
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be one of development, staging, production")
        return v

    @field_validator("AUTH_TOKEN")
    @classmethod
    def validate_auth_token(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("AUTH_TOKEN must not be empty")
        return value

settings = Settings()
