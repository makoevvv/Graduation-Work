"""
BlackBox — микросервис предиктивной аналитики IoT-платформы.

Endpoints:
  POST /train?sensor_id=X          — обучить модели на исторических данных датчика
  GET  /predict?sensor_id=X&steps=N — получить прогноз (без переобучения)
  GET  /anomalies?sensor_id=X      — детектировать аномалии в последних данных
  GET  /status?sensor_id=X         — статус обученной модели
  GET  /health                     — проверка работоспособности сервиса
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, timezone
import numpy as np
from loguru import logger

from .config import settings
from .database import get_db
from .ml_engine import model_manager
from .schemas import (
    TrainResponse,
    PredictResponse,
    AnomalyResponse,
    StatusResponse,
    ForecastPoint,
)

app = FastAPI(
    title="IoT BlackBox — Predictive Analytics",
    version="1.0.0",
    description=(
        "Микросервис предиктивной аналитики. "
        "Реализует прогнозирование временных рядов (Linear Regression) "
        "и детекцию аномалий (Isolation Forest) для IoT-датчиков."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────

async def fetch_sensor_data(
    sensor_id: int,
    db: AsyncSession,
    limit: int = 500,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Загружает последние `limit` точек датчика из БД (скользящее окно).
    Берёт DESC (последние), затем разворачивает в ASC для корректного обучения.
    Это гарантирует, что старые данные не «портят» модель при длительной работе.
    """
    query = text("""
        SELECT time, value
        FROM sensor_data
        WHERE sensor_id = :sensor_id
        ORDER BY time DESC
        LIMIT :limit
    """)
    result = await db.execute(query, {"sensor_id": sensor_id, "limit": limit})
    rows = result.mappings().all()

    if not rows:
        return np.array([]), np.array([])

    # Разворачиваем: данные пришли DESC, нужен ASC для обучения
    rows = list(reversed(rows))

    # Возвращаем timestamps как список datetime объектов Python (не numpy)
    timestamps = np.array([row["time"] for row in rows], dtype=object)
    values = np.array([float(row["value"]) for row in rows])
    return values, timestamps


async def save_predictions_to_db(
    sensor_id: int,
    forecast: List[dict],
    db: AsyncSession,
) -> None:
    """Сохраняет прогнозы в таблицу predictions."""
    # Удаляем старые прогнозы для этого датчика
    await db.execute(
        text("DELETE FROM predictions WHERE sensor_id = :sensor_id"),
        {"sensor_id": sensor_id},
    )

    # Вставляем новые — парсим prediction_time из ISO строки в datetime
    for point in forecast:
        pt = point["prediction_time"]
        if isinstance(pt, str):
            # Убираем 'Z' суффикс если есть, заменяем на +00:00
            pt = pt.replace("Z", "+00:00")
            try:
                pt = datetime.fromisoformat(pt)
            except Exception:
                pt = datetime.now(timezone.utc)
        await db.execute(
            text("""
                INSERT INTO predictions (sensor_id, prediction_time, value)
                VALUES (:sensor_id, :prediction_time, :value)
            """),
            {
                "sensor_id": sensor_id,
                "prediction_time": pt,
                "value": point["value"],
            },
        )
    await db.commit()
    logger.info(f"Сохранено {len(forecast)} прогнозов для sensor_id={sensor_id}")


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "blackbox"}


