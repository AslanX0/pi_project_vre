# Routen fuer Lineare Regression (/api/regression/*)
# Zeit -> Temperatur / Feuchte / Luftqualitaet

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pymysql
import numpy as np

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


def _lin_reg(x_arr, y_raw):
    """Inline lineare Regression. Filtert None-Werte heraus."""
    pairs = [(x, y) for x, y in zip(x_arr, y_raw) if y is not None]
    if len(pairs) < 3:
        return None, None
    x = np.array([p[0] for p in pairs], dtype=float)
    y = np.array([p[1] for p in pairs], dtype=float)
    n = len(x)
    sx, sy = np.sum(x), np.sum(y)
    denom = n * np.sum(x ** 2) - sx ** 2
    if denom == 0:
        return None, None
    slope = float((n * np.sum(x * y) - sx * sy) / denom)
    intercept = float((sy - slope * sx) / n)
    return slope, intercept


def _build_series(x_ms, x_hours, y_raw, slope, intercept, last_ts, epoch_dt, n_predictions=5):
    """Baut Datenpunkte, Trendlinie und Prognose fuer eine Variable auf."""
    points = [{"x": xm, "y": y} for xm, y in zip(x_ms, y_raw) if y is not None]

    trend = None
    predictions = []
    if slope is not None and len(x_hours) >= 2:
        trend = [
            {"x": x_ms[0], "y": round(slope * x_hours[0] + intercept, 2)},
            {"x": x_ms[-1], "y": round(slope * x_hours[-1] + intercept, 2)}
        ]
        for i in range(1, n_predictions + 1):
            future_ts = last_ts + timedelta(minutes=5 * i)
            x_h = (future_ts - epoch_dt).total_seconds() / 3600
            predictions.append({
                "x": int(future_ts.timestamp() * 1000),
                "y": round(slope * x_h + intercept, 2)
            })

    return {"points": points, "trend": trend, "predictions": predictions}


@router.get("/api/regression/scatter")
def api_regression_scatter(hours: int = Query(default=0)):
    """Zeitreihen-Daten fuer Temperatur, Feuchte und Luftqualitaet mit Trendlinie und Prognose."""
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        if hours > 0:
            time_ago = datetime.now() - timedelta(hours=hours)
            cursor.execute("""
                SELECT timestamp, temperature, humidity, gas_resistance
                FROM sensor_data
                WHERE timestamp >= %s AND timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """, (time_ago,))
        else:
            cursor.execute("""
                SELECT timestamp, temperature, humidity, gas_resistance
                FROM sensor_data
                WHERE timestamp IS NOT NULL
                ORDER BY timestamp ASC
            """)

        rows = cursor.fetchall()
        if not rows:
            empty = {"points": [], "trend": None, "predictions": []}
            return {"success": True, "data": {
                "temperature": empty, "humidity": empty, "gas": empty, "count": 0
            }}

        # Epoch-Referenzpunkt
        if regression.epoch_offset is not None:
            epoch_dt = datetime.fromtimestamp(regression.epoch_offset)
        else:
            epoch_dt = rows[0]['timestamp']

        x_ms = [int(r['timestamp'].timestamp() * 1000) for r in rows]
        x_hours = [(r['timestamp'] - epoch_dt).total_seconds() / 3600 for r in rows]
        last_ts = rows[-1]['timestamp']

        temp_vals = [r.get('temperature') for r in rows]
        hum_vals = [r.get('humidity') for r in rows]
        gas_vals = [r.get('gas_resistance') for r in rows]

        # Fuer Temperatur: trainiertes Modell bevorzugen, sonst inline berechnen
        if regression.slope is not None and regression.epoch_offset is not None:
            t_slope, t_intercept = regression.slope, regression.intercept
        else:
            t_slope, t_intercept = _lin_reg(x_hours, temp_vals)

        h_slope, h_intercept = _lin_reg(x_hours, hum_vals)
        g_slope, g_intercept = _lin_reg(x_hours, gas_vals)

        return {"success": True, "data": {
            "temperature": _build_series(x_ms, x_hours, temp_vals, t_slope, t_intercept, last_ts, epoch_dt),
            "humidity":    _build_series(x_ms, x_hours, hum_vals,  h_slope, h_intercept, last_ts, epoch_dt),
            "gas":         _build_series(x_ms, x_hours, gas_vals,  g_slope, g_intercept, last_ts, epoch_dt),
            "count": len(rows),
            "regression_line": {  # Rueckwaertskompatibilitaet fuer Status-Karten
                "slope": t_slope, "intercept": t_intercept,
                "r_squared": regression.r_squared
            } if t_slope is not None else None
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