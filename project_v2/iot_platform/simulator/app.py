"""
IoT Sensor Simulator — микросервис для генерации тестовых данных датчиков.

Возможности:
- Генерация данных с трендом (рост/падение/стабильно)
- Добавление гауссова шума
- Генерация случайных выбросов (аномалий)
- Управление через веб-интерфейс
- Логи в реальном времени через SSE (Server-Sent Events)
"""

import os
import time
import queue
import threading
import random
from datetime import datetime, timezone
from collections import deque

import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)

# Конфигурация
BACKEND_URL = os.getenv('BACKEND_URL', 'http://localhost:8000')
SENSOR_DATA_ENDPOINT = f"{BACKEND_URL}/api/v1/data/"

# Хранилище активных симуляций: sensor_id -> параметры
active_simulations = {}
scheduler = BackgroundScheduler()
scheduler.start()

# Очередь логов для SSE (последние 200 записей)
log_queue = deque(maxlen=200)
sse_clients = []  # список очередей для SSE-клиентов
sse_lock = threading.Lock()

# Типы датчиков и их диапазоны
SENSOR_TYPES = {
    'temperature': {'unit': '°C',   'min': -10,  'max': 40},
    'humidity':    {'unit': '%',    'min': 0,    'max': 100},
    'pressure':    {'unit': 'hPa',  'min': 950,  'max': 1050},
    'vibration':   {'unit': 'mm/s', 'min': 0,    'max': 20},
}


# ─────────────────────────────────────────────
# Логирование с рассылкой SSE-клиентам
# ─────────────────────────────────────────────

def push_log(level: str, message: str):
    """Добавляет запись в лог и рассылает SSE-клиентам."""
    ts = datetime.now().strftime('%H:%M:%S')
    entry = {"ts": ts, "level": level, "msg": message}
    log_queue.append(entry)

    data = f"[{ts}] [{level}] {message}"
    with sse_lock:
        dead = []
        for q in sse_clients:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            sse_clients.remove(q)


# ─────────────────────────────────────────────
# Генерация значений датчика
# ─────────────────────────────────────────────

def generate_sensor_value(sensor_type: str, base_value: float,
                           noise: bool, outliers: bool) -> float:
    """Генерирует значение датчика с шумом и выбросами."""
    value = base_value
    type_cfg = SENSOR_TYPES[sensor_type]
    range_ = type_cfg['max'] - type_cfg['min']

    if noise:
        value += random.gauss(0, range_ * 0.05)

    if outliers and random.random() < 0.05:
        value += random.choice([-1, 1]) * range_ * random.uniform(0.2, 0.5)

    # Ограничиваем диапазоном
    value = max(type_cfg['min'], min(type_cfg['max'], value))
    return round(value, 3)


# ─────────────────────────────────────────────
# Задача планировщика — отправка данных
# ─────────────────────────────────────────────

