"""
BME680 Umweltsensor – Temperatur, Luftdruck, Feuchtigkeit und Gasqualität.
"""

import bme680
from .config import (
    BME_HUMIDITY_OS,
    BME_PRESSURE_OS, 
    BME_TEMPERATURE_OS,
    BME_FILTER_SIZE,
    GAS_HEATER_TEMP,
    GAS_HEATER_DURATION
)

_sensor = None


def _initialisieren():
    """Sucht und konfiguriert den Sensor."""
    global _sensor
    
    for adresse in [bme680.I2C_ADDR_PRIMARY, bme680.I2C_ADDR_SECONDARY]:
        try:
            _sensor = bme680.BME680(adresse)
            break
        except (RuntimeError, IOError):
            continue
    
    if _sensor is None:
        return
    
    _sensor.set_humidity_oversample(BME_HUMIDITY_OS)
    _sensor.set_pressure_oversample(BME_PRESSURE_OS)
    _sensor.set_temperature_oversample(BME_TEMPERATURE_OS)
    _sensor.set_filter(BME_FILTER_SIZE)
    _sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)
    _sensor.set_gas_heater_temperature(GAS_HEATER_TEMP)
    _sensor.set_gas_heater_duration(GAS_HEATER_DURATION)
    _sensor.select_gas_heater_profile(0)


def messen():
    """
    Liest alle Sensordaten aus.
    
    Rückgabe: Dict mit temperatur, druck, feuchtigkeit, gas
              oder None wenn Sensor nicht verfügbar.
    """
    if _sensor is None:
        _initialisieren()
    
    if _sensor is None or not _sensor.get_sensor_data():
        return None
    
    daten = _sensor.data
    
    return {
        'temperatur': round(daten.temperature, 2),
        'druck': round(daten.pressure, 2),
        'feuchtigkeit': round(daten.humidity, 2),
        'gas': round(daten.gas_resistance, 2) if daten.heat_stable and daten.gas_resistance else None
    }


def messen_intervall(intervall=5, callback=None):
    """
    Liest Sensordaten in regelmäßigen Abständen.
    
    intervall: Sekunden zwischen Messungen
    callback:  Funktion die mit den Daten aufgerufen wird (optional)
    """
    import time
    
    while True:
        daten = messen()
        
        if callback and daten:
            callback(daten)
        
        time.sleep(intervall)