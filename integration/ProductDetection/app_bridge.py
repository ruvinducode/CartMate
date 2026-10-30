#!/usr/bin/env python3
"""Bridge between the CartMate app backend (MQTT) and the pick-command program on the Raspberry Pi.

What it does
  1. Subscribes to the topic where the backend publishes an order:   cartmate/navigation/target
  2. Turns the order into a list of items to pick (item NAME -> YOLO class, see NAME_TO_CLASS)
  3. For every item it runs pick_command.py (YOLO + QR two-step check) and waits for PICK or a timeout
  4. Publishes the progress to the app side:                          cartmate/cart/<cart_id>/status

Status message (JSON):
  {"order_id","cart_id","state","item","unit_id","detail","seq","ts"}
  state: order_received | picking | picked | pick_failed | unknown_item | order_done | order_failed

Two ways to receive orders:
  MQTT  (needs a broker; the backend must run with MQTT_MODE=real):
    python3 app_bridge.py --mqtt-host 192.168.1.10 --pick-args "--source pi --weights best.pt --udp 127.0.0.1:5005"
  HTTP polling (NO broker needed, works with the backend in mock mode):
    python3 app_bridge.py --poll --backend-url http://192.168.1.10:5000 --cart-key <CART_API_KEY> --pick-args "..."
  With --backend-url the progress is also sent to the backend (PATCH /api/orders/<id>/shopping-state), so the
  customer's app gets the "shopping finished" alert even without MQTT.
Test without a broker (reads one order from a file, prints the status messages):
  python3 app_bridge.py --payload order.json --pick-args "--source image qr_out/P002-U001.png --fake-det {target}:0.93:250,175,350,345"

In --pick-args, {target} is replaced by the YOLO class of the current item. The bridge adds
--target <class> --once --timeout <n> by itself.

Needs: paho-mqtt (pip install paho-mqtt) for real MQTT. Not tested with a real broker or the real cart yet.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import threading
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))

# Names in the app's product table (case-insensitive) -> YOLO class used by pick_command.py
NAME_TO_CLASS = {
    "cube": "cube",
    "tall box": "tall_box",
    "cylinder": "cylinder",
    "triangle prism": "triangle_prism",
}

ORDER_TOPIC = os.environ.get("MQTT_TARGET_TOPIC", "cartmate/navigation/target")


def status_topic(cart_id):
    return f"cartmate/cart/{cart_id}/status"


# ---------------------------------------------------------------- order handling
def items_from_order(order):
    """Return [(name, quantity), ...] from the backend payload. Uses item_details if present, else items."""
    out = []
    for wp in order.get("waypoints", []):
        details = wp.get("item_details")
        if details:
            for d in details:
                out.append((d.get("name", ""), int(d.get("quantity", 1) or 1)))
        else:
            for name in wp.get("items", []):
                out.append((name, 1))
    return out


STATE_TO_SHOPPING = {"picking": "picking", "picked": "picking", "order_done": "completed",
                     "order_failed": "needs_attention"}


class Publisher:
    """Publishes status messages (MQTT if a client is given, backend HTTP if given, always printed)."""

    def __init__(self, client=None, qos=1, backend=None):
        self.client = client
        self.qos = qos
        self.backend = backend
        self.seq = 0

    def send(self, order, state, item=None, unit_id=None, detail=None):
        self.seq += 1
        msg = {"order_id": order.get("order_id"), "cart_id": order.get("cart_id"), "state": state,
               "item": item, "unit_id": unit_id, "detail": detail, "seq": self.seq, "ts": round(time.time(), 3)}
        line = json.dumps(msg, separators=(",", ":"))
        print("STATUS", line, flush=True)
        if self.client is not None:
            try:
                self.client.publish(status_topic(order.get("cart_id") or "CART_01"), line, qos=self.qos)
            except Exception as e:  # a failed publish must not stop the cart
                print(f"# warning: could not publish status ({e})", file=sys.stderr)
        if self.backend is not None and state in STATE_TO_SHOPPING and order.get("order_id"):
            try:
                if not self.backend.set_shopping_state(order["order_id"], STATE_TO_SHOPPING[state]):
                    print("# warning: backend refused the shopping-state update (check CART_API_KEY)", file=sys.stderr)
            except Exception as e:
                print(f"# warning: could not update the backend ({e})", file=sys.stderr)
        return msg


def run_pick(target, pick_args, timeout, python=sys.executable):
    """Run pick_command.py for one class. Returns (picked_message or None, last_wait_reason)."""
    args = shlex.split(pick_args.replace("{target}", target))
    cmd = [python, os.path.join(HERE, "pick_command.py"), "--target", target, "--once", "--timeout", str(timeout)] + args
    last_reason = "no_output"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return None, "pick_program_timeout"
    for line in proc.stdout.splitlines():
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get("cmd") == "PICK":
            return m, None
        if m.get("cmd") == "WAIT":
            last_reason = m.get("reason", last_reason)          # the most useful reason: why it was not ready
        elif m.get("cmd") == "STOP" and last_reason == "no_output":
            last_reason = m.get("reason", last_reason)
    if proc.returncode != 0 and last_reason == "no_output":
        last_reason = "pick_program_error: " + (proc.stderr.strip().splitlines() or ["?"])[-1][:120]
    return None, last_reason


def handle_order(order, pub, pick_args, timeout, runner=run_pick):
    """Process one order. Returns True if every item was picked."""
    pub.send(order, "order_received", detail=f"{len(items_from_order(order))} item line(s)")
    ok = True
    for name, qty in items_from_order(order):
        cls = NAME_TO_CLASS.get(name.strip().lower())
        if cls is None:
            pub.send(order, "unknown_item", item=name, detail="no YOLO class for this product, skipped")
            ok = False
            continue
        for n in range(1, qty + 1):
            label = name if qty == 1 else f"{name} ({n}/{qty})"
            pub.send(order, "picking", item=label)
            picked, reason = runner(cls, pick_args, timeout)
            if picked:
                pub.send(order, "picked", item=label, unit_id=picked.get("unit_id"),
                         detail=f"decided_by={picked.get('decided_by')} conf={picked.get('confidence')}")
            else:
                pub.send(order, "pick_failed", item=label, detail=reason)
                ok = False
    pub.send(order, "order_done" if ok else "order_failed")
    return ok


# ---------------------------------------------------------------- MQTT
def make_client(host, port, user, password):
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        raise SystemExit("paho-mqtt not installed: pip install paho-mqtt")
    cid = f"cart-pi-{uuid.uuid4().hex[:6]}"
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
    else:
        client = mqtt.Client(client_id=cid)
    if user:
        client.username_pw_set(user, password or "")
    client.connect(host, port, keepalive=30)
    return client


def serve(args, backend=None):
    client = make_client(args.mqtt_host, args.mqtt_port, args.mqtt_user, args.mqtt_password)
    pub = Publisher(client, backend=backend)
    busy = threading.Lock()

    def worker(order):
        with busy:
            handle_order(order, pub, args.pick_args, args.timeout)

    def on_message(_c, _u, msg):
        try:
            order = json.loads(msg.payload.decode())
        except ValueError:
            print("# bad order message ignored", file=sys.stderr)
            return
        if args.cart_id and order.get("cart_id") != args.cart_id:
            return                                    # an order for another cart
        if busy.locked():
            pub.send(order, "order_failed", detail="cart busy with another order")
            return
        threading.Thread(target=worker, args=(order,), daemon=True).start()

    def on_connect(c, *_a):
        c.subscribe(ORDER_TOPIC, qos=1)
        print(f"# connected, waiting for orders on {ORDER_TOPIC}", file=sys.stderr)

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------- HTTP polling (no broker)
def order_from_backend(o):
    """Convert one order of GET /api/orders into the same dict that the MQTT payload has."""
    details = [{"product_id": it.get("product_id"), "name": it.get("product_name", ""),
                "quantity": int(it.get("quantity", 1) or 1)} for it in (o.get("items") or [])]
    return {"order_id": o.get("order_code") or f"ORD_{int(o['id']):04d}", "cart_id": o.get("cart_id"),
            "created_at": o.get("created_at"),
            "waypoints": [{"shelf_id": None, "items": [d["name"] for d in details], "item_details": details}]}


def new_orders(backend, cart_id, last_id):
    """Orders of this cart with id > last_id that are still waiting, oldest first."""
    found = []
    for o in backend.list_orders():
        try:
            oid = int(o["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if oid <= last_id:
            continue
        if cart_id and o.get("cart_id") != cart_id:
            continue
        if o.get("shopping_state") not in (None, "waiting"):
            continue                              # already started or finished
        if not o.get("items"):
            continue
        found.append((oid, o))
    return [o for _i, o in sorted(found, key=lambda t: t[0])]


def poll_loop(args, backend, pub, sleep=time.sleep, max_loops=None):
    last_id = 0
    if not args.process_existing:                 # start from "now": never pick old orders after a restart
        ids = [int(o["id"]) for o in backend.list_orders() if str(o.get("id", "")).isdigit()]
        last_id = max(ids, default=0)
    print(f"# polling {backend.base}/api/orders every {args.poll_seconds}s, new orders after id {last_id}", file=sys.stderr)
    loops = 0
    try:
        while max_loops is None or loops < max_loops:
            loops += 1
            for o in new_orders(backend, args.cart_id, last_id):
                last_id = max(last_id, int(o["id"]))
                handle_order(order_from_backend(o), pub, args.pick_args, args.timeout)
            sleep(args.poll_seconds)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="CartMate app (MQTT) <-> Pi pick bridge")
    ap.add_argument("--mqtt-host", default=os.environ.get("MQTT_BROKER_HOST", "localhost"))
    ap.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_BROKER_PORT", "1883")))
    ap.add_argument("--mqtt-user", default=os.environ.get("MQTT_USERNAME", ""))
    ap.add_argument("--mqtt-password", default=os.environ.get("MQTT_PASSWORD", ""))
    ap.add_argument("--cart-id", default="CART_01", help="only handle orders for this cart ('' = all)")
    ap.add_argument("--pick-args", default="--source pi --weights best.pt",
                    help="extra arguments for pick_command.py; {target} is replaced by the class")
    ap.add_argument("--timeout", type=float, default=30.0, help="seconds to find each item before giving up")
    ap.add_argument("--payload", help="test: read ONE order from this JSON file instead of MQTT")
    ap.add_argument("--poll", action="store_true", help="receive orders by polling the backend (no MQTT broker needed)")
    ap.add_argument("--poll-seconds", type=float, default=3.0)
    ap.add_argument("--process-existing", action="store_true", help="with --poll: also handle orders that already exist")
    ap.add_argument("--backend-url", default=os.environ.get("CART_BACKEND_URL", ""),
                    help="backend base URL, e.g. http://192.168.1.10:5000 (also used to report progress)")
    ap.add_argument("--cart-key", default=os.environ.get("CART_API_KEY", ""), help="X-Cart-Key shared secret")
    args = ap.parse_args(argv)

    backend = None
    if args.backend_url:
        from backend_api import Backend
        backend = Backend(args.backend_url, args.cart_key)

    if args.payload:
        with open(args.payload) as f:
            order = json.load(f)
        ok = handle_order(order, Publisher(None, backend=backend), args.pick_args, args.timeout)
        sys.exit(0 if ok else 1)
    if args.poll:
        if backend is None:
            raise SystemExit("--poll needs --backend-url")
        poll_loop(args, backend, Publisher(None, backend=backend))
        return
    serve(args, backend)


if __name__ == "__main__":
    main()
