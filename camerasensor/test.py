from gpiozero import MotionSensor
from signal import pause
import time

pir = MotionSensor(17)

while True:
    print(pir.motion_detected)
    time.sleep(1)   