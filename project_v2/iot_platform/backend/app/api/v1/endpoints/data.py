from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from datetime import datetime
from typing import List, Optional
import logging
import httpx
from collections import defaultdict

from ....core.database import get_db
from ....core.config import settings
from ....api.deps import get_current_active_user
from ....models.models import User, Sensor
from ....schemas.schemas import SensorDataIn, SensorDataOut

router = APIRouter()
logger = logging.getLogger(__name__)

# ─── Счётчик новых точек с момента последнего обучения ───────────────────────
# Ключ: sensor_id → количество новых точек после последнего обучения
_new_points_counter: dict[int, int] = defaultdict(int)
# Флаг: идёт ли сейчас переобучение для датчика (защита от параллельных запусков)
_retraining_in_progress: dict[int, bool] = defaultdict(bool)


def _sync_retrain(sensor_id: int) -> None:
    """
    Синхронная фоновая задача переобучения (запускается в threadpool FastAPI BackgroundTasks).
    Использует синхронный httpx.Client — нет конфликта с event loop.
    """
    if _retraining_in_progress[sensor_id]:
        print(f"[AutoRetrain] Sensor {sensor_id}: переобучение уже идёт, пропускаем")
        return

    _retraining_in_progress[sensor_id] = True
    try:
        print(f"[AutoRetrain] Sensor {sensor_id}: запуск авто-переобучения ML-модели...")
        logger.info(f"Sensor {sensor_id}: запуск авто-переобучения ML-модели...")

        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                f"{settings.BLACKBOX_URL}/train",
                params={
                    "sensor_id": sensor_id,
                    "forecast_steps": 10,
                    "save_to_db": True,
                },
            )

        if response.status_code == 200:
            result = response.json()
            pts = result.get("train_points", result.get("data_points", "?"))
            msg = f"Sensor {sensor_id}: авто-переобучение завершено ({pts} точек, прогнозы обновлены)"
            print(f"[AutoRetrain] {msg}")
            logger.info(msg)
            # Сбрасываем счётчик только при успехе
            _new_points_counter[sensor_id] = 0
        elif response.status_code == 422:
            detail = response.json().get("detail", "недостаточно данных")
            print(f"[AutoRetrain] Sensor {sensor_id}: пропущено — {detail}")
            logger.warning(f"Sensor {sensor_id}: авто-переобучение пропущено — {detail}")
        else:
            print(f"[AutoRetrain] Sensor {sensor_id}: ошибка {response.status_code}: {response.text[:200]}")
            logger.error(f"Sensor {sensor_id}: ошибка {response.status_code}")

    except httpx.ConnectError:
        print(f"[AutoRetrain] Sensor {sensor_id}: BlackBox недоступен")
        logger.warning(f"Sensor {sensor_id}: BlackBox недоступен, авто-переобучение отложено")
    except httpx.TimeoutException:
        print(f"[AutoRetrain] Sensor {sensor_id}: таймаут 90s")
        logger.warning(f"Sensor {sensor_id}: авто-переобучение превысило таймаут 90s")
    except Exception as e:
        print(f"[AutoRetrain] Sensor {sensor_id}: неожиданная ошибка: {e}")
        logger.error(f"Sensor {sensor_id}: неожиданная ошибка авто-переобучения: {e}")
    finally:
        _retraining_in_progress[sensor_id] = False


@router.post("/")
async def ingest_data(
    data: SensorDataIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Endpoint для записи измерений датчика.

    После записи проверяет триггер авто-переобучения:
    - Если накопилось AUTO_RETRAIN_EVERY_N_POINTS новых точек с момента
      последнего обучения — запускает переобучение ML-модели в фоне.
    - Переобучение не блокирует ответ клиенту (asyncio.create_task).
    """
    # Проверим существование датчика
    sensor = await db.get(Sensor, data.sensor_id)
    if not sensor:
        raise HTTPException(status_code=404, detail="Sensor not found")

    timestamp = data.timestamp or datetime.utcnow()
    query = text("""
        INSERT INTO sensor_data (time, sensor_id, value)
        VALUES (:time, :sensor_id, :value)
    """)
    await db.execute(query, {"time": timestamp, "sensor_id": data.sensor_id, "value": data.value})
    await db.commit()

    # ─── Триггер авто-переобучения ────────────────────────────────────────────
    retrain_every = settings.AUTO_RETRAIN_EVERY_N_POINTS
    min_points = settings.AUTO_RETRAIN_MIN_POINTS

    if retrain_every > 0:
        _new_points_counter[data.sensor_id] += 1
        counter = _new_points_counter[data.sensor_id]

        # Проверяем: накопилось ли достаточно точек для переобучения?
        if counter >= retrain_every:
            # Проверяем общее количество точек в БД (нужно минимум min_points)
            count_result = await db.execute(
                text("SELECT COUNT(*) FROM sensor_data WHERE sensor_id = :sid"),
                {"sid": data.sensor_id}
            )
            total_points = count_result.scalar()

            if total_points >= min_points:
                    msg = (f"Sensor {data.sensor_id}: накоплено {counter} новых точек "
                           f"(всего {total_points}), запускаем авто-переобучение...")
                    print(f"[AutoRetrain] {msg}")
                    logger.info(msg)
                    # Запускаем переобучение через BackgroundTasks FastAPI
                    background_tasks.add_task(_sync_retrain, data.sensor_id)
            else:
                logger.debug(
                    f"Sensor {data.sensor_id}: {total_points} точек < {min_points} минимума, "
                    f"авто-переобучение пропущено"
                )

    return {
        "status": "ok",
        "auto_retrain_in": max(0, retrain_every - _new_points_counter[data.sensor_id])
            if retrain_every > 0 else None
    }


@router.get("/", response_model=List[SensorDataOut])
async def get_sensor_data(
    sensor_id: int = Query(...),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    limit: int = Query(1000, le=10000),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем доступ к датчику
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    # Базовый SQL и словарь с параметрами
    sql = """
        SELECT time, sensor_id, value
        FROM sensor_data
        WHERE sensor_id = :sensor_id
    """
    params = {"sensor_id": sensor_id}

    # Добавляем условия для start и end только если они переданы
    if start is not None:
        sql += " AND time >= :start"
        params["start"] = start
    if end is not None:
        sql += " AND time <= :end"
        params["end"] = end

    # Добавляем сортировку и лимит
    sql += " ORDER BY time DESC LIMIT :limit"
    params["limit"] = limit

    # Выполняем запрос
    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]


@router.get("/retrain-status")
async def get_retrain_status(
    sensor_id: int = Query(..., description="ID датчика"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Возвращает статус авто-переобучения для датчика:
    - сколько новых точек накоплено
    - через сколько точек произойдёт следующее переобучение
    - идёт ли переобучение прямо сейчас
    """
    sensor = await db.get(Sensor, sensor_id)
    if not sensor or sensor.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Sensor not found or access denied")

    retrain_every = settings.AUTO_RETRAIN_EVERY_N_POINTS
    counter = _new_points_counter[sensor_id]

    return {
        "sensor_id": sensor_id,
        "auto_retrain_enabled": retrain_every > 0,
        "retrain_every_n_points": retrain_every,
        "new_points_since_last_train": counter,
        "points_until_next_retrain": max(0, retrain_every - counter) if retrain_every > 0 else None,
        "retraining_in_progress": _retraining_in_progress[sensor_id],
    }
