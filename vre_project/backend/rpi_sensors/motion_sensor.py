"""
Bewegungserkennung per RCWL-0516 Mikrowellen-Sensor.

Der RCWL-0516 ist kein klassischer PIR-Sensor sondern nutzt Mikrowellen (3.2 GHz),
um Bewegungen zu erkennen. Das hat den Vorteil dass er durch Waende und Hindernisse
hindurchsehen kann – fuer den Restauranteingang ausreichend.
GPIO-Pin und Initialisierung werden in config.py vorgenommen.
"""

import time
from datetime import datetime
import RPi.GPIO as GPIO
from .config import PIR_PIN


def ist_bewegung():
    """Gibt True zurueck wenn der Sensor gerade eine Bewegung erkennt."""
    return GPIO.input(PIR_PIN) == GPIO.HIGH


def bewegung_ueberwachen(intervall=1, aufwaermzeit=5):
    """Endlosschleife fuer manuellen Test: gibt Bewegungsstatus auf der Konsole aus.

    Der Sensor braucht ein paar Sekunden zum Einpegeln (aufwaermzeit),
    sonst liefert er beim Start Fehlalarme.
    intervall: Sekunden zwischen den Abfragen
    """
    print("Sensor wird kalibriert, warte", aufwaermzeit, "Sekunden...")
    time.sleep(aufwaermzeit)
    try:
        while True:
            jetzt = datetime.now().strftime('%H:%M:%S')

            if ist_bewegung():
                print(f"[{jetzt}] Bewegung erkannt!")
            else:
                print(f"[{jetzt}] Keine Bewegung")

            time.sleep(intervall)

    except KeyboardInterrupt:
        print()  # Zeilenumbruch nach dem ^C


if __name__ == "__main__":
    bewegung_ueberwachen()