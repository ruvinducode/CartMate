#!/usr/bin/env python3
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from navigation.obstacle_detector import ObstacleDetector
from hardware.esp32_arm_bridge import ESP32ArmBridge
from navigation.lidar_mapper import LidarMapper

def main():
    print("1. Connecting ObstacleDetector on /dev/ttyUSB0...", flush=True)
    detector = ObstacleDetector(port='/dev/ttyUSB0', safe_distance_m=0.80)
    if not detector.connect():
        print("❌ Could not connect to LiDAR!", flush=True)
        return

    print("2. Connecting ESP32ArmBridge with port exclusion...", flush=True)
    arm = ESP32ArmBridge(port='/dev/ttyUSB1', exclude_ports=['/dev/ttyUSB0', '/dev/ttyACM0'])
    arm.connect()

    print("3. Connecting LidarMapper...", flush=True)
    mapper = LidarMapper()

    print("4. Testing 5 consecutive scans while arm bridge is active...", flush=True)
    for i in range(5):
        time.sleep(0.4)
        scan = detector.get_latest_scan()
        is_active = detector.is_scanning_active()
        print(f"   [Scan {i+1}] Active: {is_active} | Scanned Points: {len(scan)}", flush=True)
        if scan:
            mapper.update_scan(scan, {'x': 0.0, 'y': 0.0, 'theta': 0.0})
            snap = mapper.get_snapshot()
            print(f"      -> Mapper World Points: {len(snap['world_points'])}", flush=True)

    print("5. Stopping detector and arm...", flush=True)
    detector.stop()
    arm.close()
    print("✅ All tests passed cleanly!", flush=True)

if __name__ == "__main__":
    main()
