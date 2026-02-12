# Sensor-Initialisierung und Lesefunktionen (BME680 + PIR)

import RPi.GPIO as GPIO
import time
import bme680
from datetime import datetime

SENSOR_PIN = 17

GPIO.setmode(GPIO.BCM)
GPIO.setup(SENSOR_PIN, GPIO.IN)
print("GPIO initialisiert (Pin 17)")

sensor = None
try:
    sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    print("BME680 Sensor gefunden (Adresse 0x76)")
except (RuntimeError, IOError):
    try:
        sensor = bme680.BME680(bme680.I2C_ADDR_SECONDARY)
        print("BME680 Sensor gefunden (Adresse 0x77)")
    except Exception as e:
        print(f"BME680 Sensor nicht gefunden: {e}")
        sensor = None

if sensor:
    sensor.set_humidity_oversample(bme680.OS_2X)
    sensor.set_pressure_oversample(bme680.OS_4X)
    sensor.set_temperature_oversample(bme680.OS_8X)
    sensor.set_filter(bme680.FILTER_SIZE_3)
    sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
    sensor.set_gas_heater_temperature(320)
    sensor.set_gas_heater_duration(200)
    sensor.select_gas_heater_profile(0)
    print("BME680 Sensor konfiguriert")


def bewegung():
    print("\n--- Starte Bewegungserkennung ---")
    time.sleep(2)
    try:
        while True:
            status = GPIO.input(SENSOR_PIN)
            if status == GPIO.HIGH:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Bewegung erkannt!")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Keine Bewegung")
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nBeendet")
        GPIO.cleanup()


def temperatur():
    print("\n--- Starte Temperaturmessung ---")
    if sensor is None:
        print("Fehler: BME680 Sensor nicht verfuegbar!")
        return
    try:
        while True:
            if sensor.get_sensor_data():
                output = "Temp: {0:.2f} C | Druck: {1:.2f} hPa | Feuchtigkeit: {2:.2f} %RH".format(
                    sensor.data.temperature, sensor.data.pressure, sensor.data.humidity)
                if sensor.data.heat_stable and sensor.data.gas_resistance is not None:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {output} | Gas: {sensor.data.gas_resistance:.0f} Ohms")
                else:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {output} | Gas: (aufwaermen...)")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nBeendet")
        GPIO.cleanup()


def read_all_sensors():
    data = {
        'temperature': None, 'pressure': None, 'humidity': None,
        'gas_resistance': None, 'movement_detected': False
    }

    if sensor:
        for attempt in range(10):
            if sensor.get_sensor_data():
                data['temperature'] = round(sensor.data.temperature, 2)
                data['pressure'] = round(sensor.data.pressure, 2)
                data['humidity'] = round(sensor.data.humidity, 2)
                if sensor.data.heat_stable and sensor.data.gas_resistance is not None:
                    data['gas_resistance'] = round(sensor.data.gas_resistance, 2)
                print(f"  BME680: {data['temperature']} C | {data['pressure']} hPa | "
                      f"{data['humidity']} %RH | Gas: {data['gas_resistance'] or '(aufwaermen...)'}")
                break
            time.sleep(1)
        else:
            print("  BME680: Keine Daten nach 10 Versuchen")
    else:
        print("  BME680: Sensor nicht verfuegbar")

    status = GPIO.input(SENSOR_PIN)
    data['movement_detected'] = status == GPIO.HIGH
    print(f"  PIR: {'Bewegung erkannt!' if data['movement_detected'] else 'Keine Bewegung'}")
    return data
