"""
Zero-Drift Verification Test for LidarOdometryTracker.
Ensures cart position stays frozen when physically stationary,
regardless of commanded action or is_executing flag.
RPLiDAR scan format: 3-tuple (quality, angle_deg, dist_mm)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from navigation.odometry import LidarOdometryTracker


def test_stationary_no_lidar():
    """No LiDAR data at all → pose must be completely frozen."""
    tracker = LidarOdometryTracker()
    all_pass = True
    for i in range(10):
        d, moving, pose = tracker.update_from_scan(
            None, commanded_action='MOVE_FORWARD', dt=0.1, is_executing=True)
        ok = (d == 0.0 and pose['x'] == 0.0 and pose['y'] == 0.0)
        status = 'PASS' if ok else 'FAIL'
        print(f"  [{i:02d}] delta={d:.4f}  x={pose['x']}  y={pose['y']}  [{status}]")
        if not ok:
            all_pass = False
    return all_pass


def test_stationary_constant_scan():
    """Constant LiDAR distances (no wall change) → zero displacement."""
    tracker = LidarOdometryTracker()
    # Uniform ring at 5m — simulates open space with nothing moving
    # Correct format: (quality, angle_deg, dist_mm)
    fake_scan = [(15, float(a), 5000.0) for a in range(0, 360, 5)]
    all_pass = True
    for i in range(10):
        d, moving, pose = tracker.update_from_scan(
            fake_scan, commanded_action='MOVE_FORWARD', dt=0.1, is_executing=True)
        ok = (abs(d) < 0.009 and abs(pose['x']) < 0.01 and abs(pose['y']) < 0.01)
        status = 'PASS' if ok else 'FAIL'
        print(f"  [{i:02d}] delta={d:.5f}  x={pose['x']}  y={pose['y']}  [{status}]")
        if not ok:
            all_pass = False
    return all_pass


def test_real_forward_motion():
    """
    Simulated front wall approaching → delta > 0 → x increases.
    Correct RPLiDAR format: 3-tuple (quality, angle_deg, dist_mm).
    Front sector = 340 to 360 and 0 to 20 degrees.
    """
    tracker = LidarOdometryTracker()

    def make_scan(front_dist_m, rear_dist_m=5.0):
        pts = []
        for angle in range(0, 360, 5):
            if angle >= 340 or angle <= 20:
                dist_mm = int(front_dist_m * 1000)
            elif 160 <= angle <= 200:
                dist_mm = int(rear_dist_m * 1000)
            else:
                dist_mm = 5000
            pts.append((15, float(angle), float(dist_mm)))
        return pts

    # Seed baseline references
    tracker.update_from_scan(make_scan(3.0), commanded_action='IDLE', dt=0.1, is_executing=False)

    detected_motion = False
    for i in range(5):
        front = 3.0 - (i + 1) * 0.05   # wall 5cm closer each scan
        rear  = 5.0 + (i + 1) * 0.05   # rear wall recedes
        d, moving, pose = tracker.update_from_scan(
            make_scan(front, rear), commanded_action='MOVE_FORWARD', dt=0.1, is_executing=True)
        if moving:
            detected_motion = True
        print(f"  [{i:02d}] front={front:.2f}m  delta={d:.4f}  x={pose['x']:.4f}  moving={moving}")
    status = 'PASS' if detected_motion else 'FAIL'
    print(f"  Motion detected: {detected_motion}  [{status}]")
    return detected_motion


if __name__ == '__main__':
    print("=" * 55)
    print("  LidarOdometryTracker Zero-Drift Verification")
    print("=" * 55)

    print("\n[Test 1] Stationary - no LiDAR data at all")
    r1 = test_stationary_no_lidar()

    print("\n[Test 2] Stationary - constant LiDAR ring (open space)")
    r2 = test_stationary_constant_scan()

    print("\n[Test 3] Real forward motion - wall approaching each scan")
    r3 = test_real_forward_motion()

    print("\n" + "=" * 55)
    results = [
        ("No LiDAR (full freeze)", r1),
        ("Constant scan (zero delta)", r2),
        ("Real motion detection", r3),
    ]
    all_passed = all(r for _, r in results)
    for name, result in results:
        icon = "PASS" if result else "FAIL"
        print(f"  [{icon}]  {name}")

    print("=" * 55)
    print(f"\n{'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    sys.exit(0 if all_passed else 1)
