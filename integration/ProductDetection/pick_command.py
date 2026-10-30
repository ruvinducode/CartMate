#!/usr/bin/env python3
"""Detect the ordered product, check it, and tell the robot arm when it may pick it.

Output: one JSON line per command (PICK, WAIT or STOP), see README_pick_interface.md.

Checks before PICK (all must hold for N frames in a row):
  1. YOLO sees the ordered class        (class match)
  2. confidence >= --min-conf           (default 0.6)
  3. QR policy (--qr-mode):
       always (default)    two-step verification: YOLO finds and names the object, the QR confirms it. Both needed.
       fallback            the arm looks from above; if YOLO is sure (conf >= --high-conf, default 0.85, and no
                           other class is close) it may PICK without the QR. If YOLO is not sure, the QR is
                           needed ("qr_needed": the arm can move closer so the camera reads it).
       off                 the QR is ignored (testing only; --no-qr is the same).
     In every mode, if a QR IS visible and it is invalid or belongs to another class, the answer is WAIT.
  4. the object stays still (centre moves less than --max-move px)    (stable)

Examples:
  python3 pick_command.py --weights best.pt --source usb --target tall_box
  python3 pick_command.py --weights best.pt --source pi  --target cube --serial /dev/ttyUSB0
  python3 pick_command.py --weights best.pt --source image photo.jpg --target cylinder --no-qr --once
  python3 pick_command.py --fake-det cylinder:0.93:100,80,220,300 --source image photo.jpg --target cylinder --no-qr --once

Send options (any combination; the JSON is always printed too):
  --serial PORT [--baud 115200]   one JSON line per command over a serial cable
  --http URL                      HTTP POST with the JSON body
  --udp HOST:PORT                 one UDP packet per command
  --file PATH                     write the latest command to a file (the other side can poll it)

Needs: opencv-python-headless, numpy, ultralytics (for the real detector). Optional: pyserial.
The Pi Camera also needs picamera2. Not tested on the real camera or robot arm yet.
"""
import argparse
import json
import math
import os
import socket
import sys
import time
import urllib.request
from collections import deque

import cv2
import numpy as np

from qr_scan import PRODUCTS, PiCam, UsbCam, lookup, read_qr, verify

CLASS_TO_PRODUCT = {info["class"]: pid for pid, info in PRODUCTS.items()}


# ---------------------------------------------------------------- detection
class YoloDetector:
    def __init__(self, weights, conf=0.25):
        try:
            from ultralytics import YOLO
        except ImportError:
            raise SystemExit("ultralytics not installed: pip install ultralytics")
        self.model = YOLO(weights)
        self.conf = conf

    def detect(self, frame):
        res = self.model.predict(frame, conf=self.conf, verbose=False)[0]
        out = []
        for b in res.boxes:
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
            out.append({"cls": res.names[int(b.cls[0])], "conf": float(b.conf[0]), "box": (x1, y1, x2, y2)})
        return out


class FakeDetector:
    """For testing without a model. Format: class:conf:x1,y1,x2,y2  (several separated by ';')."""

    def __init__(self, spec):
        self.dets = []
        for part in spec.split(";"):
            c, conf, box = part.split(":")
            self.dets.append({"cls": c, "conf": float(conf), "box": tuple(float(v) for v in box.split(","))})

    def detect(self, frame):
        return list(self.dets)


