#Konfiguration für die Sensoren.

import RPi.GPIO as GPIO

# GPIO-Modus und Warnungen
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# PIR-Sensor
PIR_PIN = 17
GPIO.setup(PIR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# BME680 Oversampling und Filter
BME_HUMIDITY_OS = 2    
BME_PRESSURE_OS = 4      
BME_TEMPERATURE_OS = 8   
BME_FILTER_SIZE = 3

# Gasheizung
GAS_HEATER_TEMP = 320    # Grad Celsius
GAS_HEATER_DURATION = 200  # Millisekunden
