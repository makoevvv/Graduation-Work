"""
ML Engine для предиктивной аналитики IoT-платформы.

Реализует два подхода:
1. Прогнозирование (Forecasting) — Linear Regression на признаках временного ряда
2. Детекция аномалий (Anomaly Detection) — Isolation Forest

Архитектура спроектирована с возможностью добавления новых моделей (LSTM и др.)
через паттерн Strategy / базовый класс BasePredictor.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict, Any
from abc import ABC, abstractmethod

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import os
from loguru import logger


# ─────────────────────────────────────────────
# Базовый класс — паттерн Strategy
# Позволяет в будущем добавить LSTM, ARIMA и др.
# ─────────────────────────────────────────────

class BasePredictor(ABC):
    """Абстрактный базовый класс для моделей прогнозирования."""

    @abstractmethod
    def fit(self, values: np.ndarray, timestamps: np.ndarray) -> None:
        """Обучить модель на исторических данных."""
        pass

    @abstractmethod
    def predict(self, steps: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Сделать прогноз на steps шагов вперёд.
        Возвращает (predicted_values, future_timestamps).
        """
        pass

    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        """Вернуть информацию о модели."""
        pass


# ─────────────────────────────────────────────
# Реализация 1: Linear Regression Forecaster
# ─────────────────────────────────────────────

class LinearRegressionForecaster(BasePredictor):
    """
    Прогнозирование временного ряда на основе Linear Regression.

    Признаки (features):
    - t  — порядковый номер точки (тренд)
    - t² — квадратичный тренд
    - скользящее среднее за 5 точек
    - скользящее среднее за 10 точек

    Это позволяет модели улавливать как линейный тренд,
    так и краткосрочные колебания.
    """

    def __init__(self):
        self.model = LinearRegression()
        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()
        self.is_fitted = False
        self.last_values: Optional[np.ndarray] = None
        self.last_timestamps: Optional[list] = None  # список datetime объектов
        self.avg_interval_seconds: float = 5.0  # средний интервал между точками

    @staticmethod
    def _normalize_timestamps(timestamps) -> list:
        """Нормализует временные метки к списку datetime объектов Python."""
        result = []
        for ts in timestamps:
            if isinstance(ts, datetime):
                result.append(ts)
            elif hasattr(ts, 'to_pydatetime'):
                # pandas Timestamp
                result.append(ts.to_pydatetime())
            elif isinstance(ts, np.datetime64):
                # numpy datetime64 → Python datetime
                ts_int = ts.astype('datetime64[ms]').astype(np.int64)
                result.append(datetime.fromtimestamp(ts_int / 1000.0, tz=timezone.utc))
            else:
                # строка или другой тип
                try:
                    result.append(datetime.fromisoformat(str(ts)))
                except Exception:
                    result.append(datetime.now(timezone.utc))
        return result

    def _build_features(self, values: np.ndarray) -> np.ndarray:
        """Строит матрицу признаков из массива значений."""
        n = len(values)
        t = np.arange(n, dtype=float)
        t2 = t ** 2

        # Скользящие средние (заполняем начало первым значением)
        ma5 = pd.Series(values).rolling(5, min_periods=1).mean().values
        ma10 = pd.Series(values).rolling(10, min_periods=1).mean().values

        return np.column_stack([t, t2, ma5, ma10])

    def fit(self, values: np.ndarray, timestamps: np.ndarray) -> None:
        """Обучает модель на исторических данных."""
        if len(values) < 2:
            raise ValueError("Недостаточно данных для обучения (минимум 2 точки)")

        self.last_values = values.copy()

        # Нормализуем временные метки к datetime Python
        self.last_timestamps = self._normalize_timestamps(timestamps)

        # Вычисляем средний интервал между измерениями
        if len(self.last_timestamps) > 1:
            intervals = []
            for i in range(1, len(self.last_timestamps)):
                delta = (self.last_timestamps[i] - self.last_timestamps[i-1]).total_seconds()
                intervals.append(delta)
            self.avg_interval_seconds = float(np.median(intervals))
            if self.avg_interval_seconds <= 0:
                self.avg_interval_seconds = 5.0

        X = self._build_features(values)
        y = values.reshape(-1, 1)

        X_scaled = self.scaler_X.fit_transform(X)
        y_scaled = self.scaler_y.fit_transform(y).ravel()

        self.model.fit(X_scaled, y_scaled)
        self.is_fitted = True

        logger.info(
            f"LinearRegressionForecaster обучен на {len(values)} точках, "
            f"интервал={self.avg_interval_seconds:.1f}с, "
            f"R²={self.model.score(X_scaled, y_scaled):.4f}"
        )

    def predict(self, steps: int) -> Tuple[np.ndarray, np.ndarray]:
        """Прогнозирует следующие steps значений."""
        if not self.is_fitted:
            raise RuntimeError("Модель не обучена. Вызовите fit() сначала.")

        n = len(self.last_values)
        future_values = []
        extended_values = self.last_values.copy().tolist()

        for i in range(steps):
            # Строим признаки для следующей точки
            arr = np.array(extended_values)
            X_future = self._build_features(arr)
            # Берём только последнюю строку (следующая точка)
            X_last = X_future[-1:].copy()
            # Обновляем t и t² для будущей точки
            t_next = float(n + i)
            X_last[0, 0] = t_next
            X_last[0, 1] = t_next ** 2

            X_scaled = self.scaler_X.transform(X_last)
            y_scaled = self.model.predict(X_scaled)
            y_pred = self.scaler_y.inverse_transform(y_scaled.reshape(-1, 1)).ravel()[0]

            future_values.append(y_pred)
            extended_values.append(y_pred)

        # Генерируем будущие временные метки как список datetime объектов
        last_ts = self.last_timestamps[-1]
        if not isinstance(last_ts, datetime):
            last_ts = datetime.now(timezone.utc)
        interval = timedelta(seconds=self.avg_interval_seconds)
        future_timestamps = [last_ts + interval * (i + 1) for i in range(steps)]

        return np.array(future_values), future_timestamps

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "type": "LinearRegressionForecaster",
            "is_fitted": self.is_fitted,
            "train_points": len(self.last_values) if self.last_values is not None else 0,
            "avg_interval_seconds": self.avg_interval_seconds,
            "coefficients": self.model.coef_.tolist() if self.is_fitted else None,
        }


