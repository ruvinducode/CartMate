#!/usr/bin/env python3
"""A tiny fake of the CartMate backend, ONLY for testing the Pi programs without the real app.

  python3 fake_backend.py            # listens on http://0.0.0.0:5050, X-Cart-Key = testkey
It has the same endpoints the Pi uses: GET /api/orders, PATCH /api/orders/<id>/shopping-state,
GET /api/carts/<cart>/current-otp, POST /api/orders/<id>/verify-otp, and POST /fake/order to add an order.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

KEY = "testkey"
ORDERS = []       # dicts like the real backend's order JSON
OTPS = {}         # order id -> otp


def add_order(items, cart_id="CART_01", otp="123456"):
    oid = len(ORDERS) + 1
    ORDERS.append({"id": oid, "order_code": f"ORD_{oid:04d}", "cart_id": cart_id, "status": "sent_to_cart",
                   "shopping_state": "waiting", "created_at": "2026-10-20T07:00:00Z",
                   "items": [{"product_id": 7 + i, "product_name": n, "quantity": q} for i, (n, q) in enumerate(items)]})
    OTPS[oid] = otp
    return oid


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n).decode() or "{}") if n else {}

    def _auth(self):
        if self.headers.get("X-Cart-Key") != KEY:
            self._send(401, {"msg": "bad cart key"})
            return False
        return True

    def do_GET(self):
        p = self.path
        if p == "/api/orders":
            return self._send(200, ORDERS)
        if p.startswith("/api/carts/") and p.endswith("/current-otp"):
            if not self._auth():
                return
            cart = p.split("/")[3]
            for o in reversed(ORDERS):
                if o["cart_id"] == cart and o["shopping_state"] == "completed":
                    return self._send(200, {"order_id": o["order_code"], "otp": OTPS[o["id"]], "expires_at": "2026-10-21T07:00:00Z"})
            return self._send(404, {"msg": "no order ready"})
        self._send(404, {})

    def do_PATCH(self):
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "orders"] and parts[3] == "shopping-state":
            if not self._auth():
                return
            st = self._body().get("state")
            if st not in ("waiting", "picking", "completed", "needs_attention"):
                return self._send(400, {"msg": "bad state"})
            for o in ORDERS:
                if o["id"] == int(parts[2]):
                    o["shopping_state"] = st
                    return self._send(200, o)
            return self._send(404, {})
        self._send(404, {})

    def do_POST(self):
        if self.path == "/fake/order":
            b = self._body()
            return self._send(200, {"id": add_order([(i["name"], i.get("quantity", 1)) for i in b["items"]])})
        parts = self.path.strip("/").split("/")
        if len(parts) == 4 and parts[3] == "verify-otp":
            if not self._auth():
                return
            b = self._body()
            ok = OTPS.get(int(parts[2])) == b.get("otp")
            return self._send(200 if ok else 400, {"valid": ok})
        self._send(404, {})


def serve(port=5050):
    return HTTPServer(("0.0.0.0", port), H)


if __name__ == "__main__":
    print("fake backend on port 5050, key", KEY, file=sys.stderr)
    serve().serve_forever()
