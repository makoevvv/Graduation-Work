# IoT Platform — Платформа для сбора и анализа данных с датчиков IoT с предиктивной аналитикой

ВКР Макоев Р.З., группа БФИ2203, направление 02.03.02 «Фундаментальная информатика и информационные технологии»  
Московский технический университет связи и информатики, 2026

---

## Описание

Микросервисная платформа для сбора данных с IoT-датчиков в реальном времени с модулем предиктивной аналитики на основе машинного обучения. Система позволяет:

- 📡 **Собирать данные** с датчиков через REST API
- 📊 **Визуализировать** временные ряды на интерактивном дашборде
- 🤖 **Прогнозировать** будущие значения (Linear Regression)
- 🚨 **Обнаруживать аномалии** в данных (Isolation Forest)
- 🔄 **Авто-переобучать** ML-модель при накоплении новых данных (Concept Drift Detection)
- 🌡️ **Симулировать** работу датчиков для тестирования
- 🏭 **Управлять иерархией** объектов: Предприятие → Устройство → Группа → Датчик

## Архитектура

```
┌─────────────┐     HTTP      ┌─────────────┐     SQL      ┌──────────────┐
│  Симулятор   │ ──────────→  │  Backend    │ ──────────→  │ TimescaleDB  │
│  Flask:5001  │              │  FastAPI    │              │ PostgreSQL   │
└─────────────┘              │  :8000      │              │ :5432        │
                              └──────┬──────┘              └──────────────┘
                                     │ HTTP (proxy)
┌─────────────┐     HTTP      ┌──────┴──────┐
│  Frontend   │ ──────────→  │  BlackBox   │
│  React:3000 │──→ Backend   │  ML FastAPI │
└─────────────┘              │  :8001      │
                              └─────────────┘
```

> **Примечание:** Frontend обращается **только к Backend** (порт 8000). Backend проксирует ML-запросы к BlackBox (обучение, прогнозы, аномалии). Прямого взаимодействия Frontend ↔ BlackBox нет.

## Иерархия объектов

Система поддерживает многоуровневую иерархию для организации IoT-инфраструктуры:

```
Enterprise (предприятие: завод, объект, здание)
  └── Device (устройство/оборудование: насос, конвейер, HVAC)
        ├── Group (логическая группа датчиков, опционально)
        └── Sensor (датчик: температура, давление, вибрация)
              ├── SensorData (гипертаблица измерений TimescaleDB)
              └── Predictions (прогнозы ML-модели)
```

**Управление доступом:**
- `User ←→ Enterprise` через таблицу `user_enterprise_access`
- Роли: `owner` / `admin` / `viewer`
- Один пользователь может иметь доступ к нескольким предприятиям с разными ролями

## Микросервисы

| Сервис | Технология | Порт | README |
|--------|-----------|------|--------|
| **Backend API** | FastAPI + SQLAlchemy | 8000 | [backend/README.md](backend/README.md) |
| **BlackBox ML** | FastAPI + scikit-learn | 8001 | [blackbox/README.md](blackbox/README.md) |
| **Frontend** | React 19 + Recharts 3 | 3000 | [frontend/README.md](frontend/README.md) |
| **Simulator** | Flask + APScheduler | 5001 | [simulator/README.md](simulator/README.md) |
| **Database** | TimescaleDB (PostgreSQL 14) | 5432 | [database/README.md](database/README.md) |

## Быстрый старт

### Требования
- Docker 20.10+
- Docker Compose v2

### Способ 1: Через скрипты (рекомендуется)

```bash
# 1. Перейти в директорию платформы
cd project_v2/iot_platform

# 2. Сделать скрипты исполняемыми (один раз)
chmod +x scripts/*.sh

# 3. Запустить все сервисы
./scripts/start.sh
# Скрипт автоматически:
# - проверит наличие Docker и Docker Compose
# - проверит наличие .env файла
# - остановит старые контейнеры
# - соберёт и запустит все сервисы
# - дождётся готовности PostgreSQL
# - выведет информацию о доступных сервисах
```

Другие скрипты:
```bash
# Остановка (с сохранением данных)
./scripts/stop.sh

# Полная очистка (удаление всех данных и volumes!)
./scripts/clean.sh
```

