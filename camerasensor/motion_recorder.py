#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
motion_recorder.py

Laeuft auf dem Raspberry Pi 4 im Restaurant (Asia All You Can Eat).
Kamera haengt ueber dem Eingang – sobald der PIR-Sensor eine Bewegung
meldet wird ein 5-Sekunden-Video aufgenommen, als MP4 gespeichert
und in der Datenbank eingetragen.

Hardware:
  - PIR-Sensor (HW-416) an GPIO18
  - Pi Camera V1.3 per CSI-Kabel

Braucht: picamera2, gpiozero, mysql-connector-python, ffmpeg
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


# Konfiguration
PIR_GPIO_PIN = 18
RECORD_SECONDS = 5
RECORDINGS_DIR = "/home/it/pi_project_vre/recordings"

# Datenbank-Zugangsdaten (MariaDB, laeuft lokal auf dem Pi)
DB_HOST = "localhost"
DB_PORT = 3306
DB_NAME = "motion_detection"
DB_USER = "motion_user"
DB_PASSWORD = "test123"


# Logging-Setup – alles landet im Terminal damit man es live verfolgen kann
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
        self.is_recording = False
        self.running = True
        self._record_lock = False

    # -- Setup --

    def setup_directory(self):
        # Aufnahmeordner anlegen falls er noch nicht existiert
        try:
            os.makedirs(RECORDINGS_DIR, exist_ok=True)
            logger.info("Aufnahmeverzeichnis bereit: %s", RECORDINGS_DIR)
        except OSError as exc:
            logger.error("Konnte Verzeichnis nicht anlegen: %s", exc)
            raise

    def setup_camera(self):
        # Kamera initialisieren – 720p reicht fuer den Eingang
        try:
            self.camera = Picamera2()
            video_config = self.camera.create_video_configuration(
                main={"size": (1280, 720)}
            )
            self.camera.configure(video_config)
            logger.info("Kamera initialisiert (picamera2).")
        except Exception as exc:
            logger.error("Kamera-Initialisierung fehlgeschlagen: %s", exc)
            raise

    def setup_pir(self):
        # PIR-Sensor einrichten und kurz warten damit er sich einpegelt
        try:
            self.pir = MotionSensor(PIR_GPIO_PIN)
            logger.info("PIR-Sensor an GPIO%d wird kalibriert ...", PIR_GPIO_PIN)
            # 5 Sekunden warten bis der Sensor stabil ist, sonst gibt es Fehlalarme
            self.pir.wait_for_no_motion(timeout=5)
            self.pir.when_motion = self.on_motion
            logger.info("PIR-Sensor bereit. Warte auf Bewegung ...")
        except Exception as exc:
            logger.error("PIR-Initialisierung fehlgeschlagen: %s", exc)
            raise

    def setup_database(self):
        # Verbindung zur lokalen MariaDB herstellen
        try:
            self.db_conn = mysql.connector.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
            if self.db_conn.is_connected():
                logger.info("Datenbankverbindung zu '%s' hergestellt.", DB_NAME)
        except MySQLError as exc:
            logger.error("Datenbankverbindung fehlgeschlagen: %s", exc)
            raise

    # -- Kernlogik --

    def on_motion(self):
        # wird aufgerufen sobald der PIR-Sensor anschlaegt
        if self.is_recording:
            # laeuft bereits eine Aufnahme, ignorieren
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
        """Video aufnehmen, zu MP4 konvertieren und in DB speichern."""
        timestamp = datetime.now()
        ts_string = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
        base_name = f"motion_{ts_string}"

        h264_path = os.path.join(RECORDINGS_DIR, base_name + ".h264")
        mp4_path = os.path.join(RECORDINGS_DIR, base_name + ".mp4")

        logger.info("Aufnahme gestartet (%d Sekunden)...", RECORD_SECONDS)

        try:
            encoder = H264Encoder(bitrate=10_000_000)

            self.camera.start()
            time.sleep(1)  # kurz warten damit die Kamera hochfahren kann

            self.camera.start_recording(encoder, FileOutput(h264_path))
            time.sleep(RECORD_SECONDS)
            self.camera.stop_recording()
            self.camera.stop()

            logger.info("Aufnahme beendet: %s", h264_path)
            time.sleep(1)

        except Exception as exc:
            logger.error("Fehler waehrend der Aufnahme: %s", exc)
            try:
                self.camera.stop_recording()
            except Exception:
                pass
            try:
                self.camera.stop()
            except Exception:
                pass
            return

        if not os.path.exists(h264_path):
            logger.error("H264-Datei wurde nicht erstellt.")
            return

        if os.path.getsize(h264_path) < 1000:
            logger.error("H264-Datei ist leer oder beschaedigt.")
            return

        # h264 -> mp4 damit der Browser die Videos spaeter abspielen kann
        if not self.convert_to_mp4(h264_path, mp4_path):
            logger.error("MP4-Konvertierung fehlgeschlagen.")
            return

        # TODO: vielleicht noch ein Thumbnail erstellen fuer das Dashboard

        self.insert_db_record(timestamp, base_name + ".mp4", mp4_path)
        logger.info("Aufnahme erfolgreich gespeichert.")

    def convert_to_mp4(self, h264_path, mp4_path):
        # ffmpeg-Aufruf: h264-Rohdaten in einen MP4-Container packen
        try:
            command = [
                "ffmpeg",
                "-y",
                "-framerate", "30",
                "-i", h264_path,
                "-c:v", "copy",
                mp4_path,
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error("ffmpeg Fehler:")
                logger.error(result.stderr)
                return False

            logger.info("MP4 erstellt: %s", mp4_path)

            if os.path.exists(h264_path):
                os.remove(h264_path)

            return True

        except Exception as exc:
            logger.error("Konvertierungsfehler: %s", exc)
            return False

    def insert_db_record(self, timestamp, dateiname, dateipfad):
        # Aufnahme in die Datenbank eintragen
        cursor = None
        try:
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
            logger.info("DB-Eintrag erfolgreich (ID %s): %s", cursor.lastrowid, dateiname)

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

    # -- Lebenszyklus --

    def run(self):
        """Alles initialisieren und dann auf Bewegungen warten."""
        self.setup_directory()
        self.setup_database()
        self.setup_camera()
        self.setup_pir()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Strg+C empfangen, beende ...")
        finally:
            self.cleanup()

    def cleanup(self):
        # Ressourcen ordentlich freigeben beim Beenden
        logger.info("Raeume Ressourcen auf ...")

        if self.camera is not None:
            try:
                self.camera.stop_recording()
                self.camera.stop()
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