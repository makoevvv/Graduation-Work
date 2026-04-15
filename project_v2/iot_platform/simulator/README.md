# Simulator — Генератор данных IoT-датчиков

Веб-приложение для симуляции работы IoT-датчиков. Генерирует реалистичные данные (температура, влажность, давление, вибрация) и отправляет их в Backend API. Предоставляет веб-интерфейс с логами в реальном времени через **Server-Sent Events (SSE)**.

## Назначение

Симулятор решает задачу тестирования платформы без реального оборудования:
- Генерирует данные с настраиваемым **трендом** (возрастающий, убывающий, стабильный)
- Добавляет **шум** и **выбросы** для реалистичности
- Позволяет запускать несколько симуляций одновременно для разных датчиков
- Отображает логи отправки данных в реальном времени через SSE
- **Провоцирует авто-переобучение** — при отправке 20+ точек Backend автоматически переобучает ML-модель

## Технологии

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| Flask | 2.3.3 | Веб-фреймворк |
| APScheduler | 3.10.4 | Планировщик задач (периодическая отправка) |
| requests | 2.31.0 | HTTP-запросы к Backend API |
| Werkzeug | 2.3.7 | WSGI-утилиты |
| python-dotenv | 1.0.0 | Загрузка переменных окружения |

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
| `BACKEND_URL` | `http://localhost:8000` | URL Backend API |
| `PORT` | `5001` | Порт Flask-сервера |

> **Примечание:** В Docker-контейнере `BACKEND_URL` задаётся как `http://backend:8000` через docker-compose.

## API Эндпоинты

### `GET /`
Веб-интерфейс симулятора (HTML-страница).

### `POST /api/start`
Запускает симуляцию для датчика.

**Тело запроса:**
```json
{
  "sensor_id": 1,
  "sensor_type": "temperature",
  "interval": 5,
  "trend": "up",
  "noise": true,
  "outliers": false,
  "min_value": -10,
  "max_value": 40
}
```

**Параметры:**
| Параметр | Тип | По умолчанию | Описание |
|---------|-----|-------------|---------|
| `sensor_id` | int | — (обязательный) | ID датчика в системе |
| `sensor_type` | str | `"temperature"` | Тип: `temperature`, `humidity`, `pressure`, `vibration` |
| `interval` | int | `5` | Интервал отправки в секундах (минимум 1) |
| `trend` | str | `"none"` | Тренд: `none`, `up`, `down` |
| `noise` | bool | `false` | Добавлять гауссов шум |
| `outliers` | bool | `false` | Добавлять случайные выбросы (5% вероятность) |
| `min_value` | float | из типа | Минимальное значение диапазона |
| `max_value` | float | из типа | Максимальное значение диапазона |

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
    "trend": "up",
    "noise": true,
    "outliers": false,
    "current_value": 23.456,
    "unit": "°C"
  }
]
```

### `GET /api/logs`
Возвращает последние 200 записей лога в формате JSON.

### `GET /api/stream`
**SSE-эндпоинт** для получения логов в реальном времени.

```
data: [17:55:17] [OK] Sensor 1 → 23.45 °C