def estimate_angle(frame, box, cls):
    """Rough in-plane angle of the object in degrees (-45..45), or None.

    Uses the orange colour of the foam objects inside the detected box and OpenCV minAreaRect.
    Only meaningful when the camera looks at the object from above. A cylinder has no useful angle.
    """
    if cls == "cylinder":
        return None
    x1, y1, x2, y2 = [int(round(v)) for v in box]
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = max(0, x1), max(0, y1), min(w, x2), min(h, y2)
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 90, 60), (25, 255, 255)) | cv2.inRange(hsv, (170, 90, 60), (180, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.2 * (x2 - x1) * (y2 - y1):
        return None
    (_, _), (_, _), ang = cv2.minAreaRect(c)
    a = ang % 90.0
    if a > 45.0:
        a -= 90.0
    return round(a, 1)


# ---------------------------------------------------------------- decision
def iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


class PickDecider:
    """Turns detections (+ QR) into PICK / WAIT commands. No camera or model inside, so it is easy to test."""

    def __init__(self, target, min_conf=0.6, stable_frames=5, max_move_px=12.0, qr_mode="always",
                 high_conf=0.85, qr_hold_s=2.0, ambig_margin=0.2):
        assert qr_mode in ("always", "fallback", "off")
        self.target = target
        self.min_conf = min_conf
        self.high_conf = high_conf
        self.qr_mode = qr_mode
        self.qr_hold_s = qr_hold_s
        self.ambig_margin = ambig_margin
        self.max_move = max_move_px
        self.n = stable_frames
        self.hist = deque(maxlen=stable_frames)
        self.qr_unit = None
        self.qr_time = 0.0

    def reset(self):
        self.hist.clear()

    def note_qr(self, text, now):
        """Call with the decoded QR text (or '') for every frame."""
        if not text:
            return
        unit = verify(text)
        if unit is not None and lookup(unit) is not None:
            self.qr_unit, self.qr_time = unit, now
        else:
            self.qr_unit, self.qr_time = "INVALID", now

    def _wait(self, reason, **extra):
        self.hist.clear()
        d = {"cmd": "WAIT", "reason": reason, "target": self.target}
        d.update(extra)
        return d

    def update(self, dets, now, frame_shape, frame=None):
        if not dets:
            return self._wait("no_object")
        cands = [d for d in dets if d["cls"] == self.target]
        if not cands:
            return self._wait("wrong_object", seen=sorted({d["cls"] for d in dets}))
        best = max(cands, key=lambda d: d["conf"])
        if best["conf"] < self.min_conf:
            return self._wait("low_confidence", confidence=round(best["conf"], 2))

        # is YOLO sure? (high confidence and no other class sitting on the same object with a similar score)
        ambiguous = any(o["cls"] != self.target and iou(o["box"], best["box"]) > 0.5
                        and o["conf"] >= best["conf"] - self.ambig_margin for o in dets)
        sure = best["conf"] >= self.high_conf and not ambiguous

        unit, qr_used = None, False
        if self.qr_mode != "off":
            fresh = self.qr_unit is not None and (now - self.qr_time) <= self.qr_hold_s
            if fresh:
                if self.qr_unit == "INVALID":
                    return self._wait("qr_invalid")           # a QR is visible but fake / unreadable
                info = lookup(self.qr_unit)
                if info["class"] != self.target:
                    return self._wait("qr_mismatch", qr_class=info["class"])
                unit, qr_used = self.qr_unit, True
            elif self.qr_mode == "always" or not sure:
                why = "policy" if self.qr_mode == "always" else ("ambiguous" if ambiguous else "low_confidence")
                return self._wait("qr_needed", why=why, hint="move_closer")

        x1, y1, x2, y2 = best["box"]
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        self.hist.append((cx, cy))
        if len(self.hist) < self.n:
            return {"cmd": "WAIT", "reason": "settling", "target": self.target, "frames": f"{len(self.hist)}/{self.n}"}
        mx = sum(p[0] for p in self.hist) / len(self.hist)
        my = sum(p[1] for p in self.hist) / len(self.hist)
        if max(math.hypot(p[0] - mx, p[1] - my) for p in self.hist) > self.max_move:
            self.hist.popleft()
            return {"cmd": "WAIT", "reason": "moving", "target": self.target}

        h, w = frame_shape[:2]
        angle = estimate_angle(frame, best["box"], self.target) if frame is not None else None
        info = PRODUCTS[CLASS_TO_PRODUCT[self.target]]
        return {
            "cmd": "PICK",
            "target": self.target,
            "product_id": CLASS_TO_PRODUCT.get(self.target),
            "unit_id": unit,
            "decided_by": "yolo+qr" if qr_used else "yolo",
            "size_mm": info["size_mm"],
            "weight_g": info["weight_g"],
            "weight_tol_g": info["tol_g"],
            "confidence": round(best["conf"], 2),
            "center_px": [round(cx, 1), round(cy, 1)],
            "center_norm": [round(cx / w, 3), round(cy / h, 3)],
            "bbox_px": [round(v, 1) for v in best["box"]],
            "angle_deg": angle,
            "frame": {"w": w, "h": h},
        }


# ---------------------------------------------------------------- sending
class Sender:
    def __init__(self, serial_port=None, baud=115200, http=None, udp=None, file=None):
        self.ser = None
        if serial_port:
            try:
                import serial
            except ImportError:
                raise SystemExit("pyserial not installed: pip install pyserial")
            self.ser = serial.Serial(serial_port, baud, timeout=1)
        self.http = http
        self.udp = None
        if udp:
            host, port = udp.rsplit(":", 1)
            self.udp = (host, int(port))
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.file = file
        self.seq = 0

    def send(self, msg):
        self.seq += 1
        msg = dict(msg, seq=self.seq, ts=round(time.time(), 3))
        line = json.dumps(msg, separators=(",", ":"))
        print(line, flush=True)
        try:
            if self.ser:
                self.ser.write((line + "\n").encode())
            if self.http:
                req = urllib.request.Request(self.http, data=line.encode(), headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=2).read()
            if self.udp:
                self.sock.sendto(line.encode(), self.udp)
            if self.file:
                tmp = self.file + ".tmp"
                with open(tmp, "w") as f:
                    f.write(line + "\n")
                os.replace(tmp, self.file)
        except Exception as e:  # a failed send must not stop the loop
            print(f"# warning: could not send ({e})", file=sys.stderr)
        return msg

    def close(self):
        if self.ser:
            self.ser.close()


class ImageSource:
    def __init__(self, path):
        self.img = cv2.imread(path)
        if self.img is None:
            raise SystemExit(f"Cannot read {path}")

    def frame(self):
        return self.img.copy()

    def close(self):
        pass


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Send PICK / WAIT / STOP commands to the robot arm")
    ap.add_argument("--source", choices=["pi", "usb", "image"], required=True)
    ap.add_argument("path", nargs="?", help="image file (for --source image)")
    ap.add_argument("--weights", help="YOLO weights, e.g. best.pt")
    ap.add_argument("--fake-det", help="test without a model: class:conf:x1,y1,x2,y2")
    tg = ap.add_mutually_exclusive_group(required=True)
    tg.add_argument("--target", choices=sorted(CLASS_TO_PRODUCT), help="ordered class")
    tg.add_argument("--product", choices=sorted(PRODUCTS), help="ordered product id, e.g. P002")
    ap.add_argument("--min-conf", type=float, default=0.6)
    ap.add_argument("--stable", type=int, default=5, help="frames in a row before PICK")
    ap.add_argument("--max-move", type=float, default=12.0, help="max centre movement in px")
    ap.add_argument("--qr-mode", choices=["always", "fallback", "off"], default="always",
                    help="always: two-step check, YOLO + QR both needed (default); fallback: QR only when YOLO is not sure; off")
    ap.add_argument("--high-conf", type=float, default=0.85, help="YOLO is 'sure' at or above this confidence")
    ap.add_argument("--no-qr", action="store_true", help="same as --qr-mode off (testing only)")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds without PICK before STOP")
    ap.add_argument("--cooldown", type=float, default=5.0, help="seconds to wait after a PICK (loop mode)")
    ap.add_argument("--once", action="store_true", help="stop after the first PICK")
    ap.add_argument("--serial")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--http")
    ap.add_argument("--udp")
    ap.add_argument("--file")
    args = ap.parse_args(argv)

    target = args.target or PRODUCTS[args.product]["class"]
    if args.fake_det:
        det = FakeDetector(args.fake_det)
    elif args.weights:
        det = YoloDetector(args.weights)
    else:
        raise SystemExit("Give --weights best.pt (or --fake-det for a test)")

    if args.source == "image":
        if not args.path:
            raise SystemExit("Give the image path: --source image photo.jpg")
        cam = ImageSource(args.path)
    else:
        cam = PiCam() if args.source == "pi" else UsbCam()

    qr_mode = "off" if args.no_qr else args.qr_mode
    decider = PickDecider(target, args.min_conf, args.stable, args.max_move, qr_mode=qr_mode, high_conf=args.high_conf)
    sender = Sender(args.serial, args.baud, args.http, args.udp, args.file)
    qr_detector = cv2.QRCodeDetector()

    start = time.time()
    last_key, last_sent, bad_frames = None, 0.0, 0
    print(f"# target={target} min_conf={args.min_conf} stable={args.stable} qr={qr_mode} high_conf={args.high_conf}", file=sys.stderr)
    try:
        while True:
            frame = cam.frame()
            now = time.time()
            if frame is None:
                bad_frames += 1
                if bad_frames > 30:
                    sender.send({"cmd": "STOP", "reason": "camera_error"})
                    break
                continue
            bad_frames = 0
            if qr_mode != "off":
                decider.note_qr(read_qr(frame, qr_detector), now)
            msg = decider.update(det.detect(frame), now, frame.shape, frame)

            if msg["cmd"] == "PICK":
                sender.send(msg)
                if args.once:
                    break
                time.sleep(args.cooldown)       # give the arm time to pick
                decider.reset()
                start = time.time()
                last_key = None
                continue

            key = (msg["reason"], msg.get("frames") if msg["reason"] != "settling" else None)
            if key != last_key or now - last_sent > 1.0:   # do not flood: send on change or once a second
                sender.send(msg)
                last_key, last_sent = key, now

            if now - start > args.timeout:
                sender.send({"cmd": "STOP", "reason": "timeout"})
                break
            if args.source == "image":
                time.sleep(0.02)
    except KeyboardInterrupt:
        sender.send({"cmd": "STOP", "reason": "operator_stop"})
    finally:
        cam.close()
        sender.close()


if __name__ == "__main__":
    main()
