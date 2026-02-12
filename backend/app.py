# FastAPI-Server - Restaurant Sensor API (Sensordaten, Personenschaetzung, Auto-Estimation)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from database import get_db_connection
from routes import data_router, occupancy_router, estimator_router
from routes.occupancy import estimator


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

app.include_router(data_router)
app.include_router(occupancy_router)
app.include_router(estimator_router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("   ASIA RESTAURANT - FastAPI Sensor Server")
    print("   " + "=" * 56)
    print("   Dashboard:      http://0.0.0.0:5000/")
    print("   API Docs:       http://0.0.0.0:5000/docs")
    print("   API Occupancy:  http://0.0.0.0:5000/api/occupancy/current")
    print("   API Sensoren:   http://0.0.0.0:5000/api/data/latest")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=5000)
