# Simulator — Генератор данных IoT-датчиков

Веб-приложение для симуляции работы IoT-датчиков. Генерирует реалистичные данные (температура, влажность, давление и др.) и отправляет их в Backend API. Предоставляет веб-интерфейс с логами в реальном времени через **Server-Sent Events (SSE)**.

## Назначение

Симулятор решает задачу тестирования платформы без реального оборудования:
- Генерирует данные с настраиваемым **трендом** (возрастающий, убывающий, стабильный, случайный)
- Добавляет **шум** и **выбросы** для реалистичности
- Позволяет запускать несколько симуляций одновременно для разных датчиков
- Отображает логи отправки данных в реальном времени через SSE
- **Провоцирует авто-переобучение** — при отправке 20+ точек Backend автоматически переобучает ML-модель

## Технологии

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| Flask | 3.0 | Веб-фреймворк |
| APScheduler | 3.10 | Планировщик задач (периодическая отправка) |
| requests | 2.31 | HTTP-запросы к Backend API |
| Werkzeug | 2.3 | WSGI-утилиты |

## Структура проекта

```
simulator/
├── app.py                  # Flask-приложение, все маршруты и логика
├── templates/
│   └── index.html          # Веб-интерфейс симулятора
├── static/
│   ├── style.css           # Тёмная тема, стили
│   └── script.js           # JavaScript: SSE-клиент, управление симуляциями
├── Dockerfile
└── requirements.txt
```

## Запуск

### Через Docker Compose (рекомендуется)
```bash
cd project_v2/iot_platform
docker compose up simulator
```

### Локально
```bash
cd simulator
pip install -r requirements.txt
python app.py
# Открыть http://localhost:5001
```

## Переменные окружения

| Переменная | Значение по умолчанию | Описание |
|-----------|----------------------|---------|
| `BACKEND_URL` | `http://backend:8000` | URL Backend API |
| `PORT` | `5001` | Порт Flask-сервера |

## API Эндпоинты

### `GET /`
Веб-интерфейс симулятора (HTML-страница).

### `POST /api/start`
Запускает симуляцию для датчика.

**Тело запроса:**
```json
{
  "sensor_id": 1,
  "token": "eyJ...",
  "sensor_type": "temperature",
  "base_value": 22.0,
  "noise_level": 0.5,
  "interval": 5,
  "trend": "increasing",
  "add_outliers": false,
  "add_seasonality": true
}
```

**Параметры:**
| Параметр | Тип | Описание |
|---------|-----|---------|
| `sensor_id` | int | ID датчика в системе |
| `token` | str | JWT-токен для авторизации |
| `sensor_type` | str | Тип: temperature, humidity, pressure, voltage, current, custom |
| `base_value` | float | Базовое значение (начальная точка) |
| `noise_level` | float | Уровень шума (0.0 — 5.0) |
| `interval` | int | Интервал отправки в секундах |
| `trend` | str | Тренд: stable, increasing, decreasing, random |
| `add_outliers` | bool | Добавлять случайные выбросы |
| `add_seasonality` | bool | Добавлять сезонность (синусоида) |

### `POST /api/stop`
Останавливает симуляцию для датчика.
```json
{"sensor_id": 1}
```

### `POST /api/stop_all`
Останавливает все активные симуляции.

### `GET /api/simulations`
Возвращает список активных симуляций.
```json
[
  {
    "sensor_id": 1,
    "sensor_type": "temperature",
    "interval": 5,
    "trend": "increasing",
    "running": true
  }
]
```

### `GET /api/logs`
Возвращает последние 100 записей лога в формате JSON.

### `GET /api/stream`
**SSE-эндпоинт** для получения логов в реальном времени.

```
data: {"level": "INFO", "message": "Датчик 1: отправлено 23.45°C", "timestamp": "17:55:17"}

data: {"level": "ERROR", "message": "Ошибка подключения к API", "timestamp": "17:55:22"}
```

### `GET /api/sensor_types`
Возвращает список поддерживаемых типов датчиков с диапазонами значений.

## Генерация данных

### Алгоритм `generate_sensor_value()`

