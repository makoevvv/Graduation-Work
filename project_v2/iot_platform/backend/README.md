# Backend API — IoT Platform

Основной бэкенд-сервис платформы. Реализован на **FastAPI** с асинхронным доступом к базе данных через **SQLAlchemy 2.0 + asyncpg**. Обеспечивает REST API для управления пользователями, предприятиями, устройствами, датчиками, данными и ML-прогнозами. Включает механизм **авто-переобучения** ML-модели при накоплении новых данных.

## Технологии

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| FastAPI | 0.104.1 | Веб-фреймворк, OpenAPI-документация |
| SQLAlchemy | 2.0.23 | Асинхронный ORM |
| asyncpg | 0.29.0 | Асинхронный драйвер PostgreSQL |
| Pydantic | v2 (2.5.0) | Валидация данных, схемы |
| pydantic-settings | 2.1.0 | Управление конфигурацией |
| python-jose | 3.3.0 | JWT-токены |
| passlib + bcrypt | 1.7.4 / 4.0.1 | Хэширование паролей |
| httpx | 0.25.2 | HTTP-клиент (async для API, sync для BackgroundTasks) |
| loguru | 0.7.2 | Структурированное логирование |
| uvicorn | 0.24.0 | ASGI-сервер |
| alembic | 1.12.1 | Миграции БД |
| email-validator | 2.1.0 | Валидация email |

## Структура проекта

```
backend/
├── app/
│   ├── main.py              # Точка входа, lifespan, CORS, роутеры
│   ├── api/
│   │   ├── deps.py          # Зависимости FastAPI (get_current_user)
│   │   └── v1/
│   │       ├── api.py       # Регистрация всех роутеров
│   │       └── endpoints/
│   │           ├── auth.py        # /auth/register, /auth/login
│   │           ├── enterprises.py # CRUD предприятий + управление доступом
│   │           ├── devices.py     # CRUD устройств
│   │           ├── groups.py      # CRUD групп датчиков
│   │           ├── sensors.py     # CRUD датчиков
│   │           ├── data.py        # Запись/чтение измерений + авто-переобучение
│   │           └── predictions.py # Обучение ML, прогнозы, аномалии
│   ├── core/
│   │   ├── config.py        # Настройки через pydantic-settings (+ AUTO_RETRAIN_*)
│   │   ├── database.py      # Движок SQLAlchemy, сессии
│   │   └── security.py      # JWT, хэширование паролей
│   ├── models/
│   │   └── models.py        # ORM-модели: User, Enterprise, UserEnterpriseAccess, Device, Group, Sensor
│   ├── schemas/
│   │   └── schemas.py       # Pydantic-схемы запросов/ответов
│   └── utils/
│       └── logging.py       # Настройка логирования
├── Dockerfile
└── requirements.txt
```

## Запуск

### Через Docker Compose (рекомендуется)
```bash
cd project_v2/iot_platform
docker compose up backend
```

### Локально (для разработки)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Переменные окружения

| Переменная | Пример | Описание |
|-----------|--------|---------|
| `POSTGRES_USER` | `iot_user` | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | `strong_password` | Пароль PostgreSQL |
| `POSTGRES_DB` | `iot_db` | Имя базы данных |
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL |
| `SECRET_KEY` | `super-secret-key` | Ключ для подписи JWT |
| `ALGORITHM` | `HS256` | Алгоритм JWT (по умолчанию) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Время жизни токена (по умолчанию) |
| `BLACKBOX_URL` | `http://blackbox:8001` | URL ML-сервиса |
| `AUTO_RETRAIN_EVERY_N_POINTS` | `20` | Переобучать каждые N новых точек (0 = выкл) |
| `AUTO_RETRAIN_MIN_POINTS` | `10` | Минимум точек для первого обучения |
| `LOG_LEVEL` | `INFO` | Уровень логирования |

> **Примечание:** `DATABASE_URL` строится автоматически из `POSTGRES_*` переменных в `config.py`.

