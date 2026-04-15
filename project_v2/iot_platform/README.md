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

## Архитектура

```
┌─────────────┐     HTTP     ┌─────────────┐     SQL      ┌──────────────┐
│  Симулятор  │ ──────────→  │  Backend    │ ──────────→  │ TimescaleDB  │
│  Flask:5001 │              │  FastAPI    │              │ PostgreSQL   │
└─────────────┘              │  :8000      │              │ :5432        │
                             └──────┬──────┘              └──────────────┘
                                    │ HTTP
                                    ↓
┌─────────────┐     HTTP      ┌─────────────┐
│  Frontend   │ ──────────→  │  BlackBox   │
│  React:3000 │              │  ML FastAPI │
└─────────────┘              │  :8001      │
                             └─────────────┘
```

## Микросервисы

| Сервис | Технология | Порт | README |
|--------|-----------|------|--------|
| **Backend API** | FastAPI + SQLAlchemy | 8000 | [backend/README.md](backend/README.md) |
| **BlackBox ML** | FastAPI + scikit-learn | 8001 | [blackbox/README.md](blackbox/README.md) |
| **Frontend** | React 18 + Recharts | 3000 | [frontend/README.md](frontend/README.md) |
| **Simulator** | Flask + APScheduler | 5001 | [simulator/README.md](simulator/README.md) |
| **Database** | TimescaleDB (PostgreSQL 14) | 5432 | [database/README.md](database/README.md) |

## Быстрый старт

### Требования
- Docker 20.10+
- Docker Compose v2

### Запуск всей системы

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
curl http://localhost:8001/
# {"message": "BlackBox ML Service", "status": "ready"}

# Frontend
open http://localhost:3000

# Симулятор
open http://localhost:5001

# API документация
open http://localhost:8000/docs
open http://localhost:8001/docs
```

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
  -d '{"name": "Температура_1", "sensor_type": "temperature", "unit": "°C"}'
# Запомните id датчика из ответа (обычно 1)
```

### 3. Отправка данных через симулятор
Открыть `http://localhost:5001`, ввести ID датчика и токен, нажать «Запустить».

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
# База данных
POSTGRES_USER=iotuser
POSTGRES_PASSWORD=iotpassword
POSTGRES_DB=iotdb
DATABASE_URL=postgresql+asyncpg://iotuser:iotpassword@db:5432/iotdb

# Безопасность
SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Сервисы
BLACKBOX_URL=http://blackbox:8001
BACKEND_URL=http://backend:8000

# BlackBox ML
BLACKBOX_DATABASE_URL=postgresql://iotuser:iotpassword@db:5432/iotdb
BLACKBOX_MODELS_DIR=/app/models

# Авто-переобучение
AUTO_RETRAIN_EVERY_N_POINTS=20   # переобучать каждые 20 новых точек
AUTO_RETRAIN_MIN_POINTS=10       # минимум точек для первого обучения
```

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
├── blackbox/               # ML-микросервис
│   ├── README.md
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── frontend/               # React SPA
│   ├── README.md
│   ├── Dockerfile
│   ├── package.json
│   └── src/
├── simulator/              # Генератор данных
│   ├── README.md
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
└── database/               # Документация БД
    └── README.md
```

## Технологический стек

### Backend
- **Python 3.11** — язык программирования
- **FastAPI 0.104** — асинхронный веб-фреймворк
- **SQLAlchemy 2.0** — ORM с поддержкой async/await
- **asyncpg** — асинхронный драйвер PostgreSQL
- **Pydantic v2** — валидация данных
- **python-jose** — JWT-токены
- **bcrypt** — хэширование паролей
- **httpx** — HTTP-клиент (async для API, sync для BackgroundTasks)

### ML / Data Science
- **scikit-learn 1.3** — LinearRegression, IsolationForest
- **numpy 1.26** — числовые вычисления
- **pandas 2.1** — обработка данных
- **joblib** — сериализация моделей

### Frontend
- **React 18** — UI-фреймворк
- **React Router 6** — маршрутизация
- **Recharts** — графики временных рядов
- **Axios** — HTTP-запросы
- **Bootstrap 5** — CSS-фреймворк

### Infrastructure
- **TimescaleDB** (PostgreSQL 14) — база данных временных рядов
- **Docker Compose v2** — оркестрация контейнеров
- **Flask + APScheduler** — симулятор данных

## ML-алгоритмы

### Linear Regression Forecaster
Прогнозирует будущие значения временного ряда на основе инженерных признаков:
- Lag-признаки (t-1, t-2, t-3)
- Скользящее среднее и стандартное отклонение (окно 5)
- Временной тренд
- Временны́е признаки (час, минута)

Итеративный прогноз: каждый следующий шаг строится на основе предыдущих предсказаний.

### Isolation Forest Detector
Обнаруживает аномалии методом изоляционного леса:
- `contamination=0.05` — ожидается 5% аномалий
- Признаки: значение, скользящее среднее, отклонение
- Возвращает `anomaly_score` (чем ближе к -1, тем аномальнее)

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
- При накоплении `AUTO_RETRAIN_EVERY_N_POINTS` точек запускается фоновое переобучение
- Переобучение выполняется через `BackgroundTasks` FastAPI (threadpool) с синхронным `httpx.Client`
- Каждое переобучение использует **скользящее окно** — только последние 50 точек
- Dashboard отображает прогресс-бар и счётчик до следующего переобучения
- При завершении переобучения прогнозы и аномалии обновляются автоматически

## Управление контейнерами

```bash
# Запуск
docker compose up -d

# Остановка
docker compose down

# Просмотр логов
docker compose logs -f backend
docker compose logs -f blackbox

# Мониторинг авто-переобучения
docker logs iot_backend 2>&1 | grep AutoRetrain

# Перезапуск одного сервиса
docker compose restart backend

# Полный сброс (включая данные!)
docker compose down -v
docker compose up --build

# Статус
docker compose ps
```

## Известные ограничения и направления развития

| Ограничение | Решение в будущем |
|------------|------------------|
| Нет MQTT-брокера | Добавить Mosquitto + paho-mqtt |
| Только HTTP (нет WebSocket) | Заменить SSE на WebSocket |
| Нет горизонтального масштабирования | Kubernetes + HPA |
| Нет мобильного приложения | React Native |
| Нет алертов | Интеграция с Telegram Bot API |
| ML только Linear Regression | Добавить LSTM через BasePredictor |
| Счётчик авто-переобучения в памяти | Redis для персистентного хранения |

## Лицензия

Разработано в учебных целях. Все права принадлежат автору.
