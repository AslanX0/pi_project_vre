import numpy as np
import math
import json
import os
from datetime import datetime

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration.json")
REGRESSION_FILE = os.path.join(os.path.dirname(__file__), "regression_model.json")

MAX_PERSONS = 120
MIN_PERSONS = 0

# Standardwerte: leerer Raum bei 20°C, voller Raum (120 Personen) bei 30°C
DEFAULT_BASELINE_TEMP = 20.0
DEFAULT_FULL_TEMP = 30.0


class PersonEstimator:
    """Schätzt Personenanzahl linear aus der Raumtemperatur.
    Kalibrierung: set_baseline() bei leerem Raum, set_full_temp() bei vollem Raum aufrufen.
    """

    def __init__(self):
        self.baseline_temp = DEFAULT_BASELINE_TEMP
        self.full_temp = DEFAULT_FULL_TEMP
        self.calibrated = False
        self.calibration_date = None
        self._load_calibration()

    def _load_calibration(self):
        if not os.path.exists(CALIBRATION_FILE):
            return
        try:
            with open(CALIBRATION_FILE, "r") as f:
                data = json.load(f)
            b = data.get("baseline", {})
            if "baseline_temp" in b:
                self.baseline_temp = b.get("baseline_temp", DEFAULT_BASELINE_TEMP)
                self.full_temp = b.get("full_temp", DEFAULT_FULL_TEMP)
                self.calibrated = b.get("calibrated", False)
                self.calibration_date = b.get("calibration_date")
        except Exception as e:
            print(f"Fehler beim Laden der Kalibrierung: {e}")

    def _save_calibration(self):
        with open(CALIBRATION_FILE, "w") as f:
            json.dump({"baseline": {
                "baseline_temp": self.baseline_temp,
                "full_temp": self.full_temp,
                "calibrated": self.calibrated,
                "calibration_date": self.calibration_date
            }}, f, indent=2, default=str)

    def set_baseline(self, temperature):
        """Leerer Raum: aktuelle Temperatur als Nullpunkt setzen."""
        self.baseline_temp = temperature
        self.calibrated = True
        self.calibration_date = datetime.now().isoformat()
        self._save_calibration()

    def set_full_temp(self, temperature):
        """Voller Raum (120 Personen): Temperatur bei maximaler Belegung setzen."""
        self.full_temp = temperature
        self._save_calibration()

    def estimate(self, temperature):
        """Schätzt Personenanzahl aus der Raumtemperatur (lineare Interpolation)."""
        if temperature is None:
            return {"estimated_persons": 0}

        temp_range = self.full_temp - self.baseline_temp
        if temp_range <= 0:
            return {"estimated_persons": 0}

        raw = (temperature - self.baseline_temp) / temp_range * MAX_PERSONS
        estimated = int(np.clip(round(raw), MIN_PERSONS, MAX_PERSONS))

        return {
            "estimated_persons": estimated,
            "temperature_used": temperature,
            "baseline_temp": self.baseline_temp,
            "full_temp": self.full_temp
        }

    def get_ac_mode(self, estimated_persons):
        """Empfohlener Klimaanlagenmodus: 0=Aus, 1-5 (linear nach Personenzahl)."""
        if estimated_persons <= 0:
            return 0
        return min(5, max(1, math.ceil(estimated_persons / 24)))

    def get_status(self):
        return {
            "baseline_temp": self.baseline_temp,
            "full_temp": self.full_temp,
            "calibrated": self.calibrated,
            "calibration_date": self.calibration_date,
            "max_persons": MAX_PERSONS
        }


class TemperatureRegression:
    """
    Lineare Regression: Zeit -> Raumtemperatur
    X = Stunden seit erstem Datenpunkt, Y = Temperatur in °C
    """

    def __init__(self):
        self.slope = None
        self.intercept = None
        self.r_squared = None
        self.n_samples = 0
        self.trained_at = None
        self.last_error = None
        self.epoch_offset = None  # Unix-Timestamp des ersten Datenpunkts (Sekunden)
        self._load_model()

    def train(self, x_list, temperature_list, epoch_offset=None):
        """Trainiert das Modell. x_list: Stunden seit erstem Datenpunkt."""
        if len(x_list) < 3:
            return False

        x = np.array(x_list, dtype=float)
        y = np.array(temperature_list, dtype=float)
        n = len(x)

        sum_x, sum_y = np.sum(x), np.sum(y)
        sum_xy = np.sum(x * y)
        sum_x2 = np.sum(x ** 2)

        denom = n * sum_x2 - sum_x ** 2
        if denom == 0:
            return False

        self.slope = float((n * sum_xy - sum_x * sum_y) / denom)
        self.intercept = float((sum_y - self.slope * sum_x) / n)

        y_pred = self.slope * x + self.intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        self.r_squared = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0

        self.n_samples = n
        self.trained_at = datetime.now().isoformat()
        if epoch_offset is not None:
            self.epoch_offset = epoch_offset
        self._save_model()
        return True

    def _save_model(self):
        try:
            with open(REGRESSION_FILE, "w") as f:
                json.dump({
                    "slope": self.slope,
                    "intercept": self.intercept,
                    "r_squared": self.r_squared,
                    "n_samples": self.n_samples,
                    "trained_at": self.trained_at,
                    "epoch_offset": self.epoch_offset
                }, f, indent=2)
        except Exception as e:
            print(f"[Regression] Fehler beim Speichern: {e}")

    def _load_model(self):
        if not os.path.exists(REGRESSION_FILE):
            return
        try:
            with open(REGRESSION_FILE, "r") as f:
                data = json.load(f)
            self.slope = data.get("slope")
            self.intercept = data.get("intercept")
            self.r_squared = data.get("r_squared")
            self.n_samples = data.get("n_samples", 0)
            self.trained_at = data.get("trained_at")
            self.epoch_offset = data.get("epoch_offset")
            if self.slope is not None:
                print(f"[Regression] Modell geladen (R²={self.r_squared}, n={self.n_samples})")
        except Exception as e:
            print(f"[Regression] Fehler beim Laden: {e}")

    def predict(self, x_hours):
        """Gibt vorhergesagte Temperatur für x Stunden seit epoch_offset zurück."""
        if self.slope is None:
            return None
        return round(self.slope * x_hours + self.intercept, 2)

    def get_status(self):
        return {
            "trained": self.slope is not None,
            "slope": round(self.slope, 6) if self.slope is not None else None,
            "intercept": round(self.intercept, 4) if self.intercept is not None else None,
            "r_squared": round(self.r_squared, 4) if self.r_squared is not None else None,
            "n_samples": self.n_samples,
            "trained_at": self.trained_at,
            "scenarios": None
        }