def send_data_job(sensor_id: int):
    """Вызывается планировщиком: генерирует и отправляет данные датчика."""
    if sensor_id not in active_simulations:
        return
    sim = active_simulations[sensor_id]
    if not sim['active']:
        return

    sensor_type = sim['sensor_type']
    value = generate_sensor_value(
        sensor_type,
        sim['current_base'],
        sim['noise'],
        sim['outliers'],
    )

    # Обновляем базу для тренда
    if sim['trend'] == 'up':
        sim['current_base'] = min(
            SENSOR_TYPES[sensor_type]['max'],
            sim['current_base'] + sim['trend_step']
        )
    elif sim['trend'] == 'down':
        sim['current_base'] = max(
            SENSOR_TYPES[sensor_type]['min'],
            sim['current_base'] - sim['trend_step']
        )

    # Отправляем в бэкенд
    payload = {
        'sensor_id': sensor_id,
        'value': value,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    try:
        resp = requests.post(SENSOR_DATA_ENDPOINT, json=payload, timeout=5)
        if resp.status_code == 200:
            push_log('OK', f"Sensor {sensor_id} → {value} {SENSOR_TYPES[sensor_type]['unit']}")
        else:
            push_log('ERR', f"Sensor {sensor_id}: backend error {resp.status_code}: {resp.text[:80]}")
    except requests.exceptions.ConnectionError:
        push_log('ERR', f"Sensor {sensor_id}: не удалось подключиться к бэкенду ({BACKEND_URL})")
    except Exception as e:
        push_log('ERR', f"Sensor {sensor_id}: {str(e)[:100]}")


# ─────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html', sensor_types=list(SENSOR_TYPES.keys()))


@app.route('/api/simulations', methods=['GET'])
def get_simulations():
    """Список активных симуляций."""
    return jsonify([
        {
            'sensor_id': sid,
            'sensor_type': sim['sensor_type'],
            'interval': sim['interval'],
            'trend': sim['trend'],
            'noise': sim['noise'],
            'outliers': sim['outliers'],
            'current_value': round(sim['current_base'], 3),
            'unit': SENSOR_TYPES[sim['sensor_type']]['unit'],
        }
        for sid, sim in active_simulations.items()
        if sim['active']
    ])


@app.route('/api/start', methods=['POST'])
def start_simulation():
    """Запускает симуляцию для датчика."""
    data = request.json or {}
    sensor_id = data.get('sensor_id')
    if not sensor_id:
        return jsonify({'error': 'sensor_id is required'}), 400

    try:
        sensor_id = int(sensor_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'sensor_id must be integer'}), 400

    sensor_type = data.get('sensor_type', 'temperature')
    if sensor_type not in SENSOR_TYPES:
        return jsonify({'error': f'Invalid sensor type. Valid: {list(SENSOR_TYPES.keys())}'}), 400

    type_cfg = SENSOR_TYPES[sensor_type]
    interval = max(1, int(data.get('interval', 5)))
    min_val = float(data.get('min_value', type_cfg['min']))
    max_val = float(data.get('max_value', type_cfg['max']))
    trend = data.get('trend', 'none')
    noise = bool(data.get('noise', False))
    outliers = bool(data.get('outliers', False))

    # Останавливаем предыдущую симуляцию если есть
    if sensor_id in active_simulations:
        _stop_simulation(sensor_id)

    active_simulations[sensor_id] = {
        'sensor_type': sensor_type,
        'interval': interval,
        'trend': trend,
        'trend_step': (max_val - min_val) * 0.01,
        'noise': noise,
        'outliers': outliers,
        'min_value': min_val,
        'max_value': max_val,
        'current_base': (min_val + max_val) / 2,
        'active': True,
    }

    scheduler.add_job(
        func=send_data_job,
        trigger=IntervalTrigger(seconds=interval),
        args=[sensor_id],
        id=f"sensor_{sensor_id}",
        replace_existing=True,
    )

    push_log('START', f"Симуляция запущена: sensor_id={sensor_id}, type={sensor_type}, interval={interval}s, trend={trend}")
    return jsonify({'status': 'started', 'sensor_id': sensor_id})


@app.route('/api/stop', methods=['POST'])
def stop_simulation():
    """Останавливает симуляцию для датчика."""
    data = request.json or {}
    sensor_id = data.get('sensor_id')
    if not sensor_id:
        return jsonify({'error': 'sensor_id is required'}), 400

    try:
        sensor_id = int(sensor_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'sensor_id must be integer'}), 400

    _stop_simulation(sensor_id)
    push_log('STOP', f"Симуляция остановлена: sensor_id={sensor_id}")
    return jsonify({'status': 'stopped', 'sensor_id': sensor_id})


@app.route('/api/stop_all', methods=['POST'])
def stop_all():
    """Останавливает все активные симуляции."""
    ids = list(active_simulations.keys())
    for sid in ids:
        _stop_simulation(sid)
    push_log('STOP', f"Все симуляции остановлены ({len(ids)} шт.)")
    return jsonify({'status': 'all_stopped', 'count': len(ids)})


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Возвращает последние логи."""
    return jsonify(list(log_queue))


@app.route('/api/stream')
def stream():
    """SSE endpoint для логов в реальном времени."""
    client_queue = queue.Queue(maxsize=100)
    with sse_lock:
        sse_clients.append(client_queue)

    def generate():
        # Сначала отправляем последние 20 записей из истории
        for entry in list(log_queue)[-20:]:
            yield f"data: [{entry['ts']}] [{entry['level']}] {entry['msg']}\n\n"

        try:
            while True:
                try:
                    msg = client_queue.get(timeout=30)
                    yield f"data: {msg}\n\n"
                except queue.Empty:
                    # Heartbeat чтобы соединение не закрылось
                    yield "data: \n\n"
        except GeneratorExit:
            with sse_lock:
                if client_queue in sse_clients:
                    sse_clients.remove(client_queue)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
        }
    )


@app.route('/api/sensor_types', methods=['GET'])
def get_sensor_types():
    """Возвращает доступные типы датчиков."""
    return jsonify(SENSOR_TYPES)


def _stop_simulation(sensor_id: int):
    """Внутренняя функция остановки симуляции."""
    if sensor_id in active_simulations:
        active_simulations[sensor_id]['active'] = False
    try:
        scheduler.remove_job(f"sensor_{sensor_id}")
    except Exception:
        pass


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    push_log('INFO', f"Симулятор запущен на порту {port}, бэкенд: {BACKEND_URL}")
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
