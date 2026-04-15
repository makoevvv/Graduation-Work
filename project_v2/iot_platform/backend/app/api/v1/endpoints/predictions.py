from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List
import httpx

from ....core.database import get_db
from ....core.config import settings
from ....api.deps import get_current_active_user
from ....models.models import User, Sensor
from ....schemas.schemas import PredictionOut

router = APIRouter()


@router.get("/", response_model=List[PredictionOut])
async def get_predictions(
    sensor_id: int = Query(..., description="ID датчика"),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает сохранённые прогнозы для датчика из БД."""
    # Проверяем доступ к датчику
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    query = text("""
        SELECT sensor_id, prediction_time, value, created_at
        FROM predictions
        WHERE sensor_id = :sensor_id
        ORDER BY prediction_time ASC
        LIMIT :limit
    """)
    result = await db.execute(query, {"sensor_id": sensor_id, "limit": limit})
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.post("/train")
async def train_model(
    sensor_id: int = Query(..., description="ID датчика для обучения"),
    forecast_steps: int = Query(10, le=50, description="Количество шагов прогноза"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Запускает обучение ML-модели в BlackBox-сервисе для указанного датчика.
    После обучения прогнозы автоматически сохраняются в БД.
    """
    # Проверяем доступ к датчику
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    # Вызываем BlackBox
    blackbox_url = settings.BLACKBOX_URL
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{blackbox_url}/train",
                params={
                    "sensor_id": sensor_id,
                    "forecast_steps": forecast_steps,
                    "save_to_db": True,
                }
            )
            if response.status_code == 422:
                detail = response.json().get("detail", "Недостаточно данных для обучения")
                raise HTTPException(status_code=422, detail=detail)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"BlackBox вернул ошибку: {response.text}"
                )
            return response.json()

    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="BlackBox сервис недоступен. Убедитесь, что он запущен."
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="BlackBox не ответил вовремя (timeout 60s)"
        )


@router.get("/status")
async def get_model_status(
    sensor_id: int = Query(..., description="ID датчика"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Возвращает статус ML-модели для датчика из BlackBox."""
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    blackbox_url = settings.BLACKBOX_URL
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{blackbox_url}/status",
                params={"sensor_id": sensor_id}
            )
            return response.json()
    except Exception:
        return {"sensor_id": sensor_id, "is_trained": False, "blackbox_available": False}


@router.get("/anomalies")
async def get_anomalies(
    sensor_id: int = Query(..., description="ID датчика"),
    limit: int = Query(100, le=1000),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Запрашивает детекцию аномалий в последних данных датчика через BlackBox."""
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    blackbox_url = settings.BLACKBOX_URL
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{blackbox_url}/anomalies",
                params={"sensor_id": sensor_id, "limit": limit}
            )
            if response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Модель не обучена. Сначала запустите /predictions/train"
                )
            return response.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="BlackBox сервис недоступен")
