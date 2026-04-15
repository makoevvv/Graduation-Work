from fastapi import APIRouter
from .endpoints import auth, groups, sensors, data, predictions, enterprises, devices

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["authentication"])
router.include_router(enterprises.router, prefix="/enterprises", tags=["enterprises"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(groups.router, prefix="/groups", tags=["groups"])
router.include_router(sensors.router, prefix="/sensors", tags=["sensors"])
router.include_router(data.router, prefix="/data", tags=["data"])
router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])