data: [17:55:22] [ERR] Sensor 1: не удалось подключиться к бэкенду (http://backend:8000)
```

### `GET /api/sensor_types`
Возвращает список поддерживаемых типов датчиков с диапазонами значений.

## Генерация данных

### Алгоритм `generate_sensor_value()`

```python
def generate_sensor_value(sensor_type: str, base_value: float,
                           noise: bool, outliers: bool) -> float:
    value = base_value
    type_cfg = SENSOR_TYPES[sensor_type]
    range_ = type_cfg['max'] - type_cfg['min']

    # 1. Гауссов шум (5% от диапазона)
    if noise:
        value += random.gauss(0, range_ * 0.05)

    # 2. Случайные выбросы (5% вероятность, 20-50% от диапазона)
    if outliers and random.random() < 0.05:
        value += random.choice([-1, 1]) * range_ * random.uniform(0.2, 0.5)

    # 3. Ограничение диапазоном типа датчика
    value = max(type_cfg['min'], min(type_cfg['max'], value))
    return round(value, 3)
```

### Тренд

При каждой отправке базовое значение обновляется:
- `trend="up"`: `base += (max - min) * 0.01` (рост на 1% диапазона)
- `trend="down"`: `base -= (max - min) * 0.01` (падение на 1% диапазона)
- `trend="none"`: базовое значение не меняется

### Диапазоны значений по типам датчиков

| Тип | Мин | Макс | Единица |
|-----|-----|------|---------|
| `temperature` | -10 | 40 | °C |
| `humidity` | 0 | 100 | % |
| `pressure` | 950 | 1050 | hPa |
| `vibration` | 0 | 20 | mm/s |

## Планировщик задач (APScheduler)

Каждая симуляция — это задача в `BackgroundScheduler`:

```python
scheduler = BackgroundScheduler()

# Запуск симуляции
scheduler.add_job(
    func=send_data_job,
    trigger=IntervalTrigger(seconds=interval),
    args=[sensor_id],
    id=f"sensor_{sensor_id}",
    replace_existing=True,
)

# Остановка
scheduler.remove_job(f"sensor_{sensor_id}")
```

`send_data_job` при каждом вызове:
1. Генерирует значение через `generate_sensor_value()`
2. Обновляет базовое значение для тренда
3. Отправляет `POST /api/v1/data/` на Backend (эндпоинт публичный для записи данных)
4. Backend записывает данные и проверяет триггер авто-переобучения
5. Записывает результат в лог-очередь
6. Рассылает лог всем SSE-клиентам

## Server-Sent Events (SSE)

SSE позволяет серверу отправлять события клиенту без polling.

**Серверная часть (`/api/stream`):**
```python
def generate():
    # Отправляем последние 20 записей при подключении
    for entry in list(log_queue)[-20:]:
        yield f"data: [{entry['ts']}] [{entry['level']}] {entry['msg']}\n\n"

    # Ждём новых событий через queue.Queue
    while True:
        try:
            msg = client_queue.get(timeout=30)
            yield f"data: {msg}\n\n"
        except queue.Empty:
            yield "data: \n\n"  # heartbeat
```

**Клиентская часть (`script.js`):**
```javascript
const evtSource = new EventSource('/api/stream');
evtSource.onmessage = (event) => {
    appendLogEntry(event.data);  // Добавляем в DOM
};
```

## Веб-интерфейс

Тёмная тема с двумя панелями:

**Левая панель — форма запуска симуляции:**
- Поле ID датчика
- Выпадающий список типа датчика
- Поля: минимальное/максимальное значение, интервал
- Выпадающий список тренда (`none`, `up`, `down`)
- Чекбоксы: шум, выбросы
- Кнопки: Запустить / Остановить всё

**Правая панель — активные симуляции:**
- Карточки для каждой активной симуляции
- Кнопка остановки отдельной симуляции

**Нижняя панель — лог в реальном времени:**
- Цветовая кодировка: OK (зелёный), START/STOP (жёлтый), ERR (красный)
- Максимум 200 записей в очереди

## Пример использования

1. Открыть `http://localhost:5001`
2. В форме симулятора: ввести ID датчика, выбрать тип и параметры
3. Нажать **«Запустить»**
4. Наблюдать за логами в реальном времени
5. Перейти на Dashboard (`http://localhost:3000`) — данные появятся на графике через 5 секунд (авто-обновление)
6. После 20 отправленных точек — в логах backend появится `[AutoRetrain]`, модель переобучится автоматически

## Тестирование concept drift

Для демонстрации авто-переобучения при изменении паттерна данных:

1. Запустить симуляцию с `trend=none`, тип `temperature` (нормальная температура ~15°C)
2. Дождаться обучения модели (кнопка «Обучить модель» на Dashboard)
3. Остановить симуляцию
4. Запустить новую симуляцию с `trend=up` (температура начнёт расти)
5. После 20 точек — модель автоматически переобучится на новых данных
6. Прогнозы на Dashboard обновятся автоматически
