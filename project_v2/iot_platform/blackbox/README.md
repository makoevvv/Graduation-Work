# BlackBox ML — Сервис предиктивной аналитики

Изолированный микросервис машинного обучения. Принимает исторические данные датчиков, обучает модели прогнозирования и детекции аномалий, возвращает результаты через REST API. Реализован на **FastAPI** + **scikit-learn**.

## Назначение

BlackBox намеренно изолирован от основного бэкенда в отдельный сервис. Это позволяет:
- **Независимо масштабировать** ML-вычисления (отдельный контейнер с большим CPU/RAM)
- **Заменять алгоритмы** без изменения основного API (паттерн Strategy)
- **Изолировать зависимости** — тяжёлые библиотеки (numpy, scikit-learn) не попадают в основной образ
- **Переиспользовать** сервис для других источников данных
- **Поддерживать авто-переобучение** — Backend вызывает `/train` в фоне при накоплении новых данных

## Технологии

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| FastAPI | 0.104.1 | REST API |
| scikit-learn | 1.3.2 | ML-алгоритмы |
| numpy | 1.26.2 | Числовые вычисления |
| pandas | 2.1.3 | Обработка временных рядов |
| joblib | 1.3.2 | Сериализация моделей на диск |
| asyncpg | 0.29.0 | Прямой доступ к TimescaleDB |
| loguru | 0.7.2 | Структурированное логирование |
| uvicorn | 0.24.0 | ASGI-сервер |

## Структура проекта

```
blackbox/
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI приложение, эндпоинты
│   ├── ml_engine.py   # Ядро ML: модели, обучение, прогнозирование
│   ├── database.py    # Прямое подключение к TimescaleDB через asyncpg
│   ├── schemas.py     # Pydantic-схемы запросов/ответов
│   └── config.py      # Настройки через pydantic-settings
├── Dockerfile
└── requirements.txt
```

## Запуск

### Через Docker Compose (рекомендуется)
```bash
cd project_v2/iot_platform
docker compose up blackbox
```

### Локально
```bash
cd blackbox
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

## Переменные окружения

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `POSTGRES_USER` | `iot_user` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `strong_password` | Пароль PostgreSQL |
| `POSTGRES_DB` | `iot_db` | Имя базы данных |
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL |
| `FORECAST_STEPS` | `10` | Количество шагов прогноза (по умолчанию) |
| `MIN_TRAIN_POINTS` | `20` | Минимум точек для обучения |
| `ANOMALY_CONTAMINATION` | `0.05` | Ожидаемая доля аномалий |
| `TRAIN_WINDOW_POINTS` | `50` | Скользящее окно: обучать на последних N точках (0 = без ограничения) |

> **Примечание:** `DATABASE_URL` строится автоматически из `POSTGRES_*` переменных в `config.py`.

## API Эндпоинты

Документация: `http://localhost:8001/docs`

### `POST /train?sensor_id=1&forecast_steps=10&save_to_db=true`

Обучает модели LinearRegression и IsolationForest на исторических данных датчика. Данные загружаются напрямую из TimescaleDB. Используется **скользящее окно** — только последние `TRAIN_WINDOW_POINTS` точек.

**Query-параметры:**
| Параметр | Тип | По умолчанию | Описание |
|---------|-----|-------------|---------|
| `sensor_id` | int | — | ID датчика |
| `forecast_steps` | int | 10 | Количество шагов прогноза |
| `save_to_db` | bool | true | Сохранять прогнозы в таблицу `predictions` |
| `limit` | int | 0 | Переопределить размер окна (0 = использовать `TRAIN_WINDOW_POINTS`) |

**Ответ:**
```json
{
  "sensor_id": 1,
  "trained_at": "2026-04-13T18:41:27+00:00",
  "train_points": 50,
  "forecast": [
    {"prediction_time": "2026-04-13T18:42:00+00:00", "value": 84.73},
    {"prediction_time": "2026-04-13T18:43:00+00:00", "value": 85.12}
  ],
  "anomaly_count": 3,
  "anomaly_indices": [5, 12, 37],
  "model_info": {
    "forecaster": {"type": "LinearRegressionForecaster", "is_fitted": true, "train_points": 50},
    "detector": {"type": "IsolationForestDetector", "contamination": 0.05, "is_fitted": true}
  }
}
```

