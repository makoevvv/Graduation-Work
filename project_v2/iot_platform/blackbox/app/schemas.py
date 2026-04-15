from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ForecastPoint(BaseModel):
    prediction_time: str
    value: float


class TrainResponse(BaseModel):
    sensor_id: int
    trained_at: str
    train_points: int
    forecast: List[ForecastPoint]
    anomaly_count: int
    anomaly_indices: List[int]
    model_info: Dict[str, Any]


class PredictResponse(BaseModel):
    sensor_id: int
    steps: int
    forecast: List[ForecastPoint]


class AnomalyDetail(BaseModel):
    index: int
    time: str
    value: float
    score: float


class AnomalyResponse(BaseModel):
    sensor_id: int
    analyzed_points: int
    anomaly_count: int
    anomalies: List[Dict[str, Any]]


class StatusResponse(BaseModel):
    sensor_id: int
    is_trained: bool
    trained_at: Optional[str] = None
    forecaster_info: Optional[Dict[str, Any]] = None
