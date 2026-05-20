#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motion_recorder.py

Bewegungsgesteuertes Aufnahmesystem fuer Raspberry Pi 4.
Bei Erkennung einer Bewegung durch den PIR-Sensor (HW-416) wird eine
5-sekuendige Videoaufnahme mit der Pi Camera V1.3 gestartet, lokal als
MP4 gespeichert und ein Eintrag in eine MariaDB-Datenbank geschrieben.

Hardware:
  - PIR OUT  -> GPIO17 (BCM)
  - Pi Camera V1.3 ueber CSI

Benoetigt: picamera2, gpiozero, mysql-connector-python, ffmpeg
"""

import os
import sys
import time
import signal
import logging
import subprocess
from datetime import datetime

from gpiozero import MotionSensor
from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput
import mysql.connector
from mysql.connector import Error as MySQLError

# ---------------------------------------------------------------------------
# Konfiguration / Konstanten
# ---------------------------------------------------------------------------

# GPIO-Pin (BCM-Nummerierung) an dem der PIR-OUT-Pin haengt
PIR_GPIO_PIN = 17

# Dauer der Videoaufnahme in Sekunden
RECORD_SECONDS = 5

# Zielverzeichnis fuer die Aufnahmen
RECORDINGS_DIR = "/home/it/pi_project_vre/recordings"

# Datenbank-Zugangsdaten (Platzhalter -> bitte anpassen)
DB_HOST = "localhost"
DB_PORT = 3306
DB_NAME = "motion_detection"
DB_USER = "motion_user"
DB_PASSWORD = "test123"

# ---------------------------------------------------------------------------
# Logging-Setup (Konsolenausgabe mit Timestamp)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("motion_recorder")


class MotionRecorder:
    """Kapselt Kamera, PIR-Sensor und Datenbankverbindung."""

    def __init__(self):
        self.camera = None
        self.pir = None
        self.db_conn = None
        # Flag, damit nicht waehrend einer laufenden Aufnahme erneut
        # getriggert wird (PIR feuert sonst mehrfach hintereinander).
        self.is_recording = False
        self.running = True

    # -- Initialisierung -----------------------------------------------------

    def setup_directory(self):
        """Legt das Aufnahmeverzeichnis an, falls es nicht existiert."""
        try:
            os.makedirs(RECORDINGS_DIR, exist_ok=True)
            logger.info("Aufnahmeverzeichnis bereit: %s", RECORDINGS_DIR)
        except OSError as exc:
            logger.error("Konnte Verzeichnis nicht anlegen: %s", exc)
            raise

    def setup_camera(self):
        """Initialisiert die Pi Camera ueber picamera2."""
        try:
            self.camera = Picamera2()
            # Video-Konfiguration; Aufloesung an die V1.3-Kamera angepasst
            video_config = self.camera.create_video_configuration(
                main={"size": (1296, 972)}
            )
            self.camera.configure(video_config)
            logger.info("Kamera initialisiert (picamera2).")
        except Exception as exc:
            logger.error("Kamera-Initialisierung fehlgeschlagen: %s", exc)
            raise

    def setup_pir(self):
        """Initialisiert den PIR-Bewegungssensor ueber gpiozero."""
        try:
            self.pir = MotionSensor(PIR_GPIO_PIN)
            # Kurze Einschwingzeit, damit der Sensor sich stabilisiert
            logger.info("PIR-Sensor an GPIO%d wird kalibriert ...", PIR_GPIO_PIN)
            self.pir.wait_for_no_motion(timeout=5)
            # Callback registrieren
            self.pir.when_motion = self.on_motion
            logger.info("PIR-Sensor bereit. Warte auf Bewegung ...")
        except Exception as exc:
            logger.error("PIR-Initialisierung fehlgeschlagen: %s", exc)
            raise

    def setup_database(self):
        """Stellt die Verbindung zur MariaDB-Datenbank her."""
        try:
            self.db_conn = mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                autocommit=False,
            )
            if self.db_conn.is_connected():
                logger.info("Datenbankverbindung zu '%s' hergestellt.", DB_NAME)
        except MySQLError as exc:
            logger.error("Datenbankverbindung fehlgeschlagen: %s", exc)
            raise

    # -- Kernlogik -----------------------------------------------------------

    def on_motion(self):
        """
        Callback bei Bewegungserkennung.
        Wird durch gpiozero in einem eigenen Thread aufgerufen.
        """
        # Verhindert mehrfaches Triggern waehrend einer laufenden Aufnahme
        if self.is_recording:
            return

        self.is_recording = True
        try:
            logger.info("Bewegung erkannt!")
            self.record_and_store()
        except Exception as exc:
            logger.error("Fehler bei der Verarbeitung der Bewegung: %s", exc)
        finally:
            self.is_recording = False
            logger.info("Zurueck im Wartezustand. Warte auf Bewegung ...")

    def record_and_store(self):
        """Nimmt ein Video auf, konvertiert es zu MP4 und schreibt den DB-Eintrag."""
        timestamp = datetime.now()
        ts_string = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        base_name = f"motion_{ts_string}"

        h264_path = os.path.join(RECORDINGS_DIR, base_name + ".h264")
        mp4_path = os.path.join(RECORDINGS_DIR, base_name + ".mp4")

        # --- Aufnahme ---
        encoder = H264Encoder()
        logger.info("Aufnahme gestartet (%d Sekunden) ...", RECORD_SECONDS)
        try:
            self.camera.start_recording(encoder, FileOutput(h264_path))
            time.sleep(RECORD_SECONDS)
            self.camera.stop_recording()
            logger.info("Aufnahme beendet: %s", h264_path)
        except Exception as exc:
            logger.error("Fehler waehrend der Aufnahme: %s", exc)
            # Falls die Aufnahme abbricht, nicht weiter zum DB-Eintrag
            return

        # --- Konvertierung h264 -> mp4 ---
        if not self.convert_to_mp4(h264_path, mp4_path):
            logger.error("MP4-Konvertierung fehlgeschlagen. Kein DB-Eintrag.")
            return

        # --- DB-Eintrag ---
        self.insert_db_record(timestamp, base_name + ".mp4", mp4_path)

    def convert_to_mp4(self, h264_path, mp4_path):
        """
        Konvertiert die rohe H.264-Datei in einen MP4-Container mittels ffmpeg.
        Loescht bei Erfolg die temporaere .h264-Datei.
        """
        try:
            # -r 30: Framerate setzen; -c copy: kein Re-Encoding (schnell)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",                # vorhandene Datei ueberschreiben
                    "-framerate", "30",
                    "-i", h264_path,
                    "-c", "copy",
                    mp4_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info("Video konvertiert zu MP4: %s", mp4_path)

            # Temporaere h264-Datei aufraeumen
            if os.path.exists(h264_path):
                os.remove(h264_path)
            return True
        except subprocess.CalledProcessError as exc:
            logger.error("ffmpeg-Konvertierung fehlgeschlagen: %s", exc)
            return False
        except FileNotFoundError:
            logger.error("ffmpeg nicht gefunden. Bitte installieren (apt install ffmpeg).")
            return False

    def insert_db_record(self, timestamp, dateiname, dateipfad):
        """Schreibt einen Datensatz in die Tabelle 'recordings'."""
        cursor = None
        try:
            # Verbindung pruefen und ggf. neu aufbauen (z.B. nach Timeout)
            if self.db_conn is None or not self.db_conn.is_connected():
                logger.warning("DB-Verbindung verloren, baue neu auf ...")
                self.setup_database()

            cursor = self.db_conn.cursor()
            sql = (
                "INSERT INTO recordings (timestamp, dateiname, dateipfad) "
                "VALUES (%s, %s, %s)"
            )
            cursor.execute(sql, (timestamp, dateiname, dateipfad))
            self.db_conn.commit()
            logger.info(
                "DB-Eintrag erfolgreich (ID %s): %s", cursor.lastrowid, dateiname
            )
        except MySQLError as exc:
            logger.error("DB-Eintrag fehlgeschlagen: %s", exc)
            if self.db_conn is not None:
                try:
                    self.db_conn.rollback()
                except MySQLError:
                    pass
        finally:
            if cursor is not None:
                cursor.close()

    # -- Lebenszyklus --------------------------------------------------------

    def run(self):
        """Startet das System und haelt den Hauptthread offen."""
        self.setup_directory()
        self.setup_database()
        self.setup_camera()
        self.setup_pir()

        # Hauptthread offen halten. gpiozero verarbeitet die Events im
        # Hintergrund-Thread; hier nur auf Beenden warten.
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Strg+C empfangen, beende ...")
        finally:
            self.cleanup()

    def cleanup(self):
        """Gibt alle Ressourcen sauber frei."""
        logger.info("Raeume Ressourcen auf ...")

        # Falls noch eine Aufnahme laeuft, stoppen
        if self.camera is not None:
            try:
                # stop_recording() wirft, falls nicht aktiv aufgenommen wird
                self.camera.stop_recording()
            except Exception:
                pass
            try:
                self.camera.close()
                logger.info("Kamera geschlossen.")
            except Exception as exc:
                logger.warning("Fehler beim Schliessen der Kamera: %s", exc)

        if self.pir is not None:
            try:
                self.pir.close()
                logger.info("PIR-Sensor freigegeben.")
            except Exception as exc:
                logger.warning("Fehler beim Schliessen des PIR: %s", exc)

        if self.db_conn is not None and self.db_conn.is_connected():
            try:
                self.db_conn.close()
                logger.info("Datenbankverbindung geschlossen.")
            except MySQLError as exc:
                logger.warning("Fehler beim Schliessen der DB: %s", exc)

        logger.info("Beendet.")


def main():
    recorder = MotionRecorder()

    # SIGTERM ebenfalls sauber behandeln (z.B. bei systemctl stop)
    def handle_sigterm(signum, frame):
        recorder.running = False

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        recorder.run()
    except Exception as exc:
        logger.critical("Schwerwiegender Fehler: %s", exc)
        recorder.cleanup()
        sys.exit(1)


if __name__ == "__main__":
    main()