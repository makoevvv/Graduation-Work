from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    LOG_LEVEL: str = "INFO"

    # URL микросервиса предиктивной аналитики
    BLACKBOX_URL: str = "http://blackbox:8001"

    # Авто-переобучение ML-модели
    # Переобучать модель каждые N новых точек данных (0 = отключено)
    AUTO_RETRAIN_EVERY_N_POINTS: int = 20
    # Минимальное количество точек для первого обучения
    AUTO_RETRAIN_MIN_POINTS: int = 10

    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()