**Используется для авто-переобучения** — Backend вызывает этот эндпоинт через синхронный `httpx.Client` в `BackgroundTasks`.

### `GET /predict?sensor_id=1&steps=10`

Возвращает прогноз на N шагов вперёд (модель должна быть предварительно обучена).

**Ответ:**
```json
{
  "sensor_id": 1,
  "steps": 10,
  "forecast": [
    {"prediction_time": "2026-04-13T18:42:00+00:00", "value": 84.73},
    {"prediction_time": "2026-04-13T18:43:00+00:00", "value": 85.12}
  ]
}
```

### `GET /anomalies?sensor_id=1&limit=100`

Детектирует аномалии в последних данных датчика.

**Ответ:**
```json
{
  "sensor_id": 1,
  "analyzed_points": 100,
  "anomaly_count": 3,
  "anomalies": [
    {
      "index": 5,
      "time": "2026-04-13T10:15:16+00:00",
      "value": 20.47,
      "score": -0.5964
    }
  ]
}
```

### `GET /status?sensor_id=1`

Возвращает статус обученных моделей.

**Ответ:**
```json
{
  "sensor_id": 1,
  "is_trained": true,
  "trained_at": "2026-04-13T18:41:27+00:00",
  "forecaster_info": {
    "type": "LinearRegressionForecaster",
    "is_fitted": true,
    "train_points": 50,
    "avg_interval_seconds": 5.0,
    "coefficients": [0.12, -0.03, 0.87, 0.45]
  }
}
```

### `GET /health`

Проверка работоспособности сервиса.

```bash
curl http://localhost:8001/health
# {"status": "ok", "service": "blackbox"}
```

## Архитектура ML-движка

### Паттерн Strategy — `BasePredictor`

```python
class BasePredictor(ABC):
    """Абстрактный базовый класс для моделей прогнозирования."""

    @abstractmethod
    def fit(self, values: np.ndarray, timestamps: np.ndarray) -> None:
        """Обучить модель на исторических данных."""

    @abstractmethod
    def predict(self, steps: int) -> Tuple[np.ndarray, np.ndarray]:
        """Вернуть (predicted_values, future_timestamps) прогноза на steps шагов."""

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Метаданные модели."""
```

Благодаря этому паттерну можно добавить новые алгоритмы (LSTM, Prophet, ARIMA) без изменения API — достаточно реализовать `BasePredictor`.

### `LinearRegressionForecaster`

Прогнозирует будущие значения временного ряда с помощью линейной регрессии на инженерных признаках.

**Признаки (feature engineering):**
| Признак | Описание |
|---------|---------|
| `t` | Порядковый номер точки (линейный тренд) |
| `t²` | Квадратичный тренд |
| `ma5` | Скользящее среднее за 5 точек |
| `ma10` | Скользящее среднее за 10 точек |

Значения нормализуются через `StandardScaler` (отдельно для X и y) для стабильности обучения.

**Алгоритм прогнозирования (итеративный):**
```
for step in range(steps):
    features = build_features(extended_values)  # t, t², ma5, ma10
    X_last = features[-1]                       # последняя строка
    X_last[0] = t_next; X_last[1] = t_next²    # обновляем тренд
    next_value = scaler_y.inverse(model.predict(scaler_X.transform(X_last)))
    append next_value to extended_values
    next_timestamp = last_timestamp + avg_interval
```

Каждый следующий прогноз строится на основе предыдущих предсказанных значений.

**Нормализация временных меток** (`_normalize_timestamps`):
Метод конвертирует любые форматы временных меток (datetime64, строки ISO, pandas Timestamp, объекты datetime) в единый формат `datetime` Python для корректной работы.

