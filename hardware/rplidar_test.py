#!/usr/bin/env python3
import time
from rplidar import RPLidar

PORT_NAME = '/dev/ttyUSB0'

def main():
    print("🛰️ Connecting to RPLiDAR A1 on /dev/ttyUSB0...")
    try:
        lidar = RPLidar(PORT_NAME)
        info = lidar.get_info()
        health = lidar.get_health()
        
        print(f"✅ RPLiDAR Connected Successfully!")
        print(f"ℹ️ Device Info: {info}")
        print(f"🩺 Device Health: {health}")
        print("\n📡 Reading Scan Data (Press Ctrl+C to stop)...")

        for i, scan in enumerate(lidar.iter_scans()):
            print(f"Scan {i+1}: Received {len(scan)} data points")
            if i >= 10:  # Sample test එකක් ලෙස Scans 10ක් බලමු
                break

        lidar.stop()
        lidar.stop_motor()
        lidar.disconnect()
        print("🛑 RPLiDAR Test Completed Successfully!")

    except Exception as e:
        print(f"❌ RPLiDAR Error: {e}")

if __name__ == "__main__":
    main()