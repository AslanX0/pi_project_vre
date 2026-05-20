"""
Bewegungssensor am Raspberry Pi.
"""

import time
from datetime import datetime
import RPi.GPIO as GPIO
from .config import PIR_PIN


def ist_bewegung():
    return GPIO.input(PIR_PIN) == GPIO.HIGH


def bewegung_ueberwachen(intervall=1, aufwaermzeit=5):

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
        print()


if __name__ == "__main__":
    bewegung_ueberwachen()