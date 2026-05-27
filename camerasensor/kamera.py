from picamera2 import Picamera2
import time

# Kamera initialisieren
picam2 = Picamera2()

# Konfiguration für Foto laden und starten
picam2.create_still_configuration()
picam2.start()

# Kurz warten, damit Belichtung und Autofokus sich einstellen können
time.sleep(2)

# Ein Bild aufnehmen und speichern (mit Anführungszeichen um den Dateinamen)
picam2.capture_file("mein_foto.jpg")

# Kamera beenden
picam2.stop()
