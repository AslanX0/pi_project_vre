# FastAPI-Server – Restaurant Sensor API
# BME680 (Temperatur, Feuchtigkeit, VOC) + RCWL-0516 (Bewegung)
# Personenschaetzung (VOC-Baseline) + Lineare Regression (Personen -> Temperatur)
#
# Architektur: Der Server hat drei Hintergrund-Tasks die parallel zur API laufen:
#   1. estimation_loop  – berechnet fehlende Personenschaetzungen in der DB nach
#   2. regression_train_loop – trainiert das Regressionsmodell stuendlich neu
#   3. data_retention_loop – loescht Messdaten aelter als 30 Tage (Datenbankpflege)

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
    """Hintergrund-Task: Fuellt estimated_occupancy fuer Datensaetze nach, die noch keinen Wert haben.

    Laeuft alle 60 Sekunden und verarbeitet maximal 500 Datensaetze pro Durchlauf.
    Das passiert z.B. nach einem Neustart, wenn der Sensor Daten gespeichert hat
    bevor die Schaetzlogik aktiv war.
    """
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    cursor = conn.cursor()
                    # nur Zeilen ohne Schaetzwert holen, aufsteigend damit aeltere Daten zuerst bearbeitet werden
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
    """Hintergrund-Task: Loescht Messdaten aelter als 30 Tage.

    Laeuft einmal taeglich. Verhindert dass die Datenbank auf dem Raspberry Pi
    zu gross wird – der SD-Karten-Speicher ist begrenzt.
    """
    while True:
        # 24 Stunden warten bevor die erste Bereinigung laeuft
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
    """Hintergrund-Task: Trainiert das Regressionsmodell (Personen -> Temperatur) stuendlich neu.

    Wartet beim Start 10 Sekunden damit die DB-Verbindung sicher steht,
    dann sofortiges erstes Training – danach jede Stunde mit den letzten 48h Daten.
    """
    # kurz warten damit die App vollstaendig hochgefahren ist bevor das erste Training startet
    await asyncio.sleep(10)
    train_regression_from_db(hours=48)

    while True:
        await asyncio.sleep(3600)  # stuendlich neu trainieren
        try:
            train_regression_from_db(hours=48)
            print("[Regression] MODELL TRAINIERT (1h-Zyklus, letzte 48h Daten)")
        except Exception as e:
            print(f"[Regression] FEHLER: {e}")


def init_db():
    """Erstellt die Messtabelle beim Serverstart, falls sie noch nicht existiert.
    Wird synchron ausgefuehrt bevor die Hintergrund-Tasks starten.
    """
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
    """FastAPI-Lifespan: startet beim Hochfahren die Hintergrund-Tasks und bricht sie beim Herunterfahren ab.

    Das lifespan-Muster ersetzt seit FastAPI 0.93 die veralteten on_event-Handler.
    """
    init_db()
    # alle drei Tasks parallel starten
    task_est = asyncio.create_task(estimation_loop())
    task_reg = asyncio.create_task(regression_train_loop())
    task_ret = asyncio.create_task(data_retention_loop())
    yield  # hier laeuft die App
    # beim Beenden alle Tasks sauber abbrechen
    task_est.cancel()
    task_reg.cancel()
    task_ret.cancel()


app = FastAPI(title="Asia Restaurant API", lifespan=lifespan)

# CORS offen fuer alle Origins – akzeptabel weil der Server nur im lokalen Netzwerk erreichbar ist
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=True)

# API-Routen aus den einzelnen Modulen einbinden
app.include_router(data_router)
app.include_router(occupancy_router)
app.include_router(estimator_router)
app.include_router(regression_router)

# Pfad zum Frontend-Verzeichnis – relativ zur aktuellen Datei aufgeloest
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


# Die folgenden Routen liefern alle das gleiche index.html aus.
# Das JavaScript im Browser uebernimmt dann das Tab-Routing (Single Page Application).
@app.get("/")
def serve_dashboard(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/regression")
def serve_regression(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/sensors")
def serve_sensors(): return FileResponse(str(FRONTEND_DIR / "index.html"))

@app.get("/history")
def serve_history(): return FileResponse(str(FRONTEND_DIR / "index.html"))


# CSS, JS und andere statische Dateien unter /static bereitstellen
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    print("   " + "=" * 56)
    print("   Dashboard:      http://127.0.0.1:8000/")
    print("   API Docs:       http://127.0.0.1:8000/docs")
    print("   Regression:     http://127.0.0.1:8000/api/regression/status")
    print("=" * 67 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
