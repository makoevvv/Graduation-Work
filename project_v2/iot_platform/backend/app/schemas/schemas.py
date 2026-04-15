from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional, List

# =============================================================================
# USER
# =============================================================================

class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Token
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# =============================================================================
# ENTERPRISE
# =============================================================================

class EnterpriseBase(BaseModel):
    name: str
    description: Optional[str] = None
    address: Optional[str] = None

class EnterpriseCreate(EnterpriseBase):
    pass

class EnterpriseOut(EnterpriseBase):
    id: int
    owner_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# USER ENTERPRISE ACCESS
# =============================================================================

class UserEnterpriseAccessBase(BaseModel):
    user_id: int
    enterprise_id: int
    role: str = "viewer"  # owner / admin / viewer

class UserEnterpriseAccessCreate(UserEnterpriseAccessBase):
    pass

class UserEnterpriseAccessOut(UserEnterpriseAccessBase):
    id: int
    granted_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# DEVICE
# =============================================================================

class DeviceBase(BaseModel):
    name: str
    description: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None

class DeviceCreate(DeviceBase):
    enterprise_id: int

class DeviceOut(DeviceBase):
    id: int
    enterprise_id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# GROUP
# =============================================================================

class GroupBase(BaseModel):
    name: str
    description: Optional[str] = None

class GroupCreate(GroupBase):
    device_id: Optional[int] = None  # новое поле

class GroupOut(GroupBase):
    id: int
    user_id: Optional[int] = None
    device_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# SENSOR
# =============================================================================

class SensorBase(BaseModel):
    name: str
    type: str
    unit: str

class SensorCreate(SensorBase):
    group_id: Optional[int] = None
    device_id: Optional[int] = None  # новое поле

class SensorOut(SensorBase):
    id: int
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    device_id: Optional[int] = None
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# SENSOR DATA
# =============================================================================

class SensorDataIn(BaseModel):
    sensor_id: int
    value: float
    timestamp: Optional[datetime] = None

class SensorDataOut(BaseModel):
    time: datetime
    sensor_id: int
    value: float

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# PREDICTION
# =============================================================================

class PredictionOut(BaseModel):
    sensor_id: int
    prediction_time: datetime
    value: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# =============================================================================
# ВЛОЖЕННЫЕ СХЕМЫ (для детального вывода)
# =============================================================================

class SensorOutNested(SensorOut):
    """Датчик с информацией об устройстве."""
    pass

class DeviceOutWithSensors(DeviceOut):
    """Устройство со списком датчиков."""
    sensors: List[SensorOut] = []

    model_config = ConfigDict(from_attributes=True)

class EnterpriseOutWithDevices(EnterpriseOut):
    """Предприятие со списком устройств."""
    devices: List[DeviceOut] = []

    model_config = ConfigDict(from_attributes=True)
