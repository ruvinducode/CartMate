#!/usr/bin/env python3
"""Show the pickup OTP of the customer's order on the cart's OLED (same OTP as in the customer's app).

The OTP is made by the backend when the customer pays. This program only DISPLAYS it: it asks the backend
(GET /api/carts/<cart_id>/current-otp, header X-Cart-Key) and shows the code while an order of this cart is
ready for pickup (shopping finished). It never makes or stores an OTP itself.

Wiring: same OLED as otp_display.py (SDA GPIO2, SCL GPIO3, 3.3 V, GND, address 0x3C).

Usage:
  python3 cart_otp_display.py --backend-url http://192.168.1.10:5000 --cart-key <CART_API_KEY>
  python3 cart_otp_display.py --backend-url ... --no-oled          # print to the terminal instead of the OLED
  options: --cart-id CART_01, --interval 3 (seconds between checks), --once
Not tested on real hardware yet.
"""
import argparse
import os
import sys
import time

from backend_api import Backend
from otp_display import OledDisplay, TerminalDisplay


def screens(cart_id, info, now=None):
    """Lines for the display: (text, font size, y)."""
    if info is None:
        return [(cart_id, 16, 8), ("ready", 16, 34)]
    otp = str(info["otp"])
    shown = otp[:3] + " " + otp[3:] if len(otp) == 6 else otp
    return [(f"{cart_id}  PICKUP OTP", 12, 0), (shown, 28, 16), ("match it with your app", 12, 50)]


def run(display, backend, cart_id, interval, once=False, sleep=time.sleep, max_loops=None):
    last = "__none__"
    loops = 0
    while max_loops is None or loops < max_loops:
        loops += 1
        try:
            info = backend.current_otp(cart_id)
        except Exception as e:                     # backend not reachable: keep the last screen, try again
            print(f"# backend not reachable ({e})", file=sys.stderr)
            sleep(interval)
            continue
        key = None if info is None else (info["order_id"], info["otp"])
        if key != last:                            # redraw only when something changed
            display.show(screens(cart_id, info))
            last = key
        if once:
            return info
        sleep(interval)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Show the backend's pickup OTP on the cart OLED")
    ap.add_argument("--backend-url", default=os.environ.get("CART_BACKEND_URL", "http://localhost:5000"))
    ap.add_argument("--cart-key", default=os.environ.get("CART_API_KEY", ""))
    ap.add_argument("--cart-id", default="CART_01")
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--no-oled", action="store_true")
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args(argv)
    display = TerminalDisplay() if args.no_oled else OledDisplay()
    try:
        run(display, Backend(args.backend_url, args.cart_key), args.cart_id, args.interval, args.once)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