## API Эндпоинты

Полная документация доступна по адресу `http://localhost:8000/docs` (Swagger UI).

### Аутентификация (`/api/v1/auth`)

| Метод | Путь | Описание |
|-------|------|---------|
| `POST` | `/register` | Регистрация нового пользователя |
| `POST` | `/login` | Получение JWT access-токена |

**Пример регистрации:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "email": "user1@example.com", "password": "secret123"}'
```

**Пример входа:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=user1&password=secret123"
# Ответ: {"access_token": "eyJ...", "token_type": "bearer"}
```

### Предприятия (`/api/v1/enterprises`)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/` | Список предприятий пользователя |
| `POST` | `/` | Создать предприятие (автоматически роль `owner`) |
| `GET` | `/{id}` | Получить предприятие по ID |
| `PUT` | `/{id}` | Обновить предприятие |
| `DELETE` | `/{id}` | Удалить предприятие |

### Устройства (`/api/v1/devices`)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/` | Список устройств (фильтр по `enterprise_id`) |
| `POST` | `/` | Создать устройство |
| `GET` | `/{id}` | Получить устройство по ID |
| `PUT` | `/{id}` | Обновить устройство |
| `DELETE` | `/{id}` | Удалить устройство |

### Датчики (`/api/v1/sensors`)

| Метод | Путь | Описание |
|-------|------|---------|
| `GET` | `/` | Список датчиков (фильтр по `group_id`, `device_id`) |
| `POST` | `/` | Создать датчик |
| `GET` | `/{id}` | Получить датчик по ID |
| `PUT` | `/{id}` | Обновить датчик |
| `DELETE` | `/{id}` | Удалить датчик |

**Пример создания датчика:**
```bash
curl -X POST http://localhost:8000/api/v1/sensors/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Температура_1", "type": "temperature", "unit": "°C"}'
```

### Данные (`/api/v1/data`)

| Метод | Путь | Описание |
|-------|------|---------|
| `POST` | `/` | Записать измерение (+ триггер авто-переобучения) |
| `GET` | `/` | Получить данные датчика (с фильтрацией) |
| `GET` | `/retrain-status` | Статус авто-переобучения для датчика |

**Пример записи данных:**
```bash
curl -X POST http://localhost:8000/api/v1/data/ \
  -H "Content-Type: application/json" \
  -d '{"sensor_id": 1, "value": 23.5}'
# Ответ: {"status": "ok", "auto_retrain_in": 15}
```

**Пример получения данных:**
```bash
curl "http://localhost:8000/api/v1/data/?sensor_id=1&limit=100" \
  -H "Authorization: Bearer <token>"
```

**Статус авто-переобучения:**
```bash
curl "http://localhost:8000/api/v1/data/retrain-status?sensor_id=1" \
  -H "Authorization: Bearer <token>"
# Ответ:
# {
#   "sensor_id": 1,
#   "auto_retrain_enabled": true,
#   "retrain_every_n_points": 20,
#   "new_points_since_last_train": 7,
#   "points_until_next_retrain": 13,
#   "retraining_in_progress": false
# }
```

### Прогнозы (`/api/v1/predictions`)

| Метод | Путь | Описание |
|-------|------|---------|
| `POST` | `/train` | Запустить обучение ML-модели |
| `GET` | `/` | Получить сохранённые прогнозы |
| `GET` | `/status` | Статус ML-модели для датчика |
| `GET` | `/anomalies` | Детекция аномалий в последних данных |

**Пример обучения модели:**
```bash
curl -X POST "http://localhost:8000/api/v1/predictions/train?sensor_id=1" \
  -H "Authorization: Bearer <token>"
```

**Пример получения аномалий:**
```bash
curl "http://localhost:8000/api/v1/predictions/anomalies?sensor_id=1&limit=50" \
  -H "Authorization: Bearer <token>"
```

## Архитектура и ключевые решения

### Lifespan (startup/shutdown)

