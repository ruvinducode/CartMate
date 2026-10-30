#!/usr/bin/env python3
"""Take many photos for the YOLO dataset, one class at a time.

Examples:
  python3 capture_photos.py --source usb --label box --count 100
  python3 capture_photos.py --source pi  --label cylinder --count 100 --delay 3
  python3 capture_photos.py --source usb --label circular_object --count 20 --manual

Photos go to ~/smartcart_photos/<label>/<label>_001.jpg and so on. Running it again
continues the numbering, so nothing is overwritten.
Needs: opencv-python-headless (USB webcam) or picamera2 (Pi Camera).
Not tested on real hardware yet.
"""
import argparse
import glob
import os
import time

HINTS = [
    "change the ANGLE (front, side, rotated, tilted)",
    "change the DISTANCE (close, medium, far)",
    "change the LIGHTING (bright, dim, light from the side)",
    "change the BACKGROUND (table, cloth, cardboard)",
    "PARTLY HIDE the object behind another object",
    "put 2 or 3 objects in the same frame",
]


class UsbCamera:
    def __init__(self, index=0, size=(1280, 720)):
        import cv2
        self.cv2 = cv2
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise SystemExit("Cannot open the webcam. Check 'lsusb' and 'ls /dev/video*'.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        for _ in range(15):  # let the exposure settle
            self.cap.read()

    def capture(self, path):
        for _ in range(2):  # drop old buffered frames
            self.cap.grab()
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Could not read a frame from the webcam")
        self.cv2.imwrite(path, frame)

    def close(self):
        self.cap.release()


class PiCamera:
    def __init__(self, size=(1280, 720)):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        self.cam.configure(self.cam.create_still_configuration(main={"size": size}))
        self.cam.start()
        time.sleep(1.5)

    def capture(self, path):
        self.cam.capture_file(path)

    def close(self):
        self.cam.stop()
        self.cam.close()


def make_camera(source):
    return PiCamera() if source == "pi" else UsbCamera()


def next_index(folder, label):
    numbers = []
    for path in glob.glob(os.path.join(folder, f"{label}_*.jpg")):
        part = os.path.splitext(os.path.basename(path))[0].rsplit("_", 1)[-1]
        if part.isdigit():
            numbers.append(int(part))
    return max(numbers, default=0) + 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Capture dataset photos")
    ap.add_argument("--source", choices=["usb", "pi"], required=True)
    ap.add_argument("--label", required=True, help="class name, e.g. box")
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between photos")
    ap.add_argument("--hint-every", type=int, default=10, help="show a variation hint every N photos")
    ap.add_argument("--manual", action="store_true", help="press Enter for every photo")
    ap.add_argument("--out", default=os.path.expanduser("~/smartcart_photos"))
    args = ap.parse_args(argv)

    folder = os.path.join(args.out, args.label)
    os.makedirs(folder, exist_ok=True)
    start = next_index(folder, args.label)
    cam = make_camera(args.source)
    print(f"Saving to {folder}, starting at number {start}. Ctrl+C to stop.")
    try:
        for i in range(args.count):
            if i % args.hint_every == 0:
                hint = HINTS[(i // args.hint_every) % len(HINTS)]
                input(f"\n>>> Next {args.hint_every} photos: {hint}. Press Enter when ready... ")
            elif args.manual:
                input("Press Enter for the next photo... ")
            else:
                time.sleep(args.delay)
            path = os.path.join(folder, f"{args.label}_{start + i:03d}.jpg")
            cam.capture(path)
            print("saved", path)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cam.close()
    print("Tip: copy the first few photos to your laptop and check the framing and focus.")


if __name__ == "__main__":
    main()
