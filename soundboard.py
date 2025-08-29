import time
from evdev import InputDevice, list_devices, categorize, ecodes

devices = [InputDevice(path) for path in list_devices()]
for dev in devices:
    print(dev.path, dev.name)

kb = InputDevice('/dev/input/eventX')   # replace X with your keyboard from list above
kb.grab()
print("Keyboard grabbed. Press some keys...")

try:
    for event in kb.read_loop():
        if event.type == ecodes.EV_KEY:
            e = categorize(event)
            if e.keystate == e.key_down:
                print("Key:", e.keycode)
except KeyboardInterrupt:
    kb.ungrab()
    print("Released and exiting")
