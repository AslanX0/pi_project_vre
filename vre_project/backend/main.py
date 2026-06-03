# Raspberry Pi Sensorstation – BME680 + PIR mit MariaDB-Anbindung
#
# Dieses Skript ist das direkte Testprogramm fuer den Raspberry Pi – nicht der FastAPI-Server.
# Es bietet ein einfaches Auswahlmenue um einzelne Sensoren oder den Vollbetrieb zu testen.
# Fuer den produktiven Dauerbetrieb wird stattdessen app.py (FastAPI) gestartet.

import sys, time
from datetime import datetime
import pymysql

import RPi.GPIO as GPIO
from vre_project.backend.rpi_sensors.sensors import alle_sensoren_auslesen
from vre_project.backend.rpi_sensors.motion_sensor import bewegung_ueberwachen
from vre_project.backend.rpi_sensors.bme680_sensor import messen_intervall

DB_CONFIG = {'host':'localhost','port':3306,'user':'root','password':'root','database':'sensor_db','cursorclass':pymysql.cursors.Cursor}
MESSINTERVALL = 300  # Sekunden zwischen zwei Messungen im Dauerbetrieb (5 Minuten)


def db_verbinden():
    """Verbindet mit der lokalen MariaDB. Bricht das Programm ab wenn die Verbindung fehlschlaegt."""
    try: return pymysql.connect(**DB_CONFIG)
    except pymysql.MySQLError as e: print(f"DB-Fehler: {e}"); sys.exit(1)


def tabelle_erstellen(cursor):
    """Legt die Messtabelle an, falls sie noch nicht existiert.
    estimated_occupancy und ac_recommendation werden spaeter vom FastAPI-Server befuellt.
    """
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


def daten_speichern(cursor, conn, daten):
    """Schreibt einen Messwert in die Datenbank.
    Wenn der BME680 noch keine Temperatur liefert (Aufwaermphase), wird der Datensatz uebersprungen.
    """
    if daten['temperatur'] is None:
        print("Keine Sensordaten – übersprungen")
        return
    cursor.execute(
        "INSERT INTO sensor_data (timestamp, temperature, pressure, humidity, gas_resistance, movement_detected) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (datetime.now(), daten['temperatur'], daten['druck'], daten['feuchtigkeit'], daten['gas'], daten['bewegung'])
    )
    conn.commit()
    print("Daten gespeichert")


def ausgabe(d):
    """Gibt einen Messwert leserlich auf der Konsole aus.
    Wenn der BME680-Gasheizung noch nicht stabil ist, wird '(aufheizen)' angezeigt.
    """
    gas = f"{d['gas']} Ω" if d['gas'] else "(aufheizen)"
    print(f"{d['temperatur']} °C | {d['druck']} hPa | {d['feuchtigkeit']} %RH | Gas: {gas}")


def hauptschleife(cursor, conn):
    """Dauerschleife: liest alle Sensoren und speichert sie in der Datenbank.
    Laeuft solange bis Strg+C gedrueckt wird.
    """
    try:
        while True:
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Lese Sensoren...")
            daten = alle_sensoren_auslesen()
            daten_speichern(cursor, conn, daten)
            print(f"Nächste Messung in {MESSINTERVALL}s")
            time.sleep(MESSINTERVALL)
    except KeyboardInterrupt:
        print("\nMessung beendet.")


if __name__ == "__main__":
    conn = db_verbinden()
    cursor = conn.cursor()
    tabelle_erstellen(cursor)
    conn.commit()

    # Einfaches Auswahlmenue zum direkten Testen einzelner Komponenten
    print("\n  1 - Bewegungssensor (PIR)\n  2 - Umweltsensor (BME680)\n  3 - Alle Sensoren + Datenbank\n  0 - Beenden\n")
    wahl = input("Auswahl: ").strip()

    aktionen = {
        "1": bewegung_ueberwachen,
        "2": lambda: messen_intervall(intervall=5, callback=ausgabe),
        "3": lambda: hauptschleife(cursor, conn),
        "0": lambda: print("Beendet.")
    }

    aktionen.get(wahl, lambda: print("Ungültige Eingabe"))()

    # GPIO-Pins zuruecksetzen, sonst bleiben sie belegt fuer den naechsten Aufruf
    GPIO.cleanup()
    try: conn.close()
    except: pass