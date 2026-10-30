import json
import paho.mqtt.client as mqtt
from config import MQTT_BROKER_HOST, MQTT_BROKER_PORT, TOPIC_NAVIGATION_TARGET

class CartMateMQTTClient:
    def __init__(self, broker_ip=None, port=None, topic=None):
        self.broker_ip = broker_ip if broker_ip is not None else MQTT_BROKER_HOST
        self.port = port if port is not None else MQTT_BROKER_PORT
        self.topic = topic if topic is not None else TOPIC_NAVIGATION_TARGET
        self.client = mqtt.Client(client_id="RaspberryPi5_CartMate")
        
        self.raw_payload = None
        self.navigation_waypoints = []

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print("\n==================================================")
            print("✅ [Raspberry Pi 5] Connected to MacBook MQTT Broker!")
            print(f"📡 Listening on topic: '{self.topic}'")
            print("==================================================\n")
            self.client.subscribe(self.topic)
        else:
            print(f"❌ MQTT Connection failed with code {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode("utf-8")
            self.raw_payload = json.loads(payload_str)
            
            order_id = self.raw_payload.get("order_id", "UNKNOWN")
            cart_id = self.raw_payload.get("cart_id", "UNKNOWN")
            waypoints = self.raw_payload.get("waypoints", [])
            
            print("\n==================================================")
            print(f"📦 NEW ORDER RECEIVED: {order_id} ({cart_id})")
            print("==================================================")
            
            self.navigation_waypoints = []
            
            for idx, wp in enumerate(waypoints, start=1):
                shelf_id = wp.get("shelf_id", "UNKNOWN")
                section = wp.get("section", 1)
                
                shelf_coords = wp.get("shelf_coords", {})
                section_coords = wp.get("section_coords", {})
                
                # Target coordinates for RPLiDAR Navigation Engine
                target_x = wp.get("x", 0.0)
                target_y = wp.get("y", 0.0)
                target_theta = wp.get("orientation_theta", 0.0)
                items = wp.get("items", [])
                
                waypoint_data = {
                    "step": idx,
                    "shelf_id": shelf_id,
                    "shelf_coords": shelf_coords,
                    "section": section,
                    "section_coords": section_coords,
                    "target_x": target_x,
                    "target_y": target_y,
                    "target_theta": target_theta,
                    "items": items
                }
                self.navigation_waypoints.append(waypoint_data)
                
                items_str = ", ".join(items) if items else "None"
                print(f"📍 Goal {idx}: Shelf {shelf_id} (Section {section})")
                print(f"   Coords -> X: {target_x}m | Y: {target_y}m | Theta: {target_theta}°")
                print(f"   Items  -> [{items_str}]")
                print("--------------------------------------------------")
                
            print(f"🚀 Total Waypoints Processed: {len(self.navigation_waypoints)}")
            print("Ready for RPLiDAR Navigation Dispatch!\n")

        except Exception as e:
            print(f"⚠️ Error parsing MQTT payload: {e}")

    def get_waypoints(self):
        """ RPLiDAR & Path Planner එකට Waypoints Array එක ලබාදෙන Getter Method එක """
        return self.navigation_waypoints

    def clear_waypoints(self):
        """ Clears all loaded waypoints and payload (e.g. when user cancels navigation) """
        self.navigation_waypoints = []
        self.raw_payload = None

    def start(self):
        print(f"🔄 Connecting to MacBook MQTT Broker at {self.broker_ip}:{self.port}...")
        try:
            self.client.connect(self.broker_ip, self.port, 60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ Connection Error: {e}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

    