# ─────────────────────────────────────────────
# Реализация 2: Isolation Forest Anomaly Detector
# ─────────────────────────────────────────────

class IsolationForestDetector:
    """
    Детектор аномалий на основе Isolation Forest.

    Isolation Forest — ансамблевый метод, который изолирует аномальные
    точки, строя случайные деревья. Аномалии изолируются быстрее,
    чем нормальные точки.

    Признаки:
    - само значение
    - отклонение от скользящего среднего
    - z-score (стандартизованное отклонение)
    """

    def __init__(self, contamination: float = 0.05):
        """
        contamination — ожидаемая доля аномалий в данных (0.0 - 0.5).
        По умолчанию 5%.
        """
        self.contamination = contamination
        self.model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
        self.is_fitted = False

    def _build_features(self, values: np.ndarray) -> np.ndarray:
        """Строит признаки для детекции аномалий."""
        series = pd.Series(values)
        ma = series.rolling(5, min_periods=1).mean().values
        deviation = values - ma

        # Z-score
        mean = np.mean(values)
        std = np.std(values) if np.std(values) > 0 else 1.0
        z_score = (values - mean) / std

        return np.column_stack([values, deviation, z_score])

    def fit(self, values: np.ndarray) -> None:
        """Обучает детектор аномалий."""
        if len(values) < 10:
            raise ValueError("Недостаточно данных для обучения (минимум 10 точек)")

        X = self._build_features(values)
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_fitted = True

        logger.info(
            f"IsolationForestDetector обучен на {len(values)} точках, "
            f"contamination={self.contamination}"
        )

    def predict(self, values: np.ndarray) -> np.ndarray:
        """
        Определяет аномалии в массиве значений.
        Возвращает булев массив: True = аномалия.
        """
        if not self.is_fitted:
            raise RuntimeError("Детектор не обучен. Вызовите fit() сначала.")

        X = self._build_features(values)
        X_scaled = self.scaler.transform(X)
        # IsolationForest: -1 = аномалия, 1 = норма
        labels = self.model.predict(X_scaled)
        return labels == -1

    def get_anomaly_scores(self, values: np.ndarray) -> np.ndarray:
        """
        Возвращает оценку аномальности для каждой точки.
        Чем ниже score, тем более аномальна точка.
        """
        if not self.is_fitted:
            raise RuntimeError("Детектор не обучен.")

        X = self._build_features(values)
        X_scaled = self.scaler.transform(X)
        return self.model.score_samples(X_scaled)


# ─────────────────────────────────────────────
# Менеджер моделей — хранит обученные модели в памяти
# ─────────────────────────────────────────────