```python
def generate_sensor_value(sensor_type, base_value, noise_level,
                           trend, step, add_outliers, add_seasonality):
    # 1. Базовое значение из диапазона типа датчика
    value = base_value

    # 2. Тренд
    if trend == "increasing":   value += step * 0.1
    elif trend == "decreasing": value -= step * 0.1
    elif trend == "random":     value += random.uniform(-1, 1)

    # 3. Шум (нормальное распределение)
    value += random.gauss(0, noise_level)

    # 4. Сезонность (синусоида с периодом 60 шагов)
    if add_seasonality:
        value += 2.0 * math.sin(2 * math.pi * step / 60)

    # 5. Случайные выбросы (5% вероятность, ±3σ)
    if add_outliers and random.random() < 0.05:
        value += random.choice([-1, 1]) * random.uniform(3, 6) * noise_level

    # 6. Ограничение диапазоном типа датчика
    value = max(min_val, min(max_val, value))
    return round(value, 3)
```

### Диапазоны значений по типам датчиков

| Тип | Мин | Макс | Единица |
|-----|-----|------|---------|
| temperature | -40 | 85 | °C |
| humidity | 0 | 100 | % |
| pressure | 900 | 1100 | hPa |
| voltage | 0 | 250 | V |
| current | 0 | 100 | A |
| custom | -1000 | 1000 | — |

## Планировщик задач (APScheduler)

Каждая симуляция — это задача в `BackgroundScheduler`:

```python
scheduler = BackgroundScheduler()

# Запуск симуляции
scheduler.add_job(
    func=send_data_job,
    trigger='interval',
    seconds=interval,
    id=f"sim_{sensor_id}",
    args=[sensor_id]
)

# Остановка
scheduler.remove_job(f"sim_{sensor_id}")
```

`send_data_job` при каждом вызове:
1. Генерирует значение через `generate_sensor_value()`
2. Отправляет `POST /api/v1/data/` на Backend (без токена — эндпоинт публичный)
3. Backend записывает данные и проверяет триггер авто-переобучения
4. Записывает результат в лог-очередь
5. Рассылает лог всем SSE-клиентам

## Server-Sent Events (SSE)

SSE позволяет серверу отправлять события клиенту без polling.

**Серверная часть (`/api/stream`):**
```python
def generate():
    # Отправляем последние 20 записей при подключении
    for entry in list(log_queue)[-20:]:
        yield f"data: {json.dumps(entry)}\n\n"

    # Ждём новых событий через threading.Event
    while True:
        sse_event.wait(timeout=30)
        # Отправляем новые записи
        for entry in new_entries:
            yield f"data: {json.dumps(entry)}\n\n"
```

**Клиентская часть (`script.js`):**
```javascript
const evtSource = new EventSource('/api/stream');
evtSource.onmessage = (event) => {
    const log = JSON.parse(event.data);
    appendLogEntry(log);  // Добавляем в DOM
};
```

## Веб-интерфейс

Тёмная тема с двумя панелями:

**Левая панель — форма запуска симуляции:**
- Поле ID датчика
- Выпадающий список типа датчика (с авто-заполнением базового значения)
- Поля: базовое значение, уровень шума, интервал
- Выпадающий список тренда
- Чекбоксы: выбросы, сезонность
- Кнопки: Запустить / Остановить всё

**Правая панель — активные симуляции:**
- Карточки для каждой активной симуляции
- Кнопка остановки отдельной симуляции

**Нижняя панель — лог в реальном времени:**
- Цветовая кодировка: INFO (зелёный), WARNING (жёлтый), ERROR (красный)
- Чекбокс авто-прокрутки
- Кнопка очистки лога
- Максимум 200 записей в DOM

## Пример использования

1. Открыть `http://localhost:5001`
2. Войти в основное приложение на `http://localhost:3000` и скопировать JWT-токен из DevTools → Application → localStorage
3. В форме симулятора: ввести ID датчика, вставить токен, выбрать тип и параметры
4. Нажать **«Запустить»**
5. Наблюдать за логами в реальном времени
6. Перейти на Dashboard — данные появятся на графике через 5 секунд (авто-обновление)
7. После 20 отправленных точек — в логах backend появится `[AutoRetrain]`, модель переобучится автоматически

## Тестирование concept drift

Для демонстрации авто-переобучения при изменении паттерна данных:

1. Запустить симуляцию с `trend=stable`, `base_value=22` (нормальная температура)
2. Дождаться обучения модели (кнопка «Обучить модель» на Dashboard)
3. Остановить симуляцию
4. Запустить новую симуляцию с `trend=increasing`, `base_value=80` (аномальная температура)
5. После 20 точек — модель автоматически переобучится на новых данных
6. Прогнозы на Dashboard обновятся автоматически
