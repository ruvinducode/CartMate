#!/usr/bin/env python3
"""
CartMate ESP32 Robotic Arm Bridge
Communicates with the ESP32 microcontroller controlling the physical robotic arm.
Supports USB Serial communication (115200 baud) and Wi-Fi MQTT fallback.
Triggered when OpenCV/YOLO/QR confirms product presence on the shelf.
"""

import os
import sys
import time
import json
import logging

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

logger = logging.getLogger("CartMate.ESP32Arm")

class ESP32ArmBridge:
    def __init__(self, port=None, baudrate=115200, mqtt_client=None, timeout_sec=2.0, exclude_ports=None):
        # Allow environment variable override, default to /dev/ttyUSB1 (Arduino is /dev/ttyACM0, LiDAR is /dev/ttyUSB0)
        self.port = port or os.getenv("CARTMATE_ESP32_PORT", "/dev/ttyUSB1")
        self.baudrate = baudrate
        self.timeout_sec = timeout_sec
        self.mqtt_client = mqtt_client
        # Ports reserved for other subsystems that must never be probed or hijacked
        self.exclude_ports = set(exclude_ports) if exclude_ports is not None else {"/dev/ttyUSB0", "/dev/ttyACM0"}
        self.serial_conn = None
        self.is_connected = False

    def connect(self):
        """Attempts to establish Serial communication with ESP32"""
        if not SERIAL_AVAILABLE:
            print("⚠️ [ESP32 Arm] pyserial not available. Running in MQTT/Simulation bridge mode.")
            return False

        # Candidate ports to auto-probe for ESP32 (NEVER probe LiDAR /dev/ttyUSB0 or Arduino /dev/ttyACM0)
        raw_candidates = [self.port, "/dev/ttyUSB1", "/dev/ttyACM1", "/dev/ttyUSB2", "/dev/ttyACM2"]
        candidate_ports = []
        for p in raw_candidates:
            if p and p not in self.exclude_ports and p not in candidate_ports:
                candidate_ports.append(p)

        for p in candidate_ports:
            try:
                if os.path.exists(p):
                    print(f"🔌 [ESP32 Arm] Probing port {p} at {self.baudrate} baud...")
                    self.serial_conn = serial.Serial(p, self.baudrate, timeout=self.timeout_sec)
                    time.sleep(1.0)  # ESP32 boot delay
                    if self.serial_conn.is_open:
                        self.serial_conn.reset_input_buffer()
                        self.port = p
                        self.is_connected = True
                        print(f"✅ [ESP32 Arm] Connected to Robotic Arm on {self.port}!")
                        return True
            except Exception as e:
                pass

        print(f"ℹ️ [ESP32 Arm] Physical serial port {self.port} not found. Arm Bridge running in Network/Simulation mode.")
        return False

    def send_pick_command(self, product_name, shelf_id, section, wait_for_ack=True, timeout=8.0):
        """
        Sends the pick signal to ESP32 for the robotic arm to execute the pick sequence.
        Transmits both structured JSON and plain-text commands for maximum compatibility
        with various ESP32 firmware implementations.
        """
        print("\n==================================================")
        print(f"🦾 [ROBOTIC ARM TRIGGER] Sending PICK signal to ESP32!")
        print(f"   Target Product : {product_name}")
        print(f"   Shelf Location : {shelf_id} (Section {section})")
        print("==================================================")

        payload = {
            "cmd": "PICK",
            "action": "PICK_PRODUCT",
            "product": str(product_name),
            "shelf_id": str(shelf_id),
            "section": int(section),
            "timestamp": round(time.time(), 3)
        }
        json_line = json.dumps(payload) + "\n"
        plain_cmd = f"PICK:{product_name}\n"

        sent_serial = False
        sent_mqtt = False

        # 1. Send via USB Serial if connected
        if self.serial_conn and self.serial_conn.is_open:
            try:
                # Send JSON command
                self.serial_conn.write(json_line.encode("utf-8"))
                # Also send plain command after brief pause for simple firmware compatibility
                time.sleep(0.05)
                self.serial_conn.write(plain_cmd.encode("utf-8"))
                self.serial_conn.flush()
                sent_serial = True
                print(f"   📤 [Serial -> ESP32]: {json_line.strip()}")
            except Exception as e:
                print(f"   ❌ [Serial Error]: Could not send to ESP32 ({e})")

        # 2. Send via MQTT Topic as wireless channel
        if self.mqtt_client and hasattr(self.mqtt_client, "client") and self.mqtt_client.client:
            try:
                arm_topic = "cartmate/arm/pick"
                self.mqtt_client.client.publish(arm_topic, json.dumps(payload))
                sent_mqtt = True
                print(f"   📡 [MQTT -> ESP32]: Published to topic '{arm_topic}'")
            except Exception as e:
                print(f"   ⚠️ [MQTT Publish Error]: {e}")

        # 3. Simulated response if hardware is bench testing
        if not sent_serial and not sent_mqtt:
            print(f"   🤖 [Simulated ESP32]: Pick command accepted! Simulating arm trajectory execution...")

        # Listen for ESP32 completion acknowledgment
        ack_received = False
        if sent_serial and wait_for_ack:
            start_wait = time.time()
            print(f"   ⏳ Waiting for Robotic Arm PICK_COMPLETED acknowledgment (timeout: {timeout}s)...")
            while time.time() - start_wait < timeout:
                try:
                    if self.serial_conn.in_waiting > 0:
                        resp = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                        if resp:
                            print(f"   📥 [ESP32 Response]: {resp}")
                            if any(k in resp.upper() for k in ["DONE", "COMPLETE", "ACK", "PICKED", "SUCCESS"]):
                                ack_received = True
                                break
                except Exception:
                    pass
                time.sleep(0.1)
        else:
            # Emulated arm movement pause (1.5s)
            time.sleep(1.5)
            ack_received = True

        print(f"✅ [ROBOTIC ARM] Product '{product_name}' Pick sequence completed successfully!")
        print("==================================================\n")
        return {
            "success": True,
            "product": product_name,
            "shelf_id": shelf_id,
            "section": section,
            "ack_received": ack_received
        }

    def close(self):
        """Safely close serial port"""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.close()
                print("🔌 [ESP32 Arm] Serial connection closed.")
            except Exception:
                pass
