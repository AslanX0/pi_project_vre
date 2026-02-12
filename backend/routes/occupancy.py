# Routen fuer Personenschaetzung (/api/occupancy/*)

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
import pymysql

from database import get_db_connection
from modules import PersonEstimator

estimator = PersonEstimator()

router = APIRouter()


@router.get("/api/occupancy/current")
def api_occupancy_current():
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1")
        latest = cursor.fetchone()

        if not latest:
            return {"success": True, "data": {
                "estimated_occupancy": 0, "occupancy_percent": 0,
                "ac_recommendation": 3, "confidence": 0, "sensors": None
            }}

        if latest.get('estimated_occupancy') is not None:
            persons = latest['estimated_occupancy']
            ac_rec = latest.get('ac_recommendation', 3)
            confidence = 50
            model = "cached"
            climate_rec = estimator._climate_recommendation(persons)
            details = {}
        else:
            movement_rate = estimator.get_movement_rate(cursor, minutes=30)
            result = estimator.estimate(
                temperature=latest.get('temperature', 22.0),
                humidity=latest.get('humidity', 40.0),
                gas_resistance=latest.get('gas_resistance'),
                movement_detected=bool(latest.get('movement_detected', False)),
                movement_rate=movement_rate
            )
            persons = result['estimated_persons']
            ac_rec = result['climate_recommendation']['level']
            confidence = result['confidence']
            model = result['model']
            climate_rec = result['climate_recommendation']
            details = result.get('details', {})
            try:
                cursor.execute("""
                    UPDATE sensor_data
                    SET estimated_occupancy = %s, ac_recommendation = %s
                    WHERE id = %s
                """, (persons, ac_rec, latest['id']))
                conn.commit()
            except Exception:
                pass

        cursor.execute("""
            SELECT SUM(CASE WHEN movement_detected = 1 THEN 1 ELSE 0 END) as cnt
            FROM sensor_data
            WHERE timestamp >= NOW() - INTERVAL 5 MINUTE
        """)
        mot5 = cursor.fetchone()
        movement_count_5min = mot5['cnt'] if mot5 and mot5['cnt'] else 0

        return {"success": True, "data": {
            "estimated_occupancy": persons,
            "occupancy_percent": round(persons / 120 * 100, 1),
            "ac_recommendation": ac_rec,
            "confidence": confidence,
            "model": model,
            "sensors": {
                "temperature": latest.get('temperature'),
                "humidity": latest.get('humidity'),
                "pressure": latest.get('pressure'),
                "gas_resistance": latest.get('gas_resistance'),
                "movement_detected": bool(latest.get('movement_detected', False)),
                "movement_count_5min": movement_count_5min
            },
            "climate_recommendation": climate_rec,
            "details": details
        }}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@router.get("/api/occupancy/history")
def api_occupancy_history(hours: int = Query(default=24)):
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        time_ago = datetime.now() - timedelta(hours=hours)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, estimated_occupancy, ac_recommendation,
                   temperature, humidity, gas_resistance, movement_detected
            FROM sensor_data
            WHERE timestamp >= %s
            ORDER BY timestamp ASC
            LIMIT 500
        """, (time_ago,))
        data = cursor.fetchall()
        for row in data:
            if row.get("timestamp"):
                row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
            if row.get("estimated_occupancy") is None:
                try:
                    est = estimator.estimate(
                        temperature=row.get('temperature', 22.0),
                        humidity=row.get('humidity', 40.0),
                        gas_resistance=row.get('gas_resistance'),
                        movement_detected=bool(row.get('movement_detected', False))
                    )
                    row['estimated_occupancy'] = est['estimated_persons']
                    row['ac_recommendation'] = est['climate_recommendation']['level']
                except Exception:
                    row['estimated_occupancy'] = 0
                    row['ac_recommendation'] = 3
        return {"success": True, "data": data}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()