При старте приложения через `@asynccontextmanager lifespan` автоматически:
1. Создаются все таблицы через `Base.metadata.create_all` (idempotent)
2. Создаётся расширение TimescaleDB (`CREATE EXTENSION IF NOT EXISTS timescaledb`)
3. Создаётся гипертаблица `sensor_data` с партиционированием по полю `time`
4. Создаются индексы для быстрых запросов по `(sensor_id, time DESC)`

### JWT-аутентификация

Схема работы:
```
Клиент → POST /auth/login → Backend → bcrypt.verify(password) → JWT(HS256) → Клиент
Клиент → GET /sensors/ + Bearer <token> → Backend → jose.decode(token) → User → Ответ
```

Токен содержит `sub` (username) и `exp` (время истечения). Зависимость `get_current_user` декодирует токен при каждом защищённом запросе.

### Авто-переобучение ML-модели

Реализовано в `data.py`. При каждом `POST /data/`:

1. Данные записываются в TimescaleDB
2. Счётчик `_new_points_counter[sensor_id]` увеличивается на 1
3. При достижении `AUTO_RETRAIN_EVERY_N_POINTS` — запускается фоновое переобучение

```python
# Счётчики в памяти процесса
_new_points_counter: dict[int, int] = defaultdict(int)
_retraining_in_progress: dict[int, bool] = defaultdict(bool)

# Триггер в POST /data/
if counter >= retrain_every and total_points >= min_points:
    background_tasks.add_task(_sync_retrain, sensor_id)
```

**Ключевое решение:** `_sync_retrain` — синхронная функция, использующая `httpx.Client` (не `AsyncClient`). Это позволяет корректно работать в threadpool FastAPI `BackgroundTasks` без конфликтов с event loop uvicorn.

```python
def _sync_retrain(sensor_id: int) -> None:
    with httpx.Client(timeout=90.0) as client:
        response = client.post(
            f"{settings.BLACKBOX_URL}/train",
            params={"sensor_id": sensor_id, "forecast_steps": 10, "save_to_db": True},
        )
```

**Мониторинг авто-переобучения:**
```bash
docker logs iot_backend 2>&1 | grep AutoRetrain
# [AutoRetrain] Sensor 1: накоплено 20 новых точек (всего 125), запускаем авто-переобучение...
# [AutoRetrain] Sensor 1: авто-переобучение завершено (125 точек, прогнозы обновлены)
```

### Интеграция с BlackBox ML

Эндпоинты `/predictions/*` проксируют запросы к ML-сервису через `httpx.AsyncClient`:
```python
async with httpx.AsyncClient(timeout=60.0) as client:
    response = await client.post(f"{settings.BLACKBOX_URL}/train", json={...})
```

Таймаут 60 секунд для обучения, 10 секунд для статуса, 30 секунд для аномалий.

### Модели данных

```python
class User(Base):          # id, username, email, hashed_password, is_active, created_at
class Enterprise(Base):    # id, name, description, address, owner_id → User, created_at
class UserEnterpriseAccess(Base):  # id, user_id → User, enterprise_id → Enterprise, role, granted_at
class Device(Base):        # id, name, description, model, serial_number, enterprise_id → Enterprise, is_active, created_at
class Group(Base):         # id, name, description, user_id → User, device_id → Device, created_at
class Sensor(Base):        # id, name, type, unit, user_id → User, group_id → Group, device_id → Device, is_active, created_at

# Гипертаблица TimescaleDB (создаётся через raw SQL в lifespan)
# sensor_data: time TIMESTAMPTZ, sensor_id INTEGER, value DOUBLE PRECISION

# Таблица прогнозов
# predictions: id, sensor_id, prediction_time, value, created_at
```

## Логирование

Логи пишутся в `logs/backend.log` и в stdout. Уровень настраивается через `LOG_LEVEL`. Формат: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.

Авто-переобучение дополнительно выводит `print`-сообщения с префиксом `[AutoRetrain]` для удобного grep-поиска в логах контейнера.

## Healthcheck

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```
