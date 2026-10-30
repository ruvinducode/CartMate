#!/usr/bin/env python3
"""Check that the REAL CartMate backend has the endpoints the Raspberry Pi code needs.

Safe by default: it only READS (GET) and tries one write WITHOUT the cart key (which must be refused).
Needs: backend_api.py in the same folder. Python 3 only, no extra packages. Works on Windows, Linux, the Pi.

  python api_check.py --backend-url http://localhost:5000 --cart-key YOUR_CART_API_KEY
Optional (changes data, only on an order you choose):
  --write-order 9      sets order 9 shopping_state to picking, then back to what it was
"""
import argparse
import sys

from backend_api import Backend

ok_count = 0
fail_count = 0


def report(name, passed, detail):
    global ok_count, fail_count
    mark = "PASS" if passed else "FAIL"
    ok_count += passed
    fail_count += (not passed)
    print(f"[{mark}] {name}\n       {detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-url", default="http://localhost:5000")
    ap.add_argument("--cart-key", default="")
    ap.add_argument("--cart-id", default="CART_01")
    ap.add_argument("--write-order", type=int, help="order id to flip picking -> original (changes data)")
    a = ap.parse_args()

    b = Backend(a.backend_url, a.cart_key)
    nokey = Backend(a.backend_url, "")
    print(f"Backend: {b.base}   cart key: {'set' if a.cart_key else 'NOT set'}   cart: {a.cart_id}\n")

    # 1. reachable + order list
    try:
        code, orders = b._call("GET", "/api/orders")
    except Exception as e:
        report("1. backend reachable", False, f"cannot connect: {e}  (is it running? is the URL/IP right? firewall?)")
        sys.exit(1)
    report("1. GET /api/orders", code == 200 and isinstance(orders, list), f"HTTP {code}, {len(orders) if isinstance(orders, list) else '?'} order(s)")

    # 2. the fields the Pi needs
    if isinstance(orders, list) and orders:
        o = orders[0]
        need = ["id", "cart_id", "items"]
        missing = [k for k in need if k not in o]
        report("2. order has id, cart_id, items", not missing, f"missing: {missing}" if missing else f"keys: {sorted(o.keys())}")
        report("2b. order has shopping_state", "shopping_state" in o,
               f"value on newest order: {o.get('shopping_state')!r}" if "shopping_state" in o
               else "NOT in GET /api/orders (the Pi then treats every order as 'waiting'; ask Claude Code to add it)")
        report("2c. order has order_code", "order_code" in o, f"{o.get('order_code')!r}")
        items = o.get("items") or []
        it_ok = bool(items) and all(("product_name" in i and "quantity" in i) for i in items)
        report("2d. items have product_name + quantity", it_ok, f"first item: {items[0] if items else 'no items'}")
        names = sorted({i.get("product_name") for od in orders for i in (od.get("items") or [])})
        known = {"cube", "tall box", "cylinder", "triangle prism"}
        report("2e. product names the Pi knows (Cube, Tall Box, Cylinder, Triangle Prism)",
               any(str(n).lower() in known for n in names), f"names seen in orders: {names}")
    else:
        print("[SKIP] 2. no orders yet: place one in the app and run again to check the fields\n")

    # 3. shopping-state without key must be refused (when a key is configured)
    target = (orders[0]["id"] if isinstance(orders, list) and orders else 1)
    code, _ = nokey._call("PATCH", f"/api/orders/{target}/shopping-state", {"state": "waiting"})
    report("3. PATCH shopping-state WITHOUT the key", code in (401, 403),
           f"HTTP {code} " + ("(refused, good)" if code in (401, 403) else
                               "(NOT refused! anyone can change an order's state; backend may be in dev mode without CART_API_KEY)"))

    # 4. current-otp
    code, data = b._call("GET", f"/api/carts/{a.cart_id}/current-otp")
    if code == 200:
        report("4. GET current-otp", True, f"an order is ready: {data.get('order_id')} (OTP hidden here)")
    elif code == 404:
        report("4. GET current-otp", True, "HTTP 404: no order is ready for pickup right now (expected before an order is 'completed')")
    else:
        report("4. GET current-otp", False, f"HTTP {code} {data}  (401/403: wrong key; 405/404 with other text: endpoint missing)")
    code, _ = nokey._call("GET", f"/api/carts/{a.cart_id}/current-otp")
    report("4b. current-otp WITHOUT the key is refused", code in (401, 403), f"HTTP {code}")

    # 5. optional write test
    if a.write_order:
        oid = a.write_order
        prev = next((x.get("shopping_state") for x in orders if x.get("id") == oid), None) or "waiting"
        s1 = b.set_shopping_state(oid, "picking")
        _, cur = b._call("GET", f"/api/orders/{oid}")
        report("5. PATCH with key -> picking", s1, f"order {oid} shopping_state now {cur.get('shopping_state') if isinstance(cur, dict) else '?'}")
        b.set_shopping_state(oid, prev)
        print(f"       restored order {oid} to {prev!r}")

    print(f"\n{ok_count} passed, {fail_count} failed")
    sys.exit(1 if fail_count else 0)


if __name__ == "__main__":
    main()
