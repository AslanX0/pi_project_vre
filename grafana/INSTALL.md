# Grafana Installation und Einrichtung

## 1. Grafana installieren (Windows)

1. Herunterladen: https://grafana.com/grafana/download?platform=windows
2. MSI-Installer ausfuehren
3. Grafana startet automatisch als Windows-Dienst
4. Browser oeffnen: http://localhost:3000
5. Login: `admin` / `admin` (beim ersten Login neues Passwort setzen)

## 2. MariaDB Datenquelle einrichten

1. Im Menue: **Connections** > **Data Sources** > **Add data source**
2. Typ waehlen: **MySQL**
3. Einstellungen:
   - **Name:** `MariaDB`
   - **Host:** `localhost:3306`
   - **Database:** `sensor_db`
   - **User:** `root`
   - **Password:** `root`
4. **Save & Test** klicken - muss "Database Connection OK" zeigen

## 3. Dashboard importieren

1. Im Menue: **Dashboards** > **New** > **Import**
2. Datei hochladen: `grafana/dashboard.json`
3. Bei "MariaDB" die eben erstellte Datenquelle waehlen
4. **Import** klicken

## 4. FastAPI Server starten

```bash
pip install fastapi uvicorn[standard] pymysql numpy
cd backend
python app.py
```

Server laeuft auf http://localhost:5000

Der Hintergrund-Estimator berechnet automatisch alle 60 Sekunden die Personenschaetzung fuer neue Datensaetze.

## 5. API-Dokumentation

FastAPI generiert automatisch eine interaktive API-Dokumentation:

- Swagger UI: http://localhost:5000/docs
- ReDoc: http://localhost:5000/redoc

## Ports

| Dienst  | Port |
|---------|------|
| Grafana | 3000 |
| FastAPI | 5000 |
| MariaDB | 3306 |
