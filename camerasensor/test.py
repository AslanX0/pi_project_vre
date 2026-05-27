from gpiozero import MotionSensor
import time
pir = MotionSensor(17)
print('Sensor bereit. Bewege dich vor den Sensor...')
time.sleep(60)
while True:
    if pir.motion_detected:
        print('BEWEGUNG ERKANNT!')
    else:
        print('Keine Bewegung')
    time.sleep(0.5)
