#!/usr/bin/env python3
import time
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from navigation.obstacle_detector import ObstacleDetector

def main():
    print("🛰️ Connecting to RPLiDAR on /dev/ttyUSB0...")
    detector = ObstacleDetector(port='/dev/ttyUSB0', safe_distance_m=0.70)
    if not detector.connect():
        print("❌ Could not connect to LiDAR.")
        return

    print("✅ LiDAR connected. Waiting 2s for 360° scan buffer...")
    time.sleep(2)

    try:
        for _ in range(15):
            scan = detector.get_latest_scan()
            if scan:
                is_blocked, min_front = detector.check_front_obstacle(scan, threshold_m=0.70)
                sectors = detector.get_sector_clearances(scan)
                print(f"📡 Scanned {len(scan)} pts | Front Min: {min_front:.2f}m (Blocked: {is_blocked}) | "
                      f"Left: {sectors['left']:.2f}m | Right: {sectors['right']:.2f}m | Rear: {sectors['rear']:.2f}m")
            else:
                print("⏳ Waiting for scan data...")
            time.sleep(0.5)
    finally:
        detector.stop()

if __name__ == "__main__":
    main()
