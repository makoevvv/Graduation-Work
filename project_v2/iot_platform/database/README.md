# Database — TimescaleDB (PostgreSQL)

Хранилище данных платформы на базе **TimescaleDB** — расширения PostgreSQL, оптимизированного для временных рядов.

## Почему TimescaleDB?

| Критерий | PostgreSQL | TimescaleDB |
|---------|-----------|------------|
| Запросы к последним N точкам | Полный скан | Только нужный чанк |
| Автопартиционирование по времени | ✗ | ✓ (гипертаблица) |
| Агрегация `time_bucket` | Медленно | Оптимизировано |
| Совместимость с SQL | ✓ | ✓ (надстройка) |
| Сжатие старых данных | ✗ | ✓ |

## Технологии

- **TimescaleDB 2.x** на базе PostgreSQL 14
- **asyncpg** — асинхронный драйвер (BlackBox)
- **SQLAlchemy 2.0 + asyncpg** — ORM (Backend)

## Запуск

### Через Docker Compose (рекомендуется)
```bash
cd project_v2/iot_platform
docker compose up db
```

### Подключение напрямую
```bash
# Через psql напрямую
docker exec -it iot_postgres psql -U iot_user -d iot_db
```

## Переменные окружения

| Переменная | Значение по умолчанию |
|-----------|----------------------|
| `POSTGRES_USER` | `iot_user` |
| `POSTGRES_PASSWORD` | `iot_password` |
| `POSTGRES_DB` | `iot_db` |

---

## Схема базы данных

### Иерархия объектов

```
Enterprise (предприятие)
  ├── user_enterprise_access  ← M2M: пользователи с ролями
  └── Device (устройство/оборудование)
        ├── Group (логическая группа датчиков, опционально)
        └── Sensor (датчик)
              ├── SensorData  ← гипертаблица измерений
              └── Predictions ← прогнозы ML
```

---

### Таблица `users`

```sql
CREATE TABLE users (
    id               SERIAL PRIMARY KEY,
    username         VARCHAR(50)  UNIQUE NOT NULL,
    email            VARCHAR(100) UNIQUE NOT NULL,
    hashed_password  VARCHAR(255) NOT NULL,
    is_active        BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
```

---

### Таблица `enterprises` ⭐ новая

Верхний уровень иерархии. Предприятие — завод, объект, здание.

