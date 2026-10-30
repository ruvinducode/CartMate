#!/usr/bin/env python3
import time
import math
import threading
from rplidar import RPLidar

# Safe patch for RPLidar upstream bug where get_health() returns a string when buffer is non-empty
_orig_rplidar_get_health = RPLidar.get_health
_orig_rplidar_start = RPLidar.start

def _safe_get_health(self):
    try:
        if hasattr(self, '_serial') and self._serial and self._serial.inWaiting() > 0:
            self._serial.flushInput()
        health = _orig_rplidar_get_health(self)
        if isinstance(health, tuple) and len(health) == 2:
            return health
    except Exception:
        pass
    if hasattr(self, '_serial') and self._serial:
        self._serial.flushInput()
    try:
        health = _orig_rplidar_get_health(self)
        if isinstance(health, tuple) and len(health) == 2:
            return health
    except Exception:
        pass
    return ('Good', 0)

def _safe_start(self, scan_type='normal'):
    if hasattr(self, '_serial') and self._serial and self._serial.inWaiting() > 0:
        self._serial.flushInput()
    try:
        return _orig_rplidar_start(self, scan_type)
    except ValueError as e:
        if "too many values to unpack" in str(e):
            if hasattr(self, '_serial') and self._serial:
                self._serial.flushInput()
            return _orig_rplidar_start(self, scan_type)
        raise

RPLidar.get_health = _safe_get_health
RPLidar.start = _safe_start

