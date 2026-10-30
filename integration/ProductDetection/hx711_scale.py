#!/usr/bin/env python3
"""HX711 + load cell: raw reading, tare, calibration, grams and a noise check.

Wiring (Raspberry Pi 5): DT -> GPIO5 (pin 29), SCK -> GPIO6 (pin 31),
VCC -> 3.3 V, GND -> GND.  Uses gpiozero, so it works on the Pi 5.

Usage:
  python3 hx711_scale.py raw             # raw numbers, to check the wiring
  python3 hx711_scale.py tare            # empty platform: saves the zero point
  python3 hx711_scale.py calibrate 200   # put a known weight (grams) on first
  python3 hx711_scale.py read            # prints the weight in grams
  python3 hx711_scale.py noise           # empty platform: noise and a suggested threshold

Not tested on real hardware yet.
"""
import json
import os
import statistics
import sys
import time

from gpiozero import DigitalInputDevice, DigitalOutputDevice

DT_PIN, SCK_PIN = 5, 6
CAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hx711_calibration.json")


class HX711:
    def __init__(self, dt_pin=DT_PIN, sck_pin=SCK_PIN):
        self.dt = DigitalInputDevice(dt_pin)
        self.sck = DigitalOutputDevice(sck_pin, initial_value=False)

    def read_raw(self, timeout=1.0):
        start = time.time()
        while self.dt.value:  # DT goes low when a reading is ready
            if time.time() - start > timeout:
                raise TimeoutError("HX711 not ready: check DT, SCK, power and the load cell wires")
            time.sleep(0.001)
        sck_on, sck_off, dt = self.sck.on, self.sck.off, self.dt
        value = 0
        for _ in range(24):  # 24 data bits, most significant first
            sck_on()
            sck_off()
            value = (value << 1) | dt.value
        sck_on()  # 25th pulse: the next reading uses channel A, gain 128
        sck_off()
        if value & 0x800000:  # negative number (two's complement)
            value -= 1 << 24
        return value


class Scale:
    def __init__(self, hx=None):
        self.hx = hx or HX711()
        self.offset = 0.0
        self.scale = 1.0  # raw counts per gram
        self.calibrated = False
        self.load()

    def load(self):
        if os.path.exists(CAL_FILE):
            with open(CAL_FILE) as f:
                data = json.load(f)
            self.offset = data["offset"]
            self.scale = data["scale"]
            self.calibrated = data.get("calibrated", False)

    def save(self):
        with open(CAL_FILE, "w") as f:
            json.dump({"offset": self.offset, "scale": self.scale, "calibrated": self.calibrated}, f, indent=2)

    def read_median(self, n=10):
        return statistics.median(self.hx.read_raw() for _ in range(n))

    def tare(self, n=20):
        self.offset = self.read_median(n)
        self.save()
        return self.offset

    def calibrate(self, known_g, n=20):
        if known_g <= 0:
            raise ValueError("The known weight must be more than 0 g")
        raw = self.read_median(n)
        scale = (raw - self.offset) / known_g
        if abs(scale) < 1e-6:
            raise ValueError("No change from the zero reading. Is the weight on the platform?")
        self.scale = scale
        self.calibrated = True
        self.save()
        return self.scale

    def grams(self, n=5):
        return (self.read_median(n) - self.offset) / self.scale


def noise_check(scale, n=40):
    values = [scale.grams(n=1) for _ in range(n)]
    mean, sd = statistics.mean(values), statistics.pstdev(values)
    spread = max(values) - min(values)
    print(f"Samples: {n}   mean: {mean:.2f} g   std: {sd:.2f} g   max-min: {spread:.2f} g")
    print(f"Pick a weight threshold above {max(5 * sd, 1.5 * spread):.1f} g (so noise never raises an alarm)")
    print("and below the weight of your lightest item.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    scale = Scale()
    try:
        if cmd == "raw":
            print("Press on the platform: the number should change. Ctrl+C to stop.")
            while True:
                raw = scale.hx.read_raw()
                warn = "   <- stuck value, check the wiring" if raw in (-1, 0x7FFFFF, -0x800000) else ""
                print(raw, warn)
                time.sleep(0.3)
        elif cmd == "tare":
            print("Keep the platform EMPTY and still...")
            print("Zero point saved:", scale.tare())
        elif cmd == "calibrate":
            if len(sys.argv) < 3:
                sys.exit("Usage: python3 hx711_scale.py calibrate <known weight in grams>")
            if not os.path.exists(CAL_FILE):
                sys.exit("Run 'tare' first (empty platform), then put the known weight on.")
            print("Keep the known weight still on the platform...")
            print("Scale saved (counts per gram):", scale.calibrate(float(sys.argv[2])))
        elif cmd == "read":
            if not scale.calibrated:
                print("Warning: not calibrated yet, so these numbers are not grams. Run tare and calibrate.")
            print("Ctrl+C to stop.")
            while True:
                print(f"{scale.grams():8.1f} g")
                time.sleep(0.3)
        elif cmd == "noise":
            print("Keep the platform EMPTY and still...")
            noise_check(scale)
        else:
            print(__doc__)
    except KeyboardInterrupt:
        print("\nStopped.")
    except TimeoutError as err:
        sys.exit(str(err))


if __name__ == "__main__":
    main()