```sql
CREATE TABLE enterprises (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    description TEXT,
    address     TEXT,
    owner_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

### Таблица `user_enterprise_access` ⭐ новая

M2M: доступ пользователей к предприятиям с ролями.

```sql
CREATE TABLE user_enterprise_access (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(id) ON DELETE CASCADE,
    role          VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- owner / admin / viewer
    granted_at    TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, enterprise_id)
);
```

**Роли:**
| Роль | Просмотр | Управление устройствами | Управление доступом | Удаление предприятия |
|------|---------|------------------------|--------------------|--------------------|
| `viewer` | ✓ | ✗ | ✗ | ✗ |
| `admin` | ✓ | ✓ | ✓ | ✗ |
| `owner` | ✓ | ✓ | ✓ | ✓ |

---

### Таблица `devices` ⭐ новая

Второй уровень: физическое оборудование внутри предприятия.

```sql
CREATE TABLE devices (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(150) NOT NULL,
    description   TEXT,
    model         VARCHAR(100),        -- модель оборудования
    serial_number VARCHAR(100),        -- серийный номер
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(id) ON DELETE CASCADE,
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

### Таблица `groups`

Логические папки/категории датчиков. Расширена полем `device_id`.

```sql
CREATE TABLE groups (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    description TEXT,
    user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,    -- обратная совместимость
    device_id   INTEGER REFERENCES devices(id) ON DELETE SET NULL, -- новое поле
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

---

### Таблица `sensors`

Расширена полями `device_id` и `is_active`.

```sql
CREATE TABLE sensors (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    type          VARCHAR(50)  NOT NULL,  -- temperature, humidity, pressure, vibration, current, voltage
    unit          VARCHAR(20)  NOT NULL,  -- °C, %, hPa, mm/s, A, V
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,       -- обратная совместимость
    group_id      INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    device_id     INTEGER REFERENCES devices(id) ON DELETE SET NULL,    -- новое поле
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
```

---

### Гипертаблица `sensor_data` ⭐

```sql
CREATE TABLE sensor_data (
    time       TIMESTAMPTZ NOT NULL,
    sensor_id  INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    value      DOUBLE PRECISION NOT NULL
);

SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);
CREATE INDEX idx_sensor_data_sensor_time ON sensor_data (sensor_id, time DESC);
```

TimescaleDB автоматически партиционирует данные по времени (чанки по 7 дней по умолчанию).

---

### Таблица `predictions`

```sql
CREATE TABLE predictions (
    id              SERIAL PRIMARY KEY,
    sensor_id       INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    prediction_time TIMESTAMPTZ NOT NULL,
    value           DOUBLE PRECISION NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Инициализация (`init.sql`)

Файл [`init.sql`](../init.sql) выполняется автоматически при первом запуске контейнера `db`. Создаёт все таблицы, индексы и гипертаблицу.

---

## TimescaleDB — ключевые концепции

### Что такое гипертаблица?

Гипертаблица — это обычная PostgreSQL-таблица, разбитая на **чанки** (chunks) по временному измерению. Каждый чанк — отдельная физическая таблица за определённый период.

### Преимущества

- Запросы к последним N точкам затрагивают только 1–2 чанка (не всю таблицу)
- Индексы меньше и быстрее (per-chunk)
- Возможность сжатия старых чанков (`compress_chunk`)
- Автоматическое удаление старых данных (`drop_chunks`)

### Пример: запрос последних 100 точек

```sql
-- Эффективно: TimescaleDB использует только последний чанк
SELECT time, value
FROM sensor_data
WHERE sensor_id = 1
ORDER BY time DESC
LIMIT 100;
```

---

## Полезные запросы

### Просмотр гипертаблиц
```sql
SELECT * FROM timescaledb_information.hypertables;
```

### Просмотр чанков
```sql
SELECT * FROM timescaledb_information.chunks
WHERE hypertable_name = 'sensor_data';
```

### Статистика по датчику
```sql
SELECT
    sensor_id,
    COUNT(*) AS total_points,
    MIN(value) AS min_val,
    MAX(value) AS max_val,
    AVG(value) AS avg_val,
    MIN(time) AS first_at,
    MAX(time) AS last_at
FROM sensor_data
WHERE sensor_id = 1
GROUP BY sensor_id;
```

### Агрегация по времени (time_bucket)
```sql
-- Среднее значение за каждые 5 минут
SELECT
    time_bucket('5 minutes', time) AS bucket,
    AVG(value) AS avg_value
FROM sensor_data
WHERE sensor_id = 1
  AND time > NOW() - INTERVAL '1 hour'
GROUP BY bucket
ORDER BY bucket DESC;
```

### Последние N измерений (скользящее окно)
```sql
-- Используется BlackBox для обучения модели (TRAIN_WINDOW_POINTS=50)
SELECT time, value
FROM sensor_data
WHERE sensor_id = 1
ORDER BY time DESC
LIMIT 50;
-- Результат разворачивается в Python: list(reversed(rows))
```

### Прогнозы для датчика
```sql
SELECT prediction_time, value
FROM predictions
WHERE sensor_id = 1
ORDER BY prediction_time ASC;
```

### Количество точек для проверки триггера авто-переобучения
```sql
SELECT COUNT(*) FROM sensor_data WHERE sensor_id = 1;
```

### Все датчики предприятия (через иерархию)
```sql
SELECT s.id, s.name, s.type, s.unit, d.name AS device_name, e.name AS enterprise_name
FROM sensors s
JOIN devices d ON s.device_id = d.id
JOIN enterprises e ON d.enterprise_id = e.id
WHERE e.id = 1;
```

### Пользователи с доступом к предприятию
```sql
SELECT u.username, u.email, uea.role, uea.granted_at
FROM user_enterprise_access uea
JOIN users u ON uea.user_id = u.id
WHERE uea.enterprise_id = 1
ORDER BY uea.role DESC;
```

---

## Healthcheck

```yaml
# docker-compose.yml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U iot_user -d iot_db"]
  interval: 10s
  timeout: 5s
  retries: 5
```

## Volumes

```yaml
volumes:
  postgres_data:    # данные PostgreSQL/TimescaleDB
  ml_models:        # модели scikit-learn (joblib)
```

### Резервное копирование
```bash
# Создать дамп
docker exec iot_postgres pg_dump -U iot_user iot_db > backup.sql

# Восстановить из дампа
docker exec -i iot_postgres psql -U iot_user iot_db < backup.sql
```