class ObstacleDetector:
    def __init__(self, port='/dev/ttyUSB0', safe_distance_m=0.20, lidar_angle_offset=0.0):
        self.port = port
        self.safe_distance_m = safe_distance_m
        self.safe_distance_mm = safe_distance_m * 1000.0  # Convert meters to mm (20cm default)
        self.lidar_angle_offset = lidar_angle_offset
        self.lidar = None
        self.is_running = False
        self.lock = threading.Lock()
        self.latest_scan = []
        self.last_scan_time = 0.0
        self.scan_count = 0
        self.scan_thread = None

    def connect(self):
        try:
            print(f"🛰️ Initializing RPLiDAR on {self.port}...")
            self.lidar = RPLidar(self.port)
            if hasattr(self.lidar, '_serial') and self.lidar._serial:
                self.lidar._serial.flushInput()
            print("✅ RPLiDAR Connected for Obstacle Detection (50cm Safety Threshold)!")
            self.is_running = True
            
            # Start persistent background scanning thread for full 360° coverage
            self.scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
            self.scan_thread.start()
            return True
        except Exception as e:
            print(f"❌ Failed to connect RPLiDAR: {e}")
            return False

    def _scan_loop(self):
        """Continuously reads full 360° scans from RPLiDAR with automatic recovery on packet loss"""
        consecutive_errors = 0
        while self.is_running and self.lidar:
            try:
                for scan in self.lidar.iter_scans(max_buf_meas=6000):
                    if not self.is_running:
                        break
                    if scan and len(scan) > 5:
                        with self.lock:
                            self.latest_scan = list(scan)
                            self.last_scan_time = time.time()
                            self.scan_count += 1
                        consecutive_errors = 0
            except Exception as e:
                if not self.is_running:
                    break
                consecutive_errors += 1
                if consecutive_errors % 10 == 1:
                    print(f"⚠️ [RPLiDAR] Scan interrupted ({e}). Auto-resynchronizing stream...")

                # Clean and resynchronize serial buffer
                try:
                    if self.lidar:
                        self.lidar.stop()
                        time.sleep(0.05)
                        if hasattr(self.lidar, '_serial') and self.lidar._serial:
                            self.lidar._serial.flushInput()
                        if hasattr(self.lidar, 'clean_input'):
                            self.lidar.clean_input()
                except Exception:
                    pass

                # If desync is persistent (e.g. DTR toggle or hardware glitch), reconnect cleanly
                if consecutive_errors > 20:
                    print(f"🔄 [RPLiDAR] Persistent error detected. Reconnecting serial link...")
                    try:
                        self.lidar.disconnect()
                        time.sleep(0.5)
                        self.lidar.connect()
                        self.lidar.start_motor()
                        time.sleep(0.2)
                        consecutive_errors = 0
                    except Exception as re_err:
                        print(f"❌ [RPLiDAR] Reconnection failed: {re_err}")
                        time.sleep(1.0)
                else:
                    time.sleep(0.05)

    def get_latest_scan(self):
        """Returns thread-safe latest complete 360° scan"""
        with self.lock:
            return list(self.latest_scan)

    def is_scanning_active(self, max_stale_sec=1.5):
        """Checks if LiDAR is actively producing fresh scan frames"""
        with self.lock:
            return (time.time() - self.last_scan_time) < max_stale_sec and self.scan_count > 0

    def check_front_obstacle(self, scan_data, threshold_m=None, corridor_half_width_m=0.32):
        """
        RPLiDAR scan data array: [(quality, angle, distance_mm), ...]
        Checks front safety zone directly in the cart's forward driving corridor.
        corridor_half_width_m: ±32cm lateral corridor (64cm total width, fits 38cm chassis).
        Ignores side shelves/aisle walls to prevent false obstacle stops.
        """
        threshold_mm = (threshold_m * 1000.0) if threshold_m is not None else self.safe_distance_mm
        front_min_distance = float('inf')
        obstacle_detected = False

        min_chassis_dist_mm = 60.0  # Ignore robot frame/noise within 6cm
        corridor_half_width_mm = corridor_half_width_m * 1000.0

        for point in scan_data:
            quality, raw_angle, distance_mm = point
            
            # Ignore invalid readings or cart's own body frame (< 15cm)
            if distance_mm <= min_chassis_dist_mm or distance_mm > 8000.0:
                continue

            # Apply LiDAR mounting offset
            angle = (raw_angle + self.lidar_angle_offset) % 360.0

            # Forward Cartesian projection: rx = forward distance, ry = lateral distance
            rad = math.radians(angle)
            rx_mm = distance_mm * math.cos(rad)
            ry_mm = distance_mm * math.sin(rad)

            # Only points in FRONT of the chassis
            if rx_mm <= min_chassis_dist_mm:
                continue

            # Check if point is inside the front driving corridor:
            # 1. Forward distance is within safety threshold
            # 2. Lateral distance is within the cart corridor (±32cm)
            is_in_front_corridor = (rx_mm <= threshold_mm and abs(ry_mm) <= corridor_half_width_mm)

            # Focused front cone: ±25° (335° to 25°)
            is_in_front_cone = (angle >= 335.0 or angle <= 25.0)

            if is_in_front_corridor or (is_in_front_cone and abs(ry_mm) <= corridor_half_width_mm * 1.2):
                if distance_mm < front_min_distance:
                    front_min_distance = distance_mm

                # Trigger obstacle flag only if directly obstructing forward path
                if distance_mm <= threshold_mm and abs(ry_mm) <= corridor_half_width_mm:
                    obstacle_detected = True

        min_dist_m = (front_min_distance / 1000.0) if front_min_distance != float('inf') else 9.99
        return obstacle_detected, min_dist_m

    def get_avoidance_direction(self, scan_data):
        """
        Determines whether steering left or right provides better clearance around front obstacle.
        Returns: ('TURN_LEFT' or 'TURN_RIGHT', clearance_m)
        """
        sectors = self.get_sector_clearances(scan_data)
        left_clear = sectors.get("left", 0.0)
        right_clear = sectors.get("right", 0.0)
        if left_clear >= right_clear:
            return "TURN_LEFT", left_clear
        else:
            return "TURN_RIGHT", right_clear

    def get_sector_clearances(self, scan_data):
        """
        Returns minimum distance in Front, Left, Right, and Rear sectors (in meters).
        Useful for determining which side has more clearance when avoiding obstacles.
        """
        front_min = float('inf')
        left_min = float('inf')
        right_min = float('inf')
        rear_min = float('inf')

        for point in scan_data:
            quality, raw_angle, dist_mm = point
            if dist_mm <= 60.0 or dist_mm > 8000.0:
                continue

            angle = (raw_angle + self.lidar_angle_offset) % 360.0

            if angle >= 335.0 or angle <= 25.0:
                if dist_mm < front_min: front_min = dist_mm
            elif 25.0 < angle <= 110.0:
                if dist_mm < left_min: left_min = dist_mm
            elif 250.0 <= angle < 335.0:
                if dist_mm < right_min: right_min = dist_mm
            elif 145.0 <= angle <= 215.0:
                if dist_mm < rear_min: rear_min = dist_mm

        return {
            "front": front_min / 1000.0 if front_min != float('inf') else 9.99,
            "left": left_min / 1000.0 if left_min != float('inf') else 9.99,
            "right": right_min / 1000.0 if right_min != float('inf') else 9.99,
            "rear": rear_min / 1000.0 if rear_min != float('inf') else 9.99,
        }

    def stop(self):
        self.is_running = False
        if self.lidar:
            try:
                self.lidar.stop()
                self.lidar.stop_motor()
                self.lidar.disconnect()
                print("🛑 RPLiDAR Stopped Safely.")
            except Exception as e:
                print(f"⚠️ Error stopping LiDAR: {e}")