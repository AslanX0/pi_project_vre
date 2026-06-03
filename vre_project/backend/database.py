"""
Datenbankverbindung fuer das Restaurant-Sensor-Dashboard.

Alle Routen importieren get_db_connection() von hier.
Jede Route oeffnet eine eigene kurzlebige Verbindung und schliesst
sie im finally-Block wieder – keine persistente Verbindung, damit
der Server bei einem Verbindungsabbruch nicht einfriert.
"""
import pymysql

# DictCursor sorgt dafuer dass Abfrageergebnisse als Dictionary zurueckkommen
# (z.B. row['temperature'] statt row[3]) – lesbarer und weniger fehleranfaellig.
db_config = {'host':'localhost','port':3306,'user':'root','password':'root','database':'sensor_db','charset':'utf8mb4','cursorclass':pymysql.cursors.DictCursor}


def get_db_connection():
    """Oeffnet eine neue Datenbankverbindung und gibt sie zurueck.

    Bei Verbindungsfehler wird None zurueckgegeben statt eine Exception zu werfen,
    damit die aufrufenden Routen mit einem sauberen HTTP-500 antworten koennen.
    """
    try: return pymysql.connect(**db_config)
    except pymysql.Error as e: print(f"DB-KEINE VERBINDUNG: {e}"); return None
