from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .api.v1.api import router as api_router
from .core.config import settings
from .core.database import engine, Base
from .utils.logging import setup_logging

# Импортируем модели, чтобы SQLAlchemy знал о них при создании таблиц
from .models import models  # noqa: F401

setup_logging(settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown события приложения.
    При старте: создаём таблицы если их нет (fallback если init.sql не отработал).
    Порядок важен: сначала независимые таблицы, потом зависимые.
    """
    async with engine.begin() as conn:
        # Убеждаемся, что TimescaleDB расширение существует
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        except Exception:
            pass  # расширение уже есть или нет прав — init.sql уже создал

        # Создаём все таблицы через SQLAlchemy ORM (idempotent, учитывает новые модели)
        # Порядок создания определяется ForeignKey-зависимостями автоматически
        await conn.run_sync(Base.metadata.create_all)

        # Fallback: гипертаблица sensor_data (SQLAlchemy не знает о TimescaleDB-специфике)
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS sensor_data (
                    time TIMESTAMPTZ NOT NULL,
                    sensor_id INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
                    value DOUBLE PRECISION NOT NULL
                )
            """))
            await conn.execute(text(
                "SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_time "
                "ON sensor_data (sensor_id, time DESC)"
            ))
        except Exception:
            pass  # таблица уже существует

        # Fallback: таблица predictions
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id SERIAL PRIMARY KEY,
                    sensor_id INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
                    prediction_time TIMESTAMPTZ NOT NULL,
                    value DOUBLE PRECISION NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_predictions_sensor_time "
                "ON predictions (sensor_id, prediction_time DESC)"
            ))
        except Exception:
            pass  # таблица уже существует

        # Fallback: индексы для новых таблиц (enterprises, devices)
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_uea_user "
                "ON user_enterprise_access (user_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_uea_enterprise "
                "ON user_enterprise_access (enterprise_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_devices_enterprise "
                "ON devices (enterprise_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_sensors_device "
                "ON sensors (device_id)"
            ))
        except Exception:
            pass  # индексы уже существуют

    yield
    # Shutdown: закрываем соединения
    await engine.dispose()


app = FastAPI(
    title="IoT Platform API",
    version="1.0.0",
    description="Backend for IoT data collection and predictive analytics",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене заменить на конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "IoT Platform API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "ok"}
