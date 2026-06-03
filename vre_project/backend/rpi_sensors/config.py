# Konfiguration fuer alle Sensoren am Raspberry Pi.
# Wird von bme680_sensor.py und motion_sensor.py importiert.

import RPi.GPIO as GPIO

# BCM-Nummerierung: GPIO-Pins werden nach Chip-Nummerierung angesprochen,
# nicht nach physischer Pin-Position auf der Leiste.
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)  # Warnungen deaktivieren falls Pins schon initialisiert waren

# PIR-Bewegungssensor (RCWL-0516 Mikrowellen-Sensor) an GPIO17
PIR_PIN = 17
GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# BME680 Oversampling: hoehere Werte = genauere Messung, aber laengere Messzeit.
# Oversampling x2/x4/x8 sind typische Werte fuer gutes Rauschen/Geschwindigkeit-Verhaeltnis.
BME_HUMIDITY_OS = 2      # x2 Oversampling fuer Feuchtigkeit
BME_PRESSURE_OS = 4      # x4 Oversampling fuer Luftdruck
BME_TEMPERATURE_OS = 8   # x8 Oversampling fuer Temperatur (hoeher wegen Eigenwaerme des Chips)
BME_FILTER_SIZE = 3      # IIR-Filter glaettet kurze Druckspitzen (z.B. Tueroeffnen)

# Gasheizung: der BME680 heizt ein Messelement auf Temperatur um VOC zu messen.
# 320 °C / 200 ms sind die vom Hersteller empfohlenen Standardwerte.
GAS_HEATER_TEMP = 320    # Grad Celsius
GAS_HEATER_DURATION = 200  # Millisekunden
