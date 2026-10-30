#!/usr/bin/env python3
"""Read the cart's product QR codes from a camera (or from an image file) and verify them.

QR content:  <unit_id>|<signature>      e.g.  P001-U017|a3f9c21b
The signature is an HMAC of the unit id, so a made-up or edited QR is rejected.
Weights/names are NOT in the QR; they come from the PRODUCTS table below (the ledger lookup).

Usage:
  python3 qr_scan.py --source image qr_codes/P001-U001.png   # test with a saved QR picture
  python3 qr_scan.py --source usb                            # USB webcam, live (Ctrl+C to stop)
  python3 qr_scan.py --source pi                             # Pi Camera, live (needs the camera connected)
options: --once (stop after the first valid QR), --save DIR (save a photo of every valid scan)

Needs: opencv-python-headless (pip install opencv-python-headless).  Pi Camera also needs picamera2.
IMPORTANT: SECRET and make_payload must be the same as in the Colab QR generator (Step 17).
Not tested on real cameras yet; the decode/verify logic is tested on generated QR images.
"""
import argparse
import hashlib
import hmac
import os
import time

import cv2

SECRET = os.environ.get("CART_QR_SECRET", "saumya_cart_secret_key").encode()  # sample key; set CART_QR_SECRET to use a private one

# Ledger lookup: product id -> details (the QR only carries the unit id).
# "class" is the YOLO class name, so the pick logic can compare YOLO and QR.
# size_mm: w = width (what the camera sees), d = depth, h = height.
# weight_g / tol_g: DESIGN values for the prototype. Add ballast to each foam object to reach the weight,
# then confirm with the load cell and adjust. The prism depth (35 mm) is an assumption: check it with a ruler.
PRODUCTS = {
    "P001": {"name": "cube", "class": "cube", "size_mm": {"w": 35, "d": 35, "h": 35}, "weight_g": 100, "tol_g": 10},
    "P002": {"name": "tall box", "class": "tall_box", "size_mm": {"w": 35, "d": 35, "h": 70}, "weight_g": 200, "tol_g": 10},
    "P003": {"name": "cylinder", "class": "cylinder", "size_mm": {"w": 35, "d": 35, "h": 70}, "weight_g": 150, "tol_g": 10},
    "P004": {"name": "triangle prism", "class": "triangle_prism", "size_mm": {"w": 35, "d": 35, "h": 35}, "weight_g": 50, "tol_g": 10},
}


def make_payload(unit_id):
    sig = hmac.new(SECRET, unit_id.encode(), hashlib.sha256).hexdigest()[:8]
    return f"{unit_id}|{sig}"


def verify(payload):
    """Return the unit id if the signature is correct, otherwise None."""
    try:
        unit_id, sig = payload.split("|")
    except ValueError:
        return None
    good = hmac.new(SECRET, unit_id.encode(), hashlib.sha256).hexdigest()[:8]
    return unit_id if hmac.compare_digest(sig, good) else None


def lookup(unit_id):
    return PRODUCTS.get(unit_id.split("-")[0])


def read_qr(frame, detector):
    """Return the text of the QR in the frame, or '' if none was found."""
    text, _points, _ = detector.detectAndDecode(frame)
    return text


class UsbCam:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            raise SystemExit("Cannot open the webcam. Check 'ls /dev/video*'.")

    def frame(self):
        ok, f = self.cap.read()
        return f if ok else None

    def close(self):
        self.cap.release()


class PiCam:
    def __init__(self):
        try:
            from picamera2 import Picamera2
        except ImportError:
            raise SystemExit("picamera2 not found (create the venv with --system-site-packages).")
        if not Picamera2.global_camera_info():
            raise SystemExit("No Pi Camera found. Connect it (Pi 5 needs a 22-pin cable) and check 'rpicam-hello --list-cameras'.")
        self.cam = Picamera2()
        self.cam.configure(self.cam.create_preview_configuration(main={"size": (1280, 720), "format": "RGB888"}))
        self.cam.start()
        time.sleep(1.5)

    def frame(self):
        return self.cam.capture_array()

    def close(self):
        self.cam.stop()
        self.cam.close()


def report(text, seen):
    unit = verify(text)
    if unit is None:
        print(f"REJECTED  QR '{text}' (bad signature, not a cart product)")
        return None
    info = lookup(unit)
    if info is None:
        print(f"UNKNOWN   {unit} is not in the product table")
        return None
    note = "" if unit not in seen else "  (already scanned)"
    sz = info["size_mm"]
    print(f"VERIFIED  {unit}  {info['name']} (class {info['class']})  size {sz['w']}x{sz['d']}x{sz['h']} mm (WxDxH)  "
          f"weight {info['weight_g']} +/- {info['tol_g']} g{note}")
    return unit


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read and verify product QR codes")
    ap.add_argument("--source", choices=["pi", "usb", "image"], required=True)
    ap.add_argument("path", nargs="?", help="image file (for --source image)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--save", help="folder to save a photo of each valid scan")
    args = ap.parse_args(argv)

    detector = cv2.QRCodeDetector()

    if args.source == "image":
        if not args.path:
            raise SystemExit("Give the image path: --source image qr_codes/P001-U001.png")
        img = cv2.imread(args.path)
        if img is None:
            raise SystemExit(f"Cannot read {args.path}")
        text = read_qr(img, detector)
        if not text:
            raise SystemExit("No QR code found in the image")
        report(text, set())
        return

    cam = PiCam() if args.source == "pi" else UsbCam()
    seen, last, last_time = set(), "", 0.0
    print("Show a product QR to the camera. Ctrl+C to stop.")
    try:
        while True:
            frame = cam.frame()
            if frame is None:
                continue
            text = read_qr(frame, detector)
            now = time.time()
            if text and (text != last or now - last_time > 3):  # do not repeat the same scan every frame
                last, last_time = text, now
                unit = report(text, seen)
                if unit:
                    seen.add(unit)
                    if args.save:
                        os.makedirs(args.save, exist_ok=True)
                        cv2.imwrite(os.path.join(args.save, f"{unit}_{int(now)}.jpg"), frame)
                    if args.once:
                        break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cam.close()


if __name__ == "__main__":
    main()
