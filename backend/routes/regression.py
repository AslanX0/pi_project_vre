# Routen fuer Lineare Regression (/api/regression/*)
# Personen -> Temperatur Vorhersage

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pymysql

from database import get_db_connection
from modules import TemperatureRegression

regression = TemperatureRegression()

router = APIRouter()


def train_regression_from_db(hours=0):
    """Trainiert das Regressionsmodell. hours=0 bedeutet alle verfuegbaren Daten."""
    conn = get_db_connection()
    if conn is None:
        regression.last_error = "Keine Datenbankverbindung"
        return False
    try:
        cursor = conn.cursor()

        if hours > 0:
            time_ago = datetime.now() - timedelta(hours=hours)
            cursor.execute("""
                SELECT timestamp, temperature
                FROM sensor_data
                WHERE timestamp >= %s
                  AND temperature IS NOT NULL
                  AND timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """, (time_ago,))
        else:
            cursor.execute("""
                SELECT timestamp, temperature
                FROM sensor_data
                WHERE temperature IS NOT NULL
                  AND timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """)

        rows = cursor.fetchall()

        if len(rows) < 3:
            regression.last_error = f"Zu wenig Daten ({len(rows)} Datenpunkte, mind. 3 benoetigt)"
            print(f"[Regression] {regression.last_error}")
            return False

        timestamps = [row['timestamp'] for row in rows]
        temp_list = [row['temperature'] for row in rows]

        # X-Werte: Stunden seit erstem Datenpunkt
        epoch = timestamps[0]
        x_list = [(t - epoch).total_seconds() / 3600 for t in timestamps]
        epoch_offset = epoch.timestamp()

        success = regression.train(x_list, temp_list, epoch_offset=epoch_offset)
        if success:
            regression.last_error = None
            print(f"[Regression] Trainiert: slope={regression.slope:.6f} °C/h, "
                  f"intercept={regression.intercept:.2f}, R²={regression.r_squared:.4f}, "
                  f"n={regression.n_samples}")
        else:
            regression.last_error = "Training fehlgeschlagen (keine Varianz in den Daten?)"
        return success
    except Exception as e:
        regression.last_error = str(e)
        print(f"[Regression] Trainingsfehler: {e}")
        return False
    finally:
        conn.close()


@router.get("/api/regression/status")
def api_regression_status():
    status = regression.get_status()
    status["last_error"] = getattr(regression, 'last_error', None)
    return {"success": True, "data": status}


@router.get("/api/regression/scatter")
def api_regression_scatter(hours: int = Query(default=0)):
    """Scatter-Daten: Zeit (x, Unix-ms) vs Temperatur (y) fuer Diagramm.
    hours=0 liefert alle verfuegbaren Daten."""
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()

        if hours > 0:
            time_ago = datetime.now() - timedelta(hours=hours)
            cursor.execute("""
                SELECT timestamp, temperature
                FROM sensor_data
                WHERE timestamp >= %s
                  AND temperature IS NOT NULL
                  AND timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """, (time_ago,))
        else:
            cursor.execute("""
                SELECT timestamp, temperature
                FROM sensor_data
                WHERE temperature IS NOT NULL
                  AND timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """)

        rows = cursor.fetchall()
        # x als Unix-Millisekunden, damit Chart.js die Achse als Zeitachse formatieren kann
        points = [
            {"x": int(row['timestamp'].timestamp() * 1000), "y": row['temperature']}
            for row in rows
        ]

        # Regressionslinie ueber die gesamte Zeitspanne
        regression_line = None
        if regression.slope is not None and regression.epoch_offset is not None and rows:
            epoch_dt = datetime.fromtimestamp(regression.epoch_offset)
            ts_first = rows[0]['timestamp']
            ts_last = rows[-1]['timestamp']
            x_first_h = (ts_first - epoch_dt).total_seconds() / 3600
            x_last_h = (ts_last - epoch_dt).total_seconds() / 3600
            regression_line = {
                "slope": regression.slope,
                "intercept": regression.intercept,
                "r_squared": regression.r_squared,
                "points": [
                    {"x": int(ts_first.timestamp() * 1000), "y": regression.predict(x_first_h)},
                    {"x": int(ts_last.timestamp() * 1000), "y": regression.predict(x_last_h)}
                ]
            }

        return {"success": True, "data": {
            "points": points,
            "count": len(points),
            "regression_line": regression_line
        }}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@router.post("/api/regression/train")
def api_regression_train(hours: int = Query(default=0)):
    """Manuelles Neutrainieren des Modells. hours=0 nutzt alle Daten."""
    success = train_regression_from_db(hours=hours)
    if success:
        return {"success": True, "message": "Modell trainiert",
                "data": regression.get_status()}
    return JSONResponse(status_code=400,
                        content={"success": False,
                                 "error": getattr(regression, 'last_error', 'Unbekannter Fehler')})