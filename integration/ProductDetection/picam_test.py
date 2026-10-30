#!/usr/bin/env python3
"""Pi Camera program: check the camera, save a photo, and (optionally) run YOLO on it.

Usage:
  python3 picam_test.py check                   # open the camera, take 1 photo, report size and brightness
  python3 picam_test.py detect --model best.pt  # take a photo, run YOLO, print class, confidence, box centre (X, Y)
  python3 picam_test.py live   --model best.pt  # repeat detection until Ctrl+C, prints FPS
  options: --out DIR (default ~/saumya_cart/picam), --conf 0.5, --size 1280x720

For 'detect' and 'live' you need ultralytics:  pip install ultralytics  (inside your own venv).
If the model is yolov8n.pt it is downloaded automatically (needs internet).
Not tested on real hardware yet.
"""
import argparse
import os
import time


def parse_size(text):
    w, h = text.lower().split("x")
    return int(w), int(h)


class PiCam:
    def __init__(self, size):
        try:
            from picamera2 import Picamera2
        except ImportError:
            raise SystemExit("picamera2 not found. Create the venv with --system-site-packages "
                             "and run: sudo apt install python3-picamera2 (ask before changing the shared Pi).")
        if not Picamera2.global_camera_info():
            raise SystemExit("No camera found. Power off, check the ribbon cable (Pi 5 needs the 22-pin "
                             "cable, contacts facing the right way) and try 'rpicam-hello --list-cameras'.")
        self.cam = Picamera2()
        # RGB888 gives a numpy array ready for YOLO; still config = full quality
        self.cam.configure(self.cam.create_still_configuration(main={"size": size, "format": "RGB888"}))
        self.cam.start()
        time.sleep(1.5)  # auto exposure settle

    def frame(self):
        return self.cam.capture_array()  # H x W x 3 numpy array

    def save(self, path):
        self.cam.capture_file(path)

    def close(self):
        self.cam.stop()
        self.cam.close()


def detect(model, frame, conf):
    """Return a list of dicts: class name, confidence, box centre in pixels, box size."""
    result = model.predict(frame, conf=conf, verbose=False)[0]
    found = []
    for box in result.boxes:
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
        found.append({
            "class": result.names[int(box.cls[0])],
            "conf": round(float(box.conf[0]), 2),
            "cx": round((x1 + x2) / 2), "cy": round((y1 + y2) / 2),
            "w": round(x2 - x1), "h": round(y2 - y1),
        })
    return found


def print_detections(found):
    if not found:
        print("  nothing detected")
    for d in found:
        print(f"  {d['class']:16s} conf {d['conf']:.2f}  centre (X={d['cx']}, Y={d['cy']})  size {d['w']}x{d['h']}")


def load_model(path):
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit("ultralytics not installed. Run: pip install ultralytics")
    return YOLO(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pi Camera check and detection")
    ap.add_argument("mode", choices=["check", "detect", "live"])
    ap.add_argument("--model", default="yolov8n.pt")
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--out", default=os.path.expanduser("~/saumya_cart/picam"))
    args = ap.parse_args(argv)

    os.makedirs(args.out, exist_ok=True)
    cam = PiCam(parse_size(args.size))
    try:
        if args.mode == "check":
            path = os.path.join(args.out, "check.jpg")
            cam.save(path)
            frame = cam.frame()
            print(f"Saved {path}")
            print(f"Frame {frame.shape[1]}x{frame.shape[0]}, average brightness {frame.mean():.0f}/255")
            if frame.mean() < 30:
                print("Very dark: remove the lens cap/film or add light.")
            elif frame.mean() > 225:
                print("Very bright: too much light or lens facing a lamp.")
            print("Copy check.jpg to your laptop and look at it: is it sharp? Is the whole cart area in view?")
        else:
            model = load_model(args.model)
            if args.mode == "detect":
                frame = cam.frame()
                t = time.time()
                found = detect(model, frame, args.conf)
                print(f"Inference {1000 * (time.time() - t):.0f} ms")
                print_detections(found)
                cam.save(os.path.join(args.out, "detect.jpg"))
            else:
                print("Live detection. Ctrl+C to stop.")
                while True:
                    t = time.time()
                    found = detect(model, cam.frame(), args.conf)
                    fps = 1 / max(time.time() - t, 1e-6)
                    print(f"--- {fps:.1f} FPS")
                    print_detections(found)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cam.close()


if __name__ == "__main__":
    main()
