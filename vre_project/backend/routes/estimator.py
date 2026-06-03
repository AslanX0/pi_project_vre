# Routen fuer Estimator-Konfiguration (/api/estimator/*)
#
# Ermoeglicht das Ablesen und Setzen der VOC-Baseline, die fuer die
# Personenschaetzung benoetigt wird. Die Baseline repraesentiert den
# Gaswiderstand bei leerem Raum – je niedriger der aktuelle Wert
# relativ dazu, desto mehr Personen werden geschaetzt.

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vre_project.backend.routes.occupancy import estimator

router = APIRouter()


class BaselineRequest(BaseModel):
    """Anfrage-Body fuer das Setzen der VOC-Baseline.
    Standardwert 200000 Ohm entspricht typischer Frischluft-Qualitaet des BME680.
    """
    gas_resistance: float = 200000


@router.get("/api/estimator/status")
def api_estimator_status():
    """Gibt den aktuellen Kalibrierungsstatus und die gespeicherte Baseline zurueck."""
    return {"success": True, "data": estimator.get_status()}


@router.post("/api/estimator/baseline")
def api_set_baseline(body: BaselineRequest):
    """Setzt die VOC-Baseline fuer die Personenschaetzung.

    Sollte bei leerem Restaurant aufgerufen werden, damit der aktuelle
    Gaswiderstand als Referenzwert (0 Personen) gespeichert wird.
    Die Baseline wird in calibration.json auf dem Pi gespeichert und
    bleibt auch nach einem Neustart erhalten.
    """
    estimator.set_baseline(gas_resistance=body.gas_resistance)
    return {"success": True, "message": "VOC-Baseline gesetzt",
            "data": estimator.get_status()}