@app.post("/train", response_model=TrainResponse)
async def train(
    sensor_id: int = Query(..., description="ID датчика для обучения"),
    limit: int = Query(
        0, ge=0, le=5000,
        description=(
            "Размер скользящего окна обучения (последние N точек). "
            "0 = использовать TRAIN_WINDOW_POINTS из настроек. "
            "Позволяет избежать влияния устаревших данных на прогноз."
        )
    ),
    forecast_steps: int = Query(
        settings.FORECAST_STEPS, le=50, description="Количество шагов прогноза"
    ),
    save_to_db: bool = Query(True, description="Сохранить прогнозы в БД"),
    db: AsyncSession = Depends(get_db),
):
    """
    Обучает ML-модели (Linear Regression + Isolation Forest) на **последних** N точках
    датчика (скользящее окно). Это предотвращает деградацию прогнозов при длительной
    работе системы, когда старые данные не отражают текущий паттерн (concept drift).

    Параметр `limit` задаёт размер окна. По умолчанию используется TRAIN_WINDOW_POINTS
    из конфигурации (200 точек). Если TRAIN_WINDOW_POINTS=0 — берутся все данные.
    """
    # Определяем размер скользящего окна
    window = limit if limit > 0 else settings.TRAIN_WINDOW_POINTS
    # Если window=0 — берём все данные (без ограничения, но ставим разумный потолок)
    effective_limit = window if window > 0 else 10000

    logger.info(
        f"Обучение sensor_id={sensor_id}: скользящее окно={effective_limit} точек"
    )

    # Загружаем последние effective_limit точек
    values, timestamps = await fetch_sensor_data(sensor_id, db, limit=effective_limit)

    if len(values) < settings.MIN_TRAIN_POINTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Недостаточно данных для обучения: {len(values)} точек. "
                f"Минимум: {settings.MIN_TRAIN_POINTS}. "
                f"Запустите симулятор для генерации данных."
            ),
        )

    # Обучаем модели
    try:
        result = model_manager.train(
            sensor_id=sensor_id,
            values=values,
            timestamps=timestamps,
            contamination=settings.ANOMALY_CONTAMINATION,
            forecast_steps=forecast_steps,
        )
    except Exception as e:
        logger.error(f"Ошибка обучения для sensor_id={sensor_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка обучения модели: {str(e)}")

    # Сохраняем прогнозы в БД
    if save_to_db and result["forecast"]:
        try:
            await save_predictions_to_db(sensor_id, result["forecast"], db)
        except Exception as e:
            logger.warning(f"Не удалось сохранить прогнозы в БД: {e}")

    return TrainResponse(
        sensor_id=sensor_id,
        trained_at=result["trained_at"],
        train_points=result["train_points"],
        forecast=[ForecastPoint(**p) for p in result["forecast"]],
        anomaly_count=result["anomalies"]["count"],
        anomaly_indices=result["anomalies"]["indices"],
        model_info=result["model_info"],
    )


@app.get("/predict", response_model=PredictResponse)
async def predict(
    sensor_id: int = Query(..., description="ID датчика"),
    steps: int = Query(settings.FORECAST_STEPS, le=50, description="Количество шагов прогноза"),
):
    """
    Возвращает прогноз для уже обученной модели (без переобучения).
    Если модель не обучена — вернёт 404.
    """
    forecast = model_manager.get_forecast(sensor_id, steps)
    if forecast is None:
        raise HTTPException(
            status_code=404,
            detail=f"Модель для sensor_id={sensor_id} не найдена. Сначала вызовите /train.",
        )

    return PredictResponse(
        sensor_id=sensor_id,
        steps=steps,
        forecast=[ForecastPoint(**p) for p in forecast],
    )


@app.get("/anomalies", response_model=AnomalyResponse)
async def detect_anomalies(
    sensor_id: int = Query(..., description="ID датчика"),
    limit: int = Query(100, le=1000, description="Количество последних точек для анализа"),
    db: AsyncSession = Depends(get_db),
):
    """
    Детектирует аномалии в последних данных датчика.
    Требует предварительного обучения через /train.
    """
    values, timestamps = await fetch_sensor_data(sensor_id, db, limit=limit)

    if len(values) == 0:
        raise HTTPException(status_code=404, detail="Нет данных для датчика")

    result = model_manager.detect_anomalies(sensor_id, values)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Модель для sensor_id={sensor_id} не найдена. Сначала вызовите /train.",
        )

    # Формируем список аномальных точек с временными метками
    anomaly_points = []
    for idx in result["anomaly_mask"]:
        pass  # будет заполнено ниже

    anomaly_details = []
    mask = result["anomaly_mask"]
    for i, (is_anomaly, score) in enumerate(zip(mask, result["scores"])):
        if is_anomaly:
            ts = timestamps[i]
            ts_str = str(ts) if not hasattr(ts, "isoformat") else ts.isoformat()
            anomaly_details.append({
                "index": i,
                "time": ts_str,
                "value": float(values[i]),
                "score": float(score),
            })

    return AnomalyResponse(
        sensor_id=sensor_id,
        analyzed_points=len(values),
        anomaly_count=result["count"],
        anomalies=anomaly_details,
    )


@app.get("/status", response_model=StatusResponse)
async def get_status(
    sensor_id: int = Query(..., description="ID датчика"),
):
    """Возвращает статус обученной модели для датчика."""
    status = model_manager.get_status(sensor_id)
    return StatusResponse(**status)
