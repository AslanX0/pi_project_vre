-- setup_database.sql
-- Erstellt die Datenbank und Tabelle fuer das Bewegungs-Aufnahmesystem.
-- Ausfuehren mit: sudo mariadb < setup_database.sql

-- Datenbank anlegen
CREATE DATABASE IF NOT EXISTS motion_detection
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE motion_detection;

-- Tabelle fuer die Aufnahmen
CREATE TABLE IF NOT EXISTS recordings (
                                          id          INT AUTO_INCREMENT PRIMARY KEY,
                                          timestamp   DATETIME      NOT NULL,
                                          dateiname   VARCHAR(255)  NOT NULL,
    dateipfad   VARCHAR(512)  NOT NULL
    );

-- Optional: dedizierten Datenbank-Benutzer anlegen (Passwort anpassen!)
-- Die Zugangsdaten muessen mit den Konstanten im Python-Skript uebereinstimmen.
CREATE USER IF NOT EXISTS 'motion_user'@'localhost'
    IDENTIFIED BY 'DEIN_PASSWORT_HIER';

GRANT SELECT, INSERT, UPDATE, DELETE
      ON motion_detection.recordings
          TO 'motion_user'@'localhost';

FLUSH PRIVILEGES;