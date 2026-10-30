#!/usr/bin/env python3
"""Small HTTP client for the CartMate backend (no extra packages, only the standard library).

Endpoints used (all added for the Pi):
  GET   /api/orders                                list of recent orders (to find new ones)
  PATCH /api/orders/<id>/shopping-state            {"state": ...}      header X-Cart-Key
  GET   /api/carts/<cart_id>/current-otp           header X-Cart-Key   -> {"order_id","otp","expires_at"}
  POST  /api/orders/<id>/verify-otp                {"otp","cart_id"}   header X-Cart-Key
Environment: CART_BACKEND_URL (default http://localhost:5000), CART_API_KEY.
"""
import json
import os
import urllib.error
import urllib.request


class Backend:
    def __init__(self, base_url=None, cart_key=None, timeout=5.0):
        self.base = (base_url or os.environ.get("CART_BACKEND_URL", "http://localhost:5000")).rstrip("/")
        self.key = cart_key if cart_key is not None else os.environ.get("CART_API_KEY", "")
        self.timeout = timeout

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.key:
            req.add_header("X-Cart-Key", self.key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "null")
            except ValueError:
                return e.code, None

    def list_orders(self):
        code, data = self._call("GET", "/api/orders")
        return data if code == 200 and isinstance(data, list) else []

    def set_shopping_state(self, order_id, state):
        """order_id: 8 or 'ORD_0008'. Returns True on success."""
        num = int(str(order_id).split("_")[-1])
        code, _ = self._call("PATCH", f"/api/orders/{num}/shopping-state", {"state": state})
        return code == 200

    def current_otp(self, cart_id):
        """Return {"order_id","otp","expires_at"} or None when no order is ready for pickup."""
        code, data = self._call("GET", f"/api/carts/{cart_id}/current-otp")
        return data if code == 200 and isinstance(data, dict) and data.get("otp") else None

    def verify_otp(self, order_id, otp, cart_id):
        num = int(str(order_id).split("_")[-1])
        code, data = self._call("POST", f"/api/orders/{num}/verify-otp", {"otp": otp, "cart_id": cart_id})
        return code, data
