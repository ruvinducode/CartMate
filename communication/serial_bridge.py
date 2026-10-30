"""
Serial Bridge Module (CartMate Subsystem 1)
Handles bi-directional USB-Serial communication between Raspberry Pi 5 and Arduino Uno.
Executes non-blocking telemetry reception and formats velocity targets for the co-processor.
"""

import serial
import threading
import time
import logging
from config import SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_TIMEOUT_SEC

logger = logging.getLogger("CartMate.SerialBridge")

class ArduinoSerialBridge:
    def __init__(self, port=SERIAL_PORT, baudrate=SERIAL_BAUDRATE):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()

        # Telemetry State Data (Received from Arduino)
        self.left_encoder_ticks = 0
        self.right_encoder_ticks = 0
        self.min_ultrasonic_cm = 999.0
        self.last_telemetry_time = 0.0

    def connect(self):
        """Establishes connection to Arduino Uno over USB-Serial."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=SERIAL_TIMEOUT_SEC
            )
            time.sleep(2.0)  # Allow Arduino reset delay after connection
            self.is_running = True
            self.thread = threading.Thread(target=self._read_loop, daemon=True)
            self.thread.start()
            logger.info(f"Connected to Arduino Uno on {self.port} at {self.baudrate} baud.")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Arduino on {self.port}: {e}")
            return False

    def _read_loop(self):
        """Background thread reading incoming ASCII telemetry frames from Arduino."""
        while self.is_running and self.serial_conn and self.serial_conn.is_open:
            try:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("TELE"):
                        self._parse_telemetry(line)
            except Exception as e:
                logger.warning(f"Serial read exception: {e}")
                time.sleep(0.05)

    def _parse_telemetry(self, line):
        """Parses line format: TELE,<left_ticks>,<right_ticks>,<ultrasonic_cm>"""
        try:
            parts = line.split(',')
            if len(parts) >= 4:
                with self.lock:
                    self.left_encoder_ticks = int(parts[1])
                    self.right_encoder_ticks = int(parts[2])
                    self.min_ultrasonic_cm = float(parts[3])
                    self.last_telemetry_time = time.time()
        except ValueError as e:
            logger.warning(f"Corrupted serial frame received: '{line}' - Error: {e}")

    def send_target_speeds(self, left_rpm: float, right_rpm: float):
        """
        Sends target wheel speeds in RPM to Arduino.
        Frame Format: V,<left_rpm>,<right_rpm>\n
        """
        if self.serial_conn and self.serial_conn.is_open:
            command = f"V,{left_rpm:.2f},{right_rpm:.2f}\n"
            try:
                with self.lock:
                    self.serial_conn.write(command.encode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to transmit velocity command to Arduino: {e}")

    def send_emergency_stop(self):
        """Transmits instant stop signal to Arduino."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                with self.lock:
                    self.serial_conn.write(b"S\n")
                logger.warning("EMERGENCY STOP command transmitted to Arduino!")
            except Exception as e:
                logger.error(f"Failed to transmit stop command: {e}")

    def get_telemetry(self):
        """Returns thread-safe copy of latest sensor data."""
        with self.lock:
            return {
                "left_ticks": self.left_encoder_ticks,
                "right_ticks": self.right_encoder_ticks,
                "ultrasonic_cm": self.min_ultrasonic_cm,
                "timestamp": self.last_telemetry_time
            }

    def close(self):
        """Gracefully shuts down serial link."""
        self.is_running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.send_emergency_stop()
            self.serial_conn.close()
            logger.info("Serial connection closed safely.")