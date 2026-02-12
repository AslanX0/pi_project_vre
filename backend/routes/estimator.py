# Routen fuer Estimator-Konfiguration (/api/estimator/*)

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database import get_db_connection
from routes.occupancy import estimator

router = APIRouter()


class BaselineRequest(BaseModel):
    temperature: float = 22.0
    humidity: float = 40.0
    gas_resistance: float = 200000


class TrainingRequest(BaseModel):
    actual_persons: int = Field(..., ge=0, le=120)


@router.get("/api/estimator/status")
def api_estimator_status():
    return {"success": True, "data": estimator.get_status()}


@router.post("/api/estimator/baseline")
def api_set_baseline(body: BaselineRequest):
    estimator.set_baseline(
        temperature=body.temperature,
        humidity=body.humidity,
        gas_resistance=body.gas_resistance
    )
    return {"success": True, "message": "Baseline gesetzt"}


@router.post("/api/estimator/train")
def api_add_training(body: TrainingRequest):
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1")
        latest = cursor.fetchone()
        if latest:
            estimator.add_training_point(
                actual_persons=body.actual_persons,
                temperature=latest.get('temperature', 22.0),
                humidity=latest.get('humidity', 40.0),
                gas_resistance=latest.get('gas_resistance'),
                movement_detected=bool(latest.get('movement_detected', False))
            )
            return {"success": True, "message": "Trainingspunkt gespeichert",
                    "status": estimator.get_status()}
        else:
            return JSONResponse(status_code=404,
                                content={"success": False, "error": "Keine Sensordaten vorhanden"})
    finally:
        conn.close()