### `IsolationForestDetector`

Обнаруживает аномалии методом изоляционного леса (Isolation Forest).

**Принцип работы:**
- Аномальные точки изолируются быстрее нормальных при случайном разбиении пространства признаков
- Параметр `contamination=0.05` означает, что ожидается ~5% аномалий в данных
- `n_estimators=100` — количество деревьев в ансамбле
- Возвращает `anomaly_score`: чем ниже score, тем более аномальна точка

**Признаки для детекции:**
| Признак | Описание |
|---------|---------|
| `value` | Само значение датчика |
| `deviation` | Отклонение от скользящего среднего (окно 5) |
| `z_score` | Стандартизованное отклонение (z-score) |

### Скользящее окно обучения (Sliding Window)

Ключевой механизм адаптации модели к изменяющимся данным (**concept drift**).

**Проблема без скользящего окна:**
```
Старые данные (125 точек): min=-4.6°C, max=87.5°C, avg=44.2°C  ← устаревший паттерн
Новые данные  (50 точек):  min=15.0°C, max=39.5°C, avg=27.3°C  ← актуальный паттерн
→ Модель, обученная на всех 175 точках, даёт неточные прогнозы
```

**Решение — обучение только на последних N точках:**
```python
# config.py
TRAIN_WINDOW_POINTS: int = 50   # обучать только на последних 50 точках

# main.py — fetch_sensor_data()
query = text("""
    SELECT time, value FROM sensor_data
    WHERE sensor_id = :sensor_id
    ORDER BY time DESC LIMIT :limit   -- берём последние N
""")
rows = list(reversed(rows))           -- разворачиваем в ASC для обучения
```

**Сравнение подходов:**
| Подход | Данные для обучения | Адаптация к drift | Точность на новых данных |
|--------|--------------------|--------------------|--------------------------|
| Без окна | Все 175 точек (avg=44°C) | ✗ | Низкая |
| Скользящее окно 50 | Последние 50 (avg=27°C) | ✓ | Высокая |

**Результат тестирования:**
```
train_points = 50  (последние 50 точек, avg=27.25°C)
forecast[0]  = 28.3°C  ← соответствует актуальному диапазону
forecast[-1] = 29.1°C
```

### `ModelManager`

Управляет жизненным циклом моделей:
- Хранит обученные модели в памяти (`dict[sensor_id → (forecaster, detector)]`)
- Сохраняет/загружает модели на диск через `joblib` (директория `/tmp/iot_models`)
- Предоставляет единый интерфейс для обучения, прогнозирования и детекции

```python
manager = ModelManager(models_dir="/tmp/iot_models")

# Обучение
manager.train(sensor_id=1, values=np.array([...]), timestamps=[...])

# Прогноз
forecasts = manager.get_forecast(sensor_id=1, steps=10)

# Аномалии
result = manager.detect_anomalies(sensor_id=1, values=np.array([...]))

# Статус
status = manager.get_status(sensor_id=1)
```

## Сохранение моделей

Модели сохраняются в файлы:
- `/tmp/iot_models/sensor_{sensor_id}.joblib` — обе модели (forecaster + detector) в одном файле

При перезапуске контейнера модели автоматически загружаются с диска (Docker volume `blackbox_models`).

## Минимальные требования к данным

- Для обучения: минимум **20 точек** данных (`MIN_TRAIN_POINTS` в config)
- Для прогнозирования: модель должна быть предварительно обучена
- Для детекции аномалий: модель должна быть предварительно обучена

## Расширение: добавление новой модели

```python
class LSTMForecaster(BasePredictor):
    """Пример добавления LSTM без изменения API."""

    def fit(self, values, timestamps):
        # Обучение LSTM через TensorFlow/PyTorch
        ...

    def predict(self, steps):
        # Прогноз через LSTM
        ...

    def get_model_info(self):
        return {"type": "LSTMForecaster", ...}

# В ModelManager достаточно заменить:
# forecaster = LSTMForecaster()  вместо LinearRegressionForecaster()
```