Подробнее: [scripts/README.md](scripts/README.md)

### Способ 2: Вручную через Docker Compose

```bash
# 1. Перейти в директорию платформы
cd project_v2/iot_platform

# 2. Запустить все сервисы
docker compose up --build

# 3. Дождаться запуска (30-60 секунд)
# Проверить статус:
docker compose ps
```

### Проверка работоспособности

```bash
# Backend API
curl http://localhost:8000/health
# {"status": "ok"}

# BlackBox ML
curl http://localhost:8001/health
# {"status": "ok", "service": "blackbox"}

# Frontend
open http://localhost:3000

# Симулятор
open http://localhost:5001

# API документация
open http://localhost:8000/docs
open http://localhost:8001/docs
```

## API Endpoints

### Backend API (`http://localhost:8000/api/v1`)

| Группа | Метод | Endpoint | Описание |
|--------|-------|----------|----------|
| **Auth** | POST | `/auth/register` | Регистрация пользователя |
| **Auth** | POST | `/auth/login` | Вход (получение JWT-токена) |
| **Enterprises** | GET/POST | `/enterprises/` | Список / создание предприятий |
| **Enterprises** | GET/PUT/DELETE | `/enterprises/{id}` | Операции с предприятием |
| **Devices** | GET/POST | `/devices/` | Список / создание устройств |
| **Devices** | GET/PUT/DELETE | `/devices/{id}` | Операции с устройством |
| **Groups** | GET/POST | `/groups/` | Список / создание групп |
| **Groups** | GET/PUT/DELETE | `/groups/{id}` | Операции с группой |
| **Sensors** | GET/POST | `/sensors/` | Список / создание датчиков |
| **Sensors** | GET/PUT/DELETE | `/sensors/{id}` | Операции с датчиком |
| **Data** | POST | `/data/` | Запись измерений (+ триггер авто-переобучения) |
| **Data** | GET | `/data/` | Получение данных датчика |
| **Data** | GET | `/data/retrain-status` | Статус авто-переобучения |
| **Predictions** | GET | `/predictions/` | Сохранённые прогнозы |
| **Predictions** | POST | `/predictions/train` | Обучение ML-модели |
| **Predictions** | GET | `/predictions/status` | Статус ML-модели |
| **Predictions** | GET | `/predictions/anomalies` | Детекция аномалий |

### BlackBox ML API (`http://localhost:8001`)

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/train?sensor_id=X` | Обучить модели на данных датчика |
| GET | `/predict?sensor_id=X&steps=N` | Получить прогноз |
| GET | `/anomalies?sensor_id=X` | Детектировать аномалии |
| GET | `/status?sensor_id=X` | Статус обученной модели |
| GET | `/health` | Проверка работоспособности |

## Тестовые данные

Для быстрой демонстрации выполните следующие шаги:

### 1. Регистрация и вход
```bash
# Регистрация
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "email": "test@example.com", "password": "testpass123"}'

# Вход (получение токена)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=testuser&password=testpass123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo "Token: $TOKEN"
```

### 2. Создание датчика
```bash
curl -X POST http://localhost:8000/api/v1/sensors/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Температура_1", "type": "temperature", "unit": "°C"}'
# Запомните id датчика из ответа (обычно 1)
```

### 3. Отправка данных через симулятор
Открыть `http://localhost:5001`, ввести ID датчика, выбрать тип и параметры, нажать «Запустить».

Или через API:
```bash
# Отправить 30 измерений
for i in $(seq 1 30); do
  VALUE=$(python3 -c "import random; print(round(20 + random.gauss(0,2), 2))")
  curl -s -X POST http://localhost:8000/api/v1/data/ \
    -H "Content-Type: application/json" \
    -d "{\"sensor_id\": 1, \"value\": $VALUE}" > /dev/null
  sleep 0.1
done
echo "Данные отправлены"
```

### 4. Обучение ML-модели
```bash
curl -X POST "http://localhost:8000/api/v1/predictions/train?sensor_id=1" \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Просмотр результатов
Открыть `http://localhost:3000`, войти как `testuser` / `testpass123`.

