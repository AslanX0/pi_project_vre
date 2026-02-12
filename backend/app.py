# FastAPI-Server - Restaurant Sensor API (Sensordaten, Personenschaetzung, Auto-Estimation)

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field
import pymysql
import asyncio
from datetime import datetime, timedelta
from regressionsanalyse import PersonEstimator

db_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root',
    'database': 'sensor_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

estimator = PersonEstimator()


def get_db_connection():
    try:
        return pymysql.connect(**db_config)
    except pymysql.Error as e:
        print(f"Fehler bei Datenbankverbindung: {e}")
        return None


class BaselineRequest(BaseModel):
    temperature: float = 22.0
    humidity: float = 40.0
    gas_resistance: float = 200000

class TrainingRequest(BaseModel):
    actual_persons: int = Field(..., ge=0, le=120)


async def estimation_loop():
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, temperature, humidity, gas_resistance, movement_detected
                        FROM sensor_data
                        WHERE estimated_occupancy IS NULL
                        ORDER BY id ASC
                    """)
                    rows = cursor.fetchall()
                    for row in rows:
                        movement_rate = estimator.get_movement_rate(cursor, minutes=30)
                        result = estimator.estimate(
                            temperature=row.get('temperature', 22.0),
                            humidity=row.get('humidity', 40.0),
                            gas_resistance=row.get('gas_resistance'),
                            movement_detected=bool(row.get('movement_detected', False)),
                            movement_rate=movement_rate
                        )
                        persons = result['estimated_persons']
                        ac_rec = result['climate_recommendation']['level']
                        cursor.execute("""
                            UPDATE sensor_data
                            SET estimated_occupancy = %s, ac_recommendation = %s
                            WHERE id = %s
                        """, (persons, ac_rec, row['id']))
                    conn.commit()
                    if rows:
                        print(f"[AutoEstimator] {len(rows)} Datensaetze geschaetzt")
                finally:
                    conn.close()
        except Exception as e:
            print(f"[AutoEstimator] Fehler: {e}")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(estimation_loop())
    print("[AutoEstimator] Hintergrund-Schaetzung gestartet (alle 60s)")
    yield
    task.cancel()


app = FastAPI(title="Asia Restaurant Sensor API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=True)


@app.get("/api/data/latest")
def api_latest():
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 1")
        data = cursor.fetchone()
        if data and data.get("timestamp"):
            data["timestamp"] = data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "data": data or {}}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@app.get("/api/data/stats")
def api_stats():
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        time_24h_ago = datetime.now() - timedelta(hours=24)
        cursor.execute("""
            SELECT
                COUNT(*) as total_readings,
                AVG(temperature) as avg_temp,
                MAX(temperature) as max_temp,
                MIN(temperature) as min_temp,
                AVG(humidity) as avg_humidity,
                AVG(pressure) as avg_pressure,
                SUM(CASE WHEN movement_detected = 1 THEN 1 ELSE 0 END) as movement_count,
                AVG(estimated_occupancy) as avg_occupancy,
                MAX(estimated_occupancy) as max_occupancy,
                MIN(estimated_occupancy) as min_occupancy
            FROM sensor_data
            WHERE timestamp >= %s
        """, (time_24h_ago,))
        stats = cursor.fetchone()
        return {"success": True, "data": stats or {}}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@app.get("/api/data/history")
def api_history(hours: int = Query(default=24), limit: int = Query(default=1000)):
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        time_ago = datetime.now() - timedelta(hours=hours)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM sensor_data
            WHERE timestamp >= %s
            ORDER BY timestamp ASC
            LIMIT %s
        """, (time_ago, limit))
        data = cursor.fetchall()
        for row in data:
            if row.get("timestamp"):
                row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        return {"success": True, "data": data}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@app.get("/api/data/table")
def api_table(page: int = Query(default=1), per_page: int = Query(default=20)):
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "Datenbankverbindung fehlgeschlagen"})
    try:
        offset = (page - 1) * per_page
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as total FROM sensor_data")
        total = cursor.fetchone()['total']
        cursor.execute("""
            SELECT * FROM sensor_data
            ORDER BY id DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        data = cursor.fetchall()
        for row in data:
            if row.get("timestamp"):
                row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }
        return {"success": True, "data": data, "pagination": pagination}
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        conn.close()


@app.get("/api/occupancy/current")
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


@app.get("/api/occupancy/history")
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


@app.get("/api/estimator/status")
def api_estimator_status():
    return {"success": True, "data": estimator.get_status()}


@app.post("/api/estimator/baseline")
def api_set_baseline(body: BaselineRequest):
    estimator.set_baseline(
        temperature=body.temperature,
        humidity=body.humidity,
        gas_resistance=body.gas_resistance
    )
    return {"success": True, "message": "Baseline gesetzt"}


@app.post("/api/estimator/train")
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


@app.get("/api/data")
def api_data_legacy():
    conn = get_db_connection()
    if conn is None:
        return JSONResponse(status_code=500, content={"error": "Datenbankverbindung fehlgeschlagen"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 50")
        data = cursor.fetchall()
        for row in data:
            if row.get("timestamp"):
                row["timestamp"] = row["timestamp"].strftime("%Y-%m-%d %H:%M:%S")
        return data
    except pymysql.Error as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        conn.close()


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("   ASIA RESTAURANT - FastAPI Sensor Server")
    print("   " + "=" * 56)
    print("   API Docs:      http://0.0.0.0:5000/docs")
    print("   API Occupancy:  http://0.0.0.0:5000/api/occupancy/current")
    print("   API Sensoren:   http://0.0.0.0:5000/api/data/latest")
    print("   API Stats:      http://0.0.0.0:5000/api/data/stats")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=5000)
