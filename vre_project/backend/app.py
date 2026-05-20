# FastAPI-Server - Restaurant Sensor API
# BME680 (Temperatur, Feuchtigkeit, VOC) + RCWL-0516 (Bewegung)
# Personenschätzung (VOC-Baseline) + Lineare Regression (Personen -> Temperatur)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from vre_project.backend.database import get_db_connection, db_config
import pymysql
from vre_project.backend.routes import data_router, occupancy_router, estimator_router, regression_router
from vre_project.backend.routes.occupancy import estimator
from vre_project.backend.routes.regression import regression, train_regression_from_db


async def estimation_loop():
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, gas_resistance, movement_detected
                        FROM sensor_data
                        WHERE estimated_occupancy IS NULL
                        ORDER BY id ASC
                        LIMIT 500
                    """)
                    rows = cursor.fetchall()
                    for row in rows:
                        result = estimator.estimate(
                            row.get('gas_resistance'),
                            bool(row.get('movement_detected', False))
                        )
                        persons = result['estimated_persons']
                        cursor.execute(
                            "UPDATE sensor_data SET estimated_occupancy = %s WHERE id = %s",
                            (persons, row['id']))
                    conn.commit()
                    if rows:
                        print(f"[AutoEstimator] {len(rows)} DATENSÄTZE GESCHÄTZT")
                finally:
                    conn.close()
        except Exception as e:
            print(f"[AutoEstimator] FEHLER: {e}")
        await asyncio.sleep(60)


async def data_retention_loop():
    """Löscht Datensätze älter als 30 Tage und läuft einmal täglich."""
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM sensor_data WHERE timestamp < NOW() - INTERVAL 30 DAY"
                    )
                    deleted = cursor.rowcount
                    conn.commit()
                    if deleted > 0:
                        print(f"[Retention] {deleted} DATENSÄTZE GELÖSCHT (>30 Tage)")
                finally:
                    conn.close()
        except Exception as e:
            print(f"[Retention] Fehler: {e}")


async def regression_train_loop():
    """Trainiert Regressionsmodell stuendlich mit Daten der letzten 48 Stunden."""
    # Erstes Training direkt beim Start
    await asyncio.sleep(10)
    train_regression_from_db(hours=48)

    while True:
        await asyncio.sleep(3600)  # Stuendlich neu trainieren
        try:
            train_regression_from_db(hours=48)
            print("[Regression] MODELL TRAINIERT (1h-Zyklus, letzte 48h Daten)")
        except Exception as e:
            print(f"[Regression] FEHLER: {e}")


def init_db():
    conn = get_db_connection()
    if conn is None:
        print("[DB] FEHLER - KEINE VERBINDUNG")
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS sensor_data ("
            "id INT AUTO_INCREMENT PRIMARY KEY, "
            "timestamp DATETIME NOT NULL, "
            "temperature FLOAT NOT NULL, "
            "pressure FLOAT, "
            "humidity FLOAT, "
            "gas_resistance FLOAT, "
            "movement_detected BOOLEAN NOT NULL, "
            "estimated_occupancy INT DEFAULT NULL, "
            "ac_recommendation INT DEFAULT NULL)"
        )
        conn.commit()
    finally:
        conn.close()


@asynccontextmanager
async def lifespan(app):
    init_db()
    task_est = asyncio.create_task(estimation_loop())
    task_reg = asyncio.create_task(regression_train_loop())
    task_ret = asyncio.create_task(data_retention_loop())
    yield
    task_est.cancel()
    task_reg.cancel()
    task_ret.cancel()


app = FastAPI(title="Asia Restaurant API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=True)

app.include_router(data_router)
app.include_router(occupancy_router)
app.include_router(estimator_router)
app.include_router(regression_router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/")
def serve_dashboard(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/regression")
def serve_regression(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/sensors")
def serve_sensors(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/history")
def serve_history(): return FileResponse(str(FRONTEND_DIR / "index.html"))


app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    print("   " + "=" * 56)
    print("   Dashboard:      http://127.0.0.1:8000/")
    print("   API Docs:       http://127.0.0.1:8000/docs")
    print("   Regression:     http://127.0.0.1:8000/api/regression/status")
    print("=" * 67 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
