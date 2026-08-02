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
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    HOST: str = Field("0.0.0.0", env="HOST")
    PORT: int = Field(8000, env="PORT")
    ENVIRONMENT: str = Field(..., env="ENVIRONMENT")
    API_VERSION: str = Field(..., env="API_VERSION")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    AUTH_TOKEN: str = Field(..., env="AUTH_TOKEN")
    REQUEST_TIMEOUT: int = Field(30, env="REQUEST_TIMEOUT")

    # MT5 specific
    MT5_LOGIN: Optional[int] = Field(None, env="MT5_LOGIN")
    MT5_PASSWORD: Optional[str] = Field(None, env="MT5_PASSWORD")
    MT5_SERVER: Optional[str] = Field(None, env="MT5_SERVER")
    MT5_TERMINAL_PATH: Optional[str] = Field(None, env="MT5_TERMINAL_PATH")
    MT5_TIMEOUT: int = Field(30000, env="MT5_TIMEOUT")

    # Operational flags
    BROKER_TRADING_ENABLED: bool = Field(False, env="BROKER_TRADING_ENABLED")

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("ENVIRONMENT")
    def validate_env(cls, v):
        if v not in ("development", "staging", "production"):
            raise ValueError("ENVIRONMENT must be one of development, staging, production")
        return v

settings = Settings()
