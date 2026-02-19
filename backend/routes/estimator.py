# Routen fuer Estimator-Konfiguration (/api/estimator/*)

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from routes.occupancy import estimator

router = APIRouter()


class BaselineRequest(BaseModel):
    temperature: float = 20.0


class FullTempRequest(BaseModel):
    temperature: float = 30.0


@router.get("/api/estimator/status")
def api_estimator_status():
    return {"success": True, "data": estimator.get_status()}


@router.post("/api/estimator/baseline")
def api_set_baseline(body: BaselineRequest):
    """Leerer Raum: Basistemperatur setzen (bei 0 Personen aufrufen)."""
    estimator.set_baseline(temperature=body.temperature)
    return {"success": True, "message": "Basistemperatur gesetzt",
            "data": estimator.get_status()}


@router.post("/api/estimator/fulltemp")
def api_set_full_temp(body: FullTempRequest):
    """Voller Raum (120 Personen): Maximaltemperatur setzen."""
    estimator.set_full_temp(temperature=body.temperature)
    return {"success": True, "message": "Vollbelegungs-Temperatur gesetzt",
            "data": estimator.get_status()}