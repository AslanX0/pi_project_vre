import time
import RPi.GPIO as GPIO

sensor_pin = 18

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(sensor_pin, GPIO.IN)

last_state = False

try:
    while True:
        current = GPIO.input(sensor_pin)
        
        if current and not last_state:
            print("Bewegung erkannt")
        if not current and last_state:
            print("Ruhe")
            
        last_state = current
        time.sleep(0.2)

except KeyboardInterrupt:
    print("Programm beendet")
    GPIO.cleanup()
