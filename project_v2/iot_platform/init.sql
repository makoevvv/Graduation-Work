-- Включаем расширение TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- =============================================================================
-- ПОЛЬЗОВАТЕЛИ
-- =============================================================================

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- ПРЕДПРИЯТИЯ (enterprises)
-- Верхний уровень иерархии. Предприятие — завод, объект, здание и т.п.
-- Один пользователь может иметь доступ к нескольким предприятиям (через access-таблицу).
-- =============================================================================

CREATE TABLE IF NOT EXISTS enterprises (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    address TEXT,                          -- физический адрес объекта
    owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,  -- создатель
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- M2M: доступ пользователей к предприятиям с ролями
-- role: 'owner' | 'admin' | 'viewer'
CREATE TABLE IF NOT EXISTS user_enterprise_access (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- owner / admin / viewer
    granted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, enterprise_id)
);

CREATE INDEX IF NOT EXISTS idx_uea_user ON user_enterprise_access (user_id);
CREATE INDEX IF NOT EXISTS idx_uea_enterprise ON user_enterprise_access (enterprise_id);

-- =============================================================================
-- УСТРОЙСТВА (devices)
-- Второй уровень: физическое оборудование внутри предприятия.
-- Например: насос №3, конвейер А, HVAC-блок 2.
-- =============================================================================

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    description TEXT,
    model VARCHAR(100),                    -- модель оборудования
    serial_number VARCHAR(100),            -- серийный номер
    enterprise_id INTEGER NOT NULL REFERENCES enterprises(id) ON DELETE CASCADE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_devices_enterprise ON devices (enterprise_id);

-- =============================================================================
-- ГРУППЫ (groups)
-- Логические папки/категории датчиков внутри устройства или предприятия.
-- Обратная совместимость: group может быть без device_id (старое поведение).
-- =============================================================================

CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    -- Старое поле: владелец-пользователь (для обратной совместимости)
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    -- Новое поле: привязка к устройству (опционально)
    device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_groups_device ON groups (device_id);

-- =============================================================================
-- ДАТЧИКИ (sensors)
-- Третий уровень: конкретный датчик на устройстве.
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,   -- temperature, humidity, pressure, vibration, current, voltage
    unit VARCHAR(20) NOT NULL,   -- °C, %, hPa, mm/s, A, V
    -- Старое поле: прямой владелец (обратная совместимость)
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    -- Старое поле: группа (обратная совместимость)
    group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
    -- Новое поле: устройство (предпочтительный способ привязки)
    device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sensors_device ON sensors (device_id);
CREATE INDEX IF NOT EXISTS idx_sensors_group ON sensors (group_id);

-- =============================================================================
-- ДАННЫЕ С ДАТЧИКОВ (гипертаблица TimescaleDB)
-- =============================================================================

CREATE TABLE IF NOT EXISTS sensor_data (
    time TIMESTAMPTZ NOT NULL,
    sensor_id INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    value DOUBLE PRECISION NOT NULL
);

-- Преобразование в гипертаблицу TimescaleDB
SELECT create_hypertable('sensor_data', 'time', if_not_exists => TRUE);

-- Индекс для ускорения запросов по sensor_id и времени
CREATE INDEX IF NOT EXISTS idx_sensor_data_sensor_time ON sensor_data (sensor_id, time DESC);

-- =============================================================================
-- ПРОГНОЗЫ ML
-- =============================================================================

CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    sensor_id INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    prediction_time TIMESTAMPTZ NOT NULL,  -- время, на которое сделан прогноз
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()   -- время создания прогноза
);

CREATE INDEX IF NOT EXISTS idx_predictions_sensor_time ON predictions (sensor_id, prediction_time DESC);

-- =============================================================================
-- КОММЕНТАРИИ К СХЕМЕ
-- =============================================================================
-- Иерархия объектов:
--   Enterprise (предприятие)
--     └── Device (устройство/оборудование)
--           ├── Group (логическая группа датчиков, опционально)
--           └── Sensor (датчик)
--                 ├── SensorData (гипертаблица измерений)
--                 └── Predictions (прогнозы ML)
--
-- Доступ пользователей:
--   User ←→ Enterprise  через user_enterprise_access (role: owner/admin/viewer)
--   Один пользователь может иметь доступ к N предприятиям с разными ролями.
--   Один пользователь может быть owner одного предприятия и viewer другого.
--
-- Обратная совместимость:
--   sensors.user_id и sensors.group_id сохранены для работы существующего кода.
--   groups.user_id сохранён для существующего кода управления группами.
--   Новый код должен использовать device_id и enterprise_id.
