/* ─── Defaults по типу датчика ─────────────────────────────── */
const SENSOR_DEFAULTS = {
  temperature: { min: -10,  max: 40   },
  humidity:    { min: 0,    max: 100  },
  pressure:    { min: 950,  max: 1050 },
  vibration:   { min: 0,    max: 20   },
};

function updateDefaults() {
  const type = document.getElementById('sensor_type').value;
  const cfg = SENSOR_DEFAULTS[type] || { min: 0, max: 100 };
  document.getElementById('min_value').value = cfg.min;
  document.getElementById('max_value').value = cfg.max;
}

/* ─── Форма запуска симуляции ──────────────────────────────── */
document.getElementById('sim-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type=submit]');
  btn.disabled = true;
  btn.textContent = '⏳ Запуск...';

  const payload = {
    sensor_id:   parseInt(document.getElementById('sensor_id').value),
    sensor_type: document.getElementById('sensor_type').value,
    min_value:   parseFloat(document.getElementById('min_value').value),
    max_value:   parseFloat(document.getElementById('max_value').value),
    interval:    parseInt(document.getElementById('interval').value),
    trend:       document.getElementById('trend').value,
    noise:       document.getElementById('noise').checked,
    outliers:    document.getElementById('outliers').checked,
  };

  try {
    const resp = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (resp.ok) {
      addLog('START', `Симуляция запущена для sensor_id=${data.sensor_id}`);
      loadSimulations();
      e.target.reset();
      updateDefaults();
    } else {
      addLog('ERR', `Ошибка: ${data.error || JSON.stringify(data)}`);
    }
  } catch (err) {
    addLog('ERR', `Сетевая ошибка: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '▶ Запустить симуляцию';
  }
});

/* ─── Остановка симуляции ──────────────────────────────────── */
async function stopSimulation(sensorId) {
  try {
    const resp = await fetch('/api/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sensor_id: sensorId }),
    });
    const data = await resp.json();
    addLog('STOP', `Симуляция остановлена: sensor_id=${sensorId}`);
    loadSimulations();
  } catch (err) {
    addLog('ERR', `Ошибка остановки: ${err.message}`);
  }
}

/* ─── Остановить все ───────────────────────────────────────── */
async function stopAll() {
  if (!confirm('Остановить все активные симуляции?')) return;
  try {
    const resp = await fetch('/api/stop_all', { method: 'POST' });
    const data = await resp.json();
    addLog('STOP', `Все симуляции остановлены (${data.count} шт.)`);
    loadSimulations();
  } catch (err) {
    addLog('ERR', `Ошибка: ${err.message}`);
  }
}

/* ─── Загрузка активных симуляций ──────────────────────────── */
async function loadSimulations() {
  try {
    const resp = await fetch('/api/simulations');
    const sims = await resp.json();

    const container = document.getElementById('sim-cards');
    const noMsg = document.getElementById('no-sims-msg');
    const badge = document.getElementById('active-count');

    badge.textContent = `${sims.length} активных`;

    if (sims.length === 0) {
      noMsg.style.display = 'block';
      container.innerHTML = '';
      return;
    }

    noMsg.style.display = 'none';
    container.innerHTML = sims.map(sim => `
      <div class="sim-card">
        <div class="sim-card-info">
          <div class="sim-card-title">
            📡 Датчик #${sim.sensor_id}
            <span style="font-weight:400; color: var(--text-dim); font-size:12px;">
              ${sim.sensor_type}
            </span>
          </div>
          <div class="sim-card-meta">
            Диапазон: ${sim.min_value}…${sim.max_value} ${sim.unit} &nbsp;|&nbsp;
            Интервал: ${sim.interval}с &nbsp;|&nbsp;
            Тренд: ${trendLabel(sim.trend)} &nbsp;|&nbsp;
            ${sim.noise ? '🌊 шум' : ''} ${sim.outliers ? '⚡ выбросы' : ''}
          </div>
        </div>
        <div class="sim-card-value">
          ${sim.current_value} <span style="font-size:12px; color:var(--text-dim)">${sim.unit}</span>
        </div>
        <button class="btn btn-danger btn-sm" onclick="stopSimulation(${sim.sensor_id})">
          ⏹
        </button>
      </div>
    `).join('');
  } catch (err) {
    console.error('loadSimulations error:', err);
  }
}

function trendLabel(trend) {
  return { none: '—', up: '↑ рост', down: '↓ падение' }[trend] || trend;
}

/* ─── Лог ──────────────────────────────────────────────────── */
const logEl = document.getElementById('log');
const logContainer = document.getElementById('log-container');

function addLog(level, message) {
  const ts = new Date().toLocaleTimeString('ru-RU');
  const line = document.createElement('span');
  line.className = `log-${level.toLowerCase()}`;
  line.textContent = `[${ts}] [${level}] ${message}\n`;
  logEl.appendChild(line);

  // Ограничиваем количество строк
  while (logEl.children.length > 300) {
    logEl.removeChild(logEl.firstChild);
  }

  // Авто-прокрутка
  if (document.getElementById('auto-scroll').checked) {
    logContainer.scrollTop = logContainer.scrollHeight;
  }
}

function clearLog() {
  logEl.innerHTML = '';
}

/* ─── SSE — логи в реальном времени ───────────────────────── */
function connectSSE() {
  const evtSource = new EventSource('/api/stream');

  evtSource.onmessage = (e) => {
    if (!e.data || e.data.trim() === '') return; // heartbeat

    const raw = e.data;
    // Определяем уровень по тексту
    let level = 'INFO';
    if (raw.includes('[OK]'))    level = 'OK';
    else if (raw.includes('[ERR]'))   level = 'ERR';
    else if (raw.includes('[START]')) level = 'START';
    else if (raw.includes('[STOP]'))  level = 'STOP';
    else if (raw.includes('[WARN]'))  level = 'WARN';

    const ts = new Date().toLocaleTimeString('ru-RU');
    const line = document.createElement('span');
    line.className = `log-${level.toLowerCase()}`;
    // Убираем дублирование временной метки из SSE
    line.textContent = raw + '\n';
    logEl.appendChild(line);

    while (logEl.children.length > 300) {
      logEl.removeChild(logEl.firstChild);
    }

    if (document.getElementById('auto-scroll').checked) {
      logContainer.scrollTop = logContainer.scrollHeight;
    }
  };

  evtSource.onerror = () => {
    addLog('WARN', 'SSE соединение прервано, переподключение через 3с...');
    evtSource.close();
    setTimeout(connectSSE, 3000);
  };
}

/* ─── Инициализация ────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  updateDefaults();
  loadSimulations();
  connectSSE();

  // Авто-обновление списка симуляций каждые 5 секунд
  setInterval(loadSimulations, 5000);

  addLog('INFO', 'Симулятор готов к работе');
});
