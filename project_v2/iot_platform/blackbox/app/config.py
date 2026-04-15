from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: str = "5432"

    FORECAST_STEPS: int = 10          # сколько точек вперёд прогнозировать
    MIN_TRAIN_POINTS: int = 20        # минимум точек для обучения
    ANOMALY_CONTAMINATION: float = 0.05  # ожидаемая доля аномалий (5%)
    TRAIN_WINDOW_POINTS: int = 50     # скользящее окно: обучать только на последних N точках
                                      # (0 = без ограничения, брать все данные)
                                      # 50 точек = быстрая адаптация к новому паттерну

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
