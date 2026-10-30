#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from navigation.obstacle_detector import ObstacleDetector

def test_obstacle_threshold():
    detector = ObstacleDetector()
    print(f"Default safe_distance_m: {detector.safe_distance_m}m ({detector.safe_distance_mm}mm)", flush=True)
    assert detector.safe_distance_m == 0.20, f"Expected 0.20, got {detector.safe_distance_m}"
    assert detector.safe_distance_mm == 200.0, f"Expected 200.0, got {detector.safe_distance_mm}"

    # 1. Obstacle at 25cm (250mm) - should NOT trigger obstacle flag
    scan_25cm = [(15, 0.0, 250.0)]
    blocked, dist = detector.check_front_obstacle(scan_25cm)
    print(f"Test 25cm (outside): blocked={blocked}, min_dist={dist:.2f}m", flush=True)
    assert not blocked, "25cm obstacle should not trigger block"

    # 2. Obstacle at 18cm (180mm) - SHOULD trigger obstacle flag
    scan_18cm = [(15, 0.0, 180.0)]
    blocked, dist = detector.check_front_obstacle(scan_18cm)
    print(f"Test 18cm (inside 20cm): blocked={blocked}, min_dist={dist:.2f}m", flush=True)
    assert blocked, "18cm obstacle should trigger block"
    assert round(dist, 2) == 0.18

    # 3. Obstacle at 10cm (100mm) - SHOULD trigger obstacle flag
    scan_10cm = [(15, 0.0, 100.0)]
    blocked, dist = detector.check_front_obstacle(scan_10cm)
    print(f"Test 10cm (close range): blocked={blocked}, min_dist={dist:.2f}m", flush=True)
    assert blocked, "10cm obstacle should trigger block"
    assert round(dist, 2) == 0.10

    print("🎉 All 20cm obstacle detector tests PASSED!", flush=True)

if __name__ == "__main__":
    test_obstacle_threshold()
