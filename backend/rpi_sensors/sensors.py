"""
Kombinierte Abfrage aller Sensoren.
"""

import time
from .motion_sensor import ist_bewegung
from .bme680_sensor import messen


def alle_sensoren_auslesen(versuche=10):
    """
    Liest PIR und BME680 aus.
    
    Rückgabe: Dict mit temperatur, druck, feuchtigkeit, gas, bewegung
    """
    ergebnis = {
        'temperatur': None,
        'druck': None,
        'feuchtigkeit': None,
        'gas': None,
        'bewegung': False
    }
    
    for _ in range(versuche):
        daten = messen()
        if daten:
            ergebnis.update(daten)
            break
        time.sleep(1)
    
    ergebnis['bewegung'] = ist_bewegung()
    
    return ergebnis


def alle_sensoren_intervall(intervall=5, callback=None):
    """
    Liest alle Sensoren in regelmäßigen Abständen.
    
    intervall: Sekunden zwischen Messungen
    callback:  Funktion die mit den Daten aufgerufen wird (optional)
    """
    while True:
        daten = alle_sensoren_auslesen()
        
        if callback:
            callback(daten)
        
        time.sleep(intervall)