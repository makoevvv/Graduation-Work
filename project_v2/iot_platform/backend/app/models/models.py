from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, func, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship
from ..core.database import Base


# =============================================================================
# ПОЛЬЗОВАТЕЛИ
# =============================================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Старые связи (обратная совместимость)
    groups = relationship("Group", back_populates="owner", cascade="all, delete-orphan")
    sensors = relationship("Sensor", back_populates="owner")

    # Новые связи
    enterprise_access = relationship("UserEnterpriseAccess", back_populates="user", cascade="all, delete-orphan")
    owned_enterprises = relationship("Enterprise", back_populates="owner", foreign_keys="Enterprise.owner_id")


# =============================================================================
# ПРЕДПРИЯТИЯ
# =============================================================================

class Enterprise(Base):
    """Верхний уровень иерархии: завод, объект, здание."""
    __tablename__ = "enterprises"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="owned_enterprises", foreign_keys=[owner_id])
    user_access = relationship("UserEnterpriseAccess", back_populates="enterprise", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="enterprise", cascade="all, delete-orphan")


class UserEnterpriseAccess(Base):
    """M2M: доступ пользователей к предприятиям с ролями (owner/admin/viewer)."""
    __tablename__ = "user_enterprise_access"
    __table_args__ = (UniqueConstraint("user_id", "enterprise_id", name="uq_user_enterprise"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    enterprise_id = Column(Integer, ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="viewer")  # owner / admin / viewer
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="enterprise_access")
    enterprise = relationship("Enterprise", back_populates="user_access")


# =============================================================================
# УСТРОЙСТВА
# =============================================================================

class Device(Base):
    """Второй уровень: физическое оборудование внутри предприятия.
    Например: насос №3, конвейер А, HVAC-блок 2."""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    model = Column(String(100), nullable=True)          # модель оборудования
    serial_number = Column(String(100), nullable=True)  # серийный номер
    enterprise_id = Column(Integer, ForeignKey("enterprises.id", ondelete="CASCADE"), nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    enterprise = relationship("Enterprise", back_populates="devices")
    sensors = relationship("Sensor", back_populates="device")
    groups = relationship("Group", back_populates="device")


# =============================================================================
# ГРУППЫ (обратная совместимость + расширение)
# =============================================================================

class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    # Старое поле: владелец-пользователь (обратная совместимость)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    # Новое поле: привязка к устройству
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="groups")
    sensors = relationship("Sensor", back_populates="group")
    device = relationship("Device", back_populates="groups")


# =============================================================================
# ДАТЧИКИ (обратная совместимость + расширение)
# =============================================================================

class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(50), nullable=False)   # temperature, humidity, pressure, vibration, current, voltage
    unit = Column(String(20), nullable=False)   # °C, %, hPa, mm/s, A, V
    # Старые поля (обратная совместимость)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True)
    # Новое поле: прямая привязка к устройству
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="sensors")
    group = relationship("Group", back_populates="sensors")
    device = relationship("Device", back_populates="sensors")
