# Datenbank-Konfiguration und Verbindung

import pymysql

db_config = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': 'root',
    'database': 'sensor_db',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


def get_db_connection():
    try:
        return pymysql.connect(**db_config)
    except pymysql.Error as e:
        print(f"Fehler bei Datenbankverbindung: {e}")
        return None
