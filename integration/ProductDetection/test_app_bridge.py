#!/usr/bin/env python3
"""Offline tests: HTTP polling bridge + cart OTP display, against fake_backend.py. No broker, camera or app needed."""
import io
import threading
import time
from contextlib import redirect_stdout, redirect_stderr
from types import SimpleNamespace

import app_bridge as ab
import cart_otp_display as cod
import fake_backend as fb
from backend_api import Backend

srv = fb.serve(5057)
threading.Thread(target=srv.serve_forever, daemon=True).start()
b = Backend("http://127.0.0.1:5057", "testkey")

# an old order that exists before the bridge starts must NOT be picked
fb.add_order([("Cube", 1)])

args = SimpleNamespace(cart_id="CART_01", pick_args="--source image qr_out/P002-U001.png --fake-det {target}:0.93:250,175,350,345",
                       timeout=4, process_existing=False, poll_seconds=0.2)
pub = ab.Publisher(None, backend=b)
out = io.StringIO()


def add_later():
    time.sleep(0.5)
    fb.add_order([("Tall Box", 1)])           # new order after start
    time.sleep(0.2)
    fb.add_order([("Tall Box", 1)], cart_id="CART_02")   # another cart: ignored


threading.Thread(target=add_later, daemon=True).start()
with redirect_stdout(out), redirect_stderr(io.StringIO()):
    ab.poll_loop(args, b, pub, max_loops=25)
text = out.getvalue()
print(text)
states = [l for l in text.splitlines() if l.startswith("STATUS")]
assert any('"picked"' in l and "ORD_0002" in l for l in states), "Tall Box of order 2 must be picked"
assert not any("ORD_0001" in l for l in states), "old order 1 must be ignored"
assert not any("ORD_0003" in l for l in states), "order of another cart must be ignored"
assert fb.ORDERS[0]["shopping_state"] == "waiting", "old order untouched"
assert fb.ORDERS[1]["shopping_state"] == "completed", fb.ORDERS[1]["shopping_state"]
print("poll mode ok: order 2 picked, backend shopping_state =", fb.ORDERS[1]["shopping_state"])

# a failing pick must end as needs_attention
fb.add_order([("Cube", 1)])
args.process_existing = True
args.pick_args = "--source image qr_out/P002-U001.png --fake-det {target}:0.93:250,175,350,345"   # QR is Tall Box -> Cube fails
for o in fb.ORDERS:
    if o["id"] != 4:
        o["shopping_state"] = "completed"
with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
    ab.poll_loop(args, b, pub, max_loops=2)
assert fb.ORDERS[3]["shopping_state"] == "needs_attention", fb.ORDERS[3]["shopping_state"]
print("failed pick -> needs_attention ok")

# wrong cart key: the update must be refused, not crash
bad = Backend("http://127.0.0.1:5057", "wrong")
assert bad.set_shopping_state("ORD_0001", "picking") is False
assert bad.current_otp("CART_01") is None
print("wrong key refused ok")

# cart OTP display
class Rec:
    def __init__(self): self.shots = []
    def show(self, lines): self.shots.append(" | ".join(t for t, _s, _y in lines))

rec = Rec()
fb.ORDERS[2]["shopping_state"] = "waiting"
for o in fb.ORDERS: o["shopping_state"] = "waiting"
cod.run(rec, b, "CART_01", 0.05, max_loops=2, sleep=lambda s: None)
assert rec.shots == ["CART_01 | ready"], rec.shots           # nothing ready: idle screen, drawn once
fb.ORDERS[1]["shopping_state"] = "completed"
cod.run(rec, b, "CART_01", 0.05, max_loops=2, sleep=lambda s: None)
print(rec.shots)
assert any("123 456" in s for s in rec.shots), rec.shots
print("cart otp display ok")
srv.shutdown()
print("ALL APP TESTS PASSED")