### 6. Авто-переобучение
После накопления 20 новых точек модель переобучается автоматически. Статус виден на Dashboard в карточке ML-модели (прогресс-бар и счётчик «через N точек»).

## Конфигурация (`.env`)

```env
# PostgreSQL / TimescaleDB
POSTGRES_USER=iot_user
POSTGRES_PASSWORD=strong_password
POSTGRES_DB=iot_db
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Backend
BACKEND_SECRET_KEY=super-secret-key-change-in-production
BACKEND_PORT=8000
BACKEND_LOG_LEVEL=INFO

# BlackBox (ML-сервис)
BLACKBOX_URL=http://blackbox:8001
BLACKBOX_PORT=8001
BLACKBOX_FORECAST_STEPS=10          # шагов прогноза вперёд
BLACKBOX_MIN_TRAIN_POINTS=20        # минимум точек для обучения
BLACKBOX_ANOMALY_CONTAMINATION=0.05 # ожидаемая доля аномалий (5%)

# Simulator
SIMULATOR_PORT=5001
BACKEND_URL=http://backend:8000

# Frontend (для браузера — localhost)
REACT_APP_BACKEND_URL=http://localhost:8000
```

> **Примечание:** `DATABASE_URL` строится динамически в коде из `POSTGRES_*` переменных. Отдельно задавать его не нужно.

### Параметры авто-переобучения (в коде backend)

| Параметр | Значение | Описание |
|----------|----------|----------|
| `AUTO_RETRAIN_EVERY_N_POINTS` | 20 | Переобучать каждые N новых точек |
| `AUTO_RETRAIN_MIN_POINTS` | 10 | Минимум точек для первого обучения |
| `TRAIN_WINDOW_POINTS` | 50 | Скользящее окно обучения (blackbox) |

## Структура проекта

```
iot_platform/
├── docker-compose.yml      # Оркестрация всех сервисов
├── .env                    # Переменные окружения
├── init.sql                # Инициализация БД (TimescaleDB)
├── README.md               # Этот файл
├── backend/                # FastAPI Backend API
│   ├── README.md
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── api/v1/endpoints/  # auth, enterprises, devices, groups, sensors, data, predictions
│       ├── core/              # config, database, security
│       ├── models/            # SQLAlchemy ORM модели
│       ├── schemas/           # Pydantic схемы
│       └── utils/             # logging
├── blackbox/               # ML-микросервис
│   ├── README.md
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── ml_engine.py    # LinearRegressionForecaster, IsolationForestDetector
│       └── schemas.py
├── frontend/               # React SPA
│   ├── README.md
│   ├── Dockerfile
│   ├── package.json
│   └── src/
│       ├── components/     # Layout, Navbar, PrivateRoute, SensorChart
│       ├── context/        # AuthContext
│       ├── pages/          # Dashboard, Devices, Enterprises, Groups, Login, Register, Sensors
│       └── services/       # api.js
├── simulator/              # Генератор данных с веб-интерфейсом
│   ├── README.md
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   ├── templates/          # index.html
│   └── static/             # script.js, style.css
├── scripts/                # Скрипты управления
│   ├── README.md
│   ├── start.sh            # Запуск всех сервисов
│   ├── stop.sh             # Остановка (с сохранением данных)
│   └── clean.sh            # Полная очистка (удаление данных)
└── database/               # Документация БД
    └── README.md
```

## Технологический стек

### Backend
- **Python 3.11** — язык программирования
- **FastAPI 0.104.1** — асинхронный веб-фреймворк
- **SQLAlchemy 2.0.23** — ORM с поддержкой async/await
- **asyncpg 0.29.0** — асинхронный драйвер PostgreSQL
- **Pydantic v2 (2.5.0)** — валидация данных
- **pydantic-settings 2.1.0** — управление конфигурацией
- **python-jose** — JWT-токены
- **passlib + bcrypt** — хэширование паролей
- **httpx 0.25.2** — HTTP-клиент (async для API, sync для BackgroundTasks)
- **loguru 0.7.2** — структурированное логирование
- **alembic 1.12.1** — миграции БД
- **email-validator 2.1.0** — валидация email

### ML / Data Science
- **scikit-learn 1.3.2** — LinearRegression, IsolationForest
- **numpy 1.26.2** — числовые вычисления
- **pandas 2.1.3** — обработка данных
- **joblib 1.3.2** — сериализация моделей