class ModelManager:
    """
    Управляет жизненным циклом ML-моделей для каждого датчика.
    Хранит модели в памяти (словарь sensor_id -> модели).
    Поддерживает сохранение/загрузку через joblib.
    """

    def __init__(self, models_dir: str = "/tmp/iot_models"):
        self.models_dir = models_dir
        os.makedirs(models_dir, exist_ok=True)
        # sensor_id -> {"forecaster": ..., "detector": ..., "trained_at": ...}
        self._models: Dict[int, Dict[str, Any]] = {}

    def train(
        self,
        sensor_id: int,
        values: np.ndarray,
        timestamps: np.ndarray,
        contamination: float = 0.05,
        forecast_steps: int = 10,
    ) -> Dict[str, Any]:
        """
        Обучает обе модели для датчика и возвращает результаты.
        """
        logger.info(f"Начало обучения моделей для sensor_id={sensor_id}, точек={len(values)}")

        # 1. Прогнозирование
        forecaster = LinearRegressionForecaster()
        forecaster.fit(values, timestamps)
        predicted_values, future_timestamps = forecaster.predict(forecast_steps)

        # 2. Детекция аномалий
        detector = IsolationForestDetector(contamination=contamination)
        detector.fit(values)
        anomaly_mask = detector.predict(values)
        anomaly_scores = detector.get_anomaly_scores(values)

        # Сохраняем модели
        trained_at = datetime.now(timezone.utc)
        self._models[sensor_id] = {
            "forecaster": forecaster,
            "detector": detector,
            "trained_at": trained_at,
        }

        # Сохраняем на диск
        self._save_to_disk(sensor_id)

        result = {
            "sensor_id": sensor_id,
            "trained_at": trained_at.isoformat(),
            "train_points": len(values),
            "forecast": [
                {
                    "prediction_time": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                    "value": float(val),
                }
                for val, ts in zip(predicted_values, future_timestamps)
            ],
            "anomalies": {
                "count": int(anomaly_mask.sum()),
                "indices": anomaly_mask.nonzero()[0].tolist(),
                "scores": anomaly_scores.tolist(),
            },
            "model_info": {
                "forecaster": forecaster.get_model_info(),
                "detector": {
                    "type": "IsolationForestDetector",
                    "contamination": contamination,
                    "is_fitted": detector.is_fitted,
                }
            }
        }

        logger.info(
            f"Обучение завершено для sensor_id={sensor_id}: "
            f"прогноз {forecast_steps} точек, аномалий={int(anomaly_mask.sum())}"
        )
        return result

    def get_forecast(self, sensor_id: int, steps: int) -> Optional[List[Dict]]:
        """Возвращает прогноз для уже обученной модели."""
        if sensor_id not in self._models:
            # Пробуем загрузить с диска
            if not self._load_from_disk(sensor_id):
                return None

        forecaster: LinearRegressionForecaster = self._models[sensor_id]["forecaster"]
        predicted_values, future_timestamps = forecaster.predict(steps)

        return [
            {
                "prediction_time": ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
                "value": float(val),
            }
            for val, ts in zip(predicted_values, future_timestamps)
        ]

    def detect_anomalies(self, sensor_id: int, values: np.ndarray) -> Optional[Dict]:
        """Детектирует аномалии в новых данных."""
        if sensor_id not in self._models:
            if not self._load_from_disk(sensor_id):
                return None

        detector: IsolationForestDetector = self._models[sensor_id]["detector"]
        anomaly_mask = detector.predict(values)
        scores = detector.get_anomaly_scores(values)

        return {
            "anomaly_mask": anomaly_mask.tolist(),
            "scores": scores.tolist(),
            "count": int(anomaly_mask.sum()),
        }

    def get_status(self, sensor_id: int) -> Dict[str, Any]:
        """Возвращает статус модели для датчика."""
        if sensor_id in self._models:
            m = self._models[sensor_id]
            return {
                "sensor_id": sensor_id,
                "is_trained": True,
                "trained_at": m["trained_at"].isoformat(),
                "forecaster_info": m["forecaster"].get_model_info(),
            }
        # Проверяем диск
        path = self._model_path(sensor_id)
        if os.path.exists(path):
            return {
                "sensor_id": sensor_id,
                "is_trained": True,
                "trained_at": "unknown (loaded from disk)",
                "forecaster_info": None,
            }
        return {"sensor_id": sensor_id, "is_trained": False}

    def _model_path(self, sensor_id: int) -> str:
        return os.path.join(self.models_dir, f"sensor_{sensor_id}.joblib")

    def _save_to_disk(self, sensor_id: int) -> None:
        try:
            path = self._model_path(sensor_id)
            joblib.dump(self._models[sensor_id], path)
            logger.debug(f"Модель sensor_id={sensor_id} сохранена: {path}")
        except Exception as e:
            logger.warning(f"Не удалось сохранить модель на диск: {e}")

    def _load_from_disk(self, sensor_id: int) -> bool:
        try:
            path = self._model_path(sensor_id)
            if os.path.exists(path):
                self._models[sensor_id] = joblib.load(path)
                logger.info(f"Модель sensor_id={sensor_id} загружена с диска")
                return True
        except Exception as e:
            logger.warning(f"Не удалось загрузить модель с диска: {e}")
        return False


# Глобальный экземпляр менеджера моделей
model_manager = ModelManager()
