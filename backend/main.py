# Hauptskript - Raspberry Pi Sensorstation (BME680 + PIR, speichert in MariaDB)

import RPi.GPIO as GPIO
import mariadb
import sys
import time
from datetime import datetime

from sensors import read_all_sensors, bewegung, temperatur

db_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root',
    'database': 'sensor_db'
}

try:
    conn = mariadb.connect(**db_config)
    cursor = conn.cursor()
    print("Datenbankverbindung erfolgreich!")
except mariadb.Error as e:
    print(f"Fehler bei Datenbankverbindung: {e}")
    sys.exit(1)

cursor.execute("""
CREATE TABLE IF NOT EXISTS sensor_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    temperature FLOAT NOT NULL,
    pressure FLOAT,
    humidity FLOAT,
    gas_resistance FLOAT,
    movement_detected BOOLEAN NOT NULL,
    estimated_occupancy INT DEFAULT NULL,
    ac_recommendation INT DEFAULT NULL,
    data_source CHAR(4) NOT NULL DEFAULT 'REAL'
)
""")
conn.commit()

for col_sql in [
    "ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS estimated_occupancy INT DEFAULT NULL",
    "ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS ac_recommendation INT DEFAULT NULL",
    "ALTER TABLE sensor_data ADD COLUMN IF NOT EXISTS data_source CHAR(4) NOT NULL DEFAULT 'REAL'"
]:
    try:
        cursor.execute(col_sql)
        conn.commit()
    except mariadb.Error:
        pass

print("Datenbank-Schema aktualisiert")


def main_loop():
    print("\n--- Starte Hauptschleife (Alle Sensoren + Datenbank) ---")
    print("Druecke STRG+C zum Beenden.\n")
    INTERVALL = 300

    try:
        while True:
            timestamp = datetime.now()
            print(f"\n[{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] Lese Sensoren...")
            data = read_all_sensors()

            if data['temperature'] is not None:
                cursor.execute(
                    """INSERT INTO sensor_data
                       (timestamp, temperature, pressure, humidity, gas_resistance,
                        movement_detected, data_source)
                       VALUES (?, ?, ?, ?, ?, ?, 'REAL')""",
                    (timestamp, data['temperature'], data['pressure'],
                     data['humidity'], data['gas_resistance'], data['movement_detected'])
                )
                conn.commit()
                print(f"  => Daten gespeichert! (Quelle: REAL)")
            else:
                print("  => Keine Temperaturdaten - nicht gespeichert.")

            print(f"  Naechste Messung in {INTERVALL} Sekunden...")
            time.sleep(INTERVALL)
    except KeyboardInterrupt:
        GPIO.cleanup()
        conn.close()
        print("Verbindung geschlossen. Auf Wiedersehen!")


def show_last_entries(count=10):
    print(f"\n--- Letzte {count} Eintraege aus der Datenbank ---\n")
    cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?", (count,))
    rows = cursor.fetchall()

    if rows:
        print(f"{'ID':<5} {'Timestamp':<20} {'Temp':>8} {'Druck':>10} {'Feucht.':>8} "
              f"{'Gas':>12} {'Bew.':<6} {'Gaeste':>7} {'AC':>4} {'Quelle':<6}")
        print("-" * 100)
        for row in rows:
            mov = "Ja" if row[6] else "Nein"
            gas = f"{row[5]:.0f}" if row[5] else "N/A"
            occ = str(row[7]) if row[7] is not None else "-"
            ac = str(row[8]) if row[8] is not None else "-"
            src = row[9] if len(row) > 9 and row[9] else "REAL"
            print(f"{row[0]:<5} {str(row[1]):<20} {row[2]:>7.2f}C {row[3]:>9.2f} "
                  f"{row[4]:>7.2f}% {gas:>12} {mov:<6} {occ:>7} {ac:>4} {src:<6}")
    else:
        print("Keine Eintraege vorhanden.")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("   RASPBERRY PI SENSOR STATION")
    print("   BME680 (Temp/Druck/Feuchtigkeit/Gas) + PIR")
    print("=" * 50)

    print("\nWaehle eine Funktion:\n")
    print("  1 - Nur Bewegungssensor (PIR)")
    print("  2 - Nur Umweltsensor (BME680)")
    print("  3 - Alle Sensoren + Datenbank speichern")
    print("  4 - Letzte Datenbankeintraege anzeigen")
    print("  0 - Beenden")

    wahl = input("\nDeine Wahl: ").strip()

    if wahl == "1":
        bewegung()
    elif wahl == "2":
        temperatur()
    elif wahl == "3":
        main_loop()
    elif wahl == "4":
        show_last_entries(10)
    elif wahl == "0":
        print("Auf Wiedersehen!")
    else:
        print("Ungueltige Eingabe!")

    GPIO.cleanup()
    try:
        conn.close()
    except:
        pass