### Frontend
- **React 19** — UI-фреймворк
- **React Router 7** — маршрутизация
- **Recharts 3** — графики временных рядов
- **Axios 1.13** — HTTP-запросы
- **Bootstrap 5.3** — CSS-фреймворк

### Infrastructure
- **TimescaleDB** (PostgreSQL 14) — база данных временных рядов
- **Docker Compose v2** — оркестрация контейнеров
- **Flask 2.3 + APScheduler 3.10** — симулятор данных с SSE

## ML-алгоритмы

### Linear Regression Forecaster
Прогнозирует будущие значения временного ряда на основе инженерных признаков:
- `t` — порядковый номер точки (линейный тренд)
- `t²` — квадратичный тренд
- `ma5` — скользящее среднее за 5 точек
- `ma10` — скользящее среднее за 10 точек

Итеративный прогноз: каждый следующий шаг строится на основе предыдущих предсказаний. Значения нормализуются через `StandardScaler` для стабильности обучения.

### Isolation Forest Detector
Обнаруживает аномалии методом изоляционного леса:
- `contamination=0.05` — ожидается 5% аномалий
- Признаки: значение, отклонение от скользящего среднего, z-score
- `n_estimators=100` — количество деревьев в ансамбле
- Возвращает `anomaly_score` (чем ниже score, тем аномальнее точка)

### Паттерн Strategy
Базовый класс `BasePredictor` (ABC) позволяет добавлять новые алгоритмы (LSTM, Prophet, ARIMA) без изменения API.

### Скользящее окно обучения (Sliding Window)
Механизм адаптации модели к изменяющимся данным. Вместо обучения на всей истории используются только последние `TRAIN_WINDOW_POINTS` точек:
- Параметр `TRAIN_WINDOW_POINTS=50` в `blackbox/app/config.py`
- SQL-запрос: `ORDER BY time DESC LIMIT 50` + `reversed()` для восстановления хронологии
- Предотвращает деградацию точности при длительной работе системы (concept drift)
- Модель всегда отражает **актуальный** паттерн данных, а не усреднённый за всю историю

### Авто-переобучение (Concept Drift Detection)
При изменении паттерна данных (concept drift) модель устаревает. Система автоматически переобучает модель:
- Счётчик новых точек с момента последнего обучения хранится в памяти процесса
- При накоплении `AUTO_RETRAIN_EVERY_N_POINTS` (20) точек запускается фоновое переобучение
- Переобучение выполняется через `BackgroundTasks` FastAPI (threadpool) с синхронным `httpx.Client`
- Каждое переобучение использует **скользящее окно** — только последние 50 точек
- Dashboard отображает прогресс-бар и счётчик до следующего переобучения
- При завершении переобучения прогнозы и аномалии обновляются автоматически

## Управление контейнерами

```bash
# Запуск (через скрипт — рекомендуется)
./scripts/start.sh

# Запуск (вручную)
docker compose up -d

# Остановка (через скрипт)
./scripts/stop.sh

# Остановка (вручную)
docker compose down

# Просмотр логов
docker compose logs -f backend
docker compose logs -f blackbox

# Мониторинг авто-переобучения
docker logs iot_backend 2>&1 | grep AutoRetrain

# Перезапуск одного сервиса
docker compose restart backend

# Полный сброс (включая данные!)
./scripts/clean.sh
# или вручную:
docker compose down -v
docker compose up --build

# Статус
docker compose ps
```

## Известные ограничения и направления развития

| Ограничение | Решение в будущем |
|------------|------------------|
| Нет MQTT-брокера | Добавить Mosquitto + paho-mqtt |
| Нет WebSocket для real-time обновлений | WebSocket в Backend (SSE уже реализован в симуляторе) |
| Нет горизонтального масштабирования | Kubernetes + HPA |
| Нет мобильного приложения | React Native |
| Нет алертов | Интеграция с Telegram Bot API |
| ML только Linear Regression | Добавить LSTM через BasePredictor |
| Счётчик авто-переобучения в памяти | Redis для персистентного хранения |

## Лицензия

Разработано в учебных целях. Все права принадлежат автору.
