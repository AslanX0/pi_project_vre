# Routen fuer Lineare Regression (/api/regression/*)
#
# Bildet die Beziehung zwischen geschaetzter Personenanzahl und gemessener Temperatur ab.
# Mehr Personen -> mehr Koerperwaerme -> hoehere Raumtemperatur.
# Das Modell wird automatisch stuendlich neu trainiert (siehe app.py regression_train_loop).

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pymysql

from vre_project.backend.database import get_db_connection
from vre_project.backend.modules import TemperatureRegression

# Einzelne Instanz des Regressionsmodells – haelt slope/intercept im Speicher
# und laedt beim Start ein gespeichertes Modell aus regression_model.json
regression = TemperatureRegression()

router = APIRouter()


def train_regression_from_db(hours=0):
    """Laedt Trainingsdaten aus der DB und trainiert das Regressionsmodell neu.

    hours=0: alle verfuegbaren Daten verwenden
    hours>0: nur Daten der letzten N Stunden (z.B. 48h fuer den stuendlichen Zyklus)
    Mindestens 3 Datenpunkte werden benoetigt, sonst schlaegt das Training fehl.
    """
    conn = get_db_connection()
    if conn is None:
        regression.last_error = "Keine Datenbankverbindung"
        return False
    try:
        cursor = conn.cursor()

        if hours > 0:
            time_ago = datetime.now() - timedelta(hours=hours)
            cursor.execute("""
                SELECT estimated_occupancy, temperature
                FROM sensor_data
                WHERE timestamp >= %s
                  AND temperature IS NOT NULL
                  AND estimated_occupancy IS NOT NULL
                ORDER BY timestamp ASC
            """, (time_ago,))
        else:
            cursor.execute("""
                SELECT estimated_occupancy, temperature
                FROM sensor_data
                WHERE temperature IS NOT NULL
                  AND estimated_occupancy IS NOT NULL
                ORDER BY timestamp ASC
            """)

        rows = cursor.fetchall()

        if len(rows) < 3:
            regression.last_error = f"Zu wenig Daten ({len(rows)} Datenpunkte, mind. 3 benoetigt)"
            return False

        persons_list = [row['estimated_occupancy'] for row in rows]
        temp_list = [row['temperature'] for row in rows]

        success = regression.train(persons_list, temp_list)
        if success:
            regression.last_error = None
        else:
            regression.last_error = "Training fehlgeschlagen"
        return success
    except Exception as e:
        regression.last_error = str(e)
        print(f"[Regression] Trainingsfehler: {e}")
        return False
    finally:
        conn.close()


@router.get("/api/regression/status")
def api_regression_status():
    """Gibt Modellparameter und Guete (R²) zurueck. last_error zeigt den letzten Trainingsfehler."""
    status = regression.get_status()
    status["last_error"] = getattr(regression, 'last_error', None)
    return {"success": True, "data": status}


@router.get("/api/regression/predict")
def api_regression_predict(persons: int = Query(default=60, ge=0, le=120)):
    """Berechnet die vorhergesagte Temperatur fuer eine gegebene Personenzahl.
    Gibt HTTP 400 zurueck wenn das Modell noch nicht trainiert wurde.
    """
    temp = regression.predict(persons)
    if temp is None:
        return JSONResponse(status_code=400,
                            content={"success": False, "error": "Modell noch nicht trainiert"})
    return {"success": True, "data": {
        "persons": persons, "predicted_temperature": temp
    }}


@router.get("/api/regression/scatter")
def api_regression_scatter(hours: int = Query(default=48)):
    """Liefert Streudiagramm-Daten: Personenanzahl (x) vs. Temperatur (y).

    Enthaelt zusaetzlich die berechnete Regressionsgerade als zwei Endpunkte,
    damit das Frontend die Gerade ohne eigene Berechnung zeichnen kann.
    hours=0 liefert alle verfuegbaren Daten.
    """
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()

        if hours > 0:
            time_ago = datetime.now() - timedelta(hours=hours)
            cursor.execute("""
                SELECT estimated_occupancy, temperature
                FROM sensor_data
                WHERE timestamp >= %s
                  AND temperature IS NOT NULL
                  AND estimated_occupancy IS NOT NULL
                ORDER BY timestamp ASC
            """, (time_ago,))
        else:
            cursor.execute("""
                SELECT estimated_occupancy, temperature
                FROM sensor_data
                WHERE temperature IS NOT NULL
                  AND estimated_occupancy IS NOT NULL
                ORDER BY timestamp ASC
            """)

        rows = cursor.fetchall()
        points = [{"x": row['estimated_occupancy'], "y": row['temperature']} for row in rows]

        regression_line = None
        if regression.slope is not None and points:
            # Linie etwas ueber den Wertebereich der Datenpunkte hinaus verlängern
            x_min = min(p['x'] for p in points)
            x_max = max(p['x'] for p in points)
            line_start = max(0, x_min - 5)
            line_end = min(130, x_max + 5)
            regression_line = {
                "slope": regression.slope,
                "intercept": regression.intercept,
                "r_squared": regression.r_squared,
                # nur Start- und Endpunkt der Geraden – Chart.js zeichnet die Linie dazwischen
                "points": [
                    {"x": line_start, "y": regression.predict(line_start)},
                    {"x": line_end,   "y": regression.predict(line_end)}
                ]
            }

        return {"success": True, "data": {
            "points": points,
            "count": len(points),
            "regression_line": regression_line,
            "scenarios": regression.predict_scenarios()
        }}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@router.post("/api/regression/train")
def api_regression_train(hours: int = Query(default=0)):
    """Loest manuell ein Neutrainieren des Modells aus.
    hours=0 nutzt alle verfuegbaren Daten. Nützlich nach langen Betriebsphasen
    oder um das automatische stuendliche Training zu ueberschreiben.
    """
    success = train_regression_from_db(hours=hours)
    if success:
        return {"success": True, "message": "Modell trainiert",
                "data": regression.get_status()}
    return JSONResponse(status_code=400,
                        content={"success": False,
                                 "error": getattr(regression, 'last_error', 'Unbekannter Fehler')})
