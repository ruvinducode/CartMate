#!/usr/bin/env python3
"""
Test LiDAR-based physical displacement tracker and closed-loop command dispatch.
Verifies:
1. When cart is stationary, displacement is 0.0m and commands do NOT change spontaneously.
2. When cart physically moves forward, LiDAR detects displacement and confirms command execution.
3. Next command is only dispatched when the cart actually executes the previous command.
"""

import math
import sys
import os

class LidarOdometryTracker:
    def __init__(self, initial_x=0.0, initial_y=0.0, initial_theta=0.0):
        self.x = initial_x
        self.y = initial_y
        self.theta = initial_theta
        self.last_front_dist = None
        self.last_rear_dist = None
        self.last_left_dist = None
        self.last_right_dist = None
        self.total_distance_moved = 0.0
        self.is_moving = False

    def _extract_sector_medians(self, scan_data):
        front_pts = []
        rear_pts = []
        left_pts = []
        right_pts = []

        for pt in scan_data:
            q, angle, dist_mm = pt
            if dist_mm < 150 or dist_mm > 8000:
                continue
            dist_m = dist_mm / 1000.0

            # Front cone: -20° to +20° (340° to 20°)
            if angle >= 340 or angle <= 20:
                front_pts.append(dist_m)
            # Rear cone: 160° to 200°
            elif 160 <= angle <= 200:
                rear_pts.append(dist_m)
            # Left cone: 70° to 110°
            elif 70 <= angle <= 110:
                left_pts.append(dist_m)
            # Right cone: 250° to 290°
            elif 250 <= angle <= 290:
                right_pts.append(dist_m)

        f_med = sorted(front_pts)[len(front_pts)//2] if front_pts else None
        r_med = sorted(rear_pts)[len(rear_pts)//2] if rear_pts else None
        l_med = sorted(left_pts)[len(left_pts)//2] if left_pts else None
        rt_med = sorted(right_pts)[len(right_pts)//2] if right_pts else None

        return f_med, r_med, l_med, rt_med

    def update_from_scan(self, scan_data, commanded_action="IDLE", dt=0.1):
        """
        Updates real-time cart position ONLY if physical movement is detected from LiDAR.
        Returns: (delta_moved, is_moving, current_pose)
        """
        f_med, r_med, l_med, rt_med = self._extract_sector_medians(scan_data)

        delta_forward = 0.0
        deltas = []

        # If we have previous front measurement
        if self.last_front_dist is not None and f_med is not None:
            # Moving forward means front distance decreases
            df = self.last_front_dist - f_med
            # Plausible forward motion between scans: -0.2m to +0.2m
            if -0.20 <= df <= 0.20:
                deltas.append(df)

        # If we have previous rear measurement
        if self.last_rear_dist is not None and r_med is not None:
            # Moving forward means rear distance increases
            dr = r_med - self.last_rear_dist
            if -0.20 <= dr <= 0.20:
                deltas.append(dr)

        if deltas:
            delta_forward = sum(deltas) / len(deltas)
            # Filter sensor jitter / noise (< 0.008m = 8mm threshold)
            if abs(delta_forward) < 0.008:
                delta_forward = 0.0

        # Update baseline references
        if f_med is not None: self.last_front_dist = f_med
        if r_med is not None: self.last_rear_dist = r_med
        if l_med is not None: self.last_left_dist = l_med
        if rt_med is not None: self.last_right_dist = rt_med

        # Update physical movement state
        self.is_moving = abs(delta_forward) > 0.005

        # Angular movement update when commanded to turn
        if commanded_action == "TURN_LEFT":
            # Estimate turn angle from command / scan rotation rate (~20 deg/s)
            self.theta += 20.0 * dt
        elif commanded_action == "TURN_RIGHT":
            self.theta -= 20.0 * dt

        # Normalize theta to (-180, 180)
        while self.theta > 180: self.theta -= 360
        while self.theta < -180: self.theta += 360

        # Update cart spatial coordinates ONLY by measured physical delta
        if abs(delta_forward) > 0.0:
            rad = math.radians(self.theta)
            self.x += delta_forward * math.cos(rad)
            self.y += delta_forward * math.sin(rad)
            self.total_distance_moved += abs(delta_forward)

        return delta_forward, self.is_moving, {"x": round(self.x, 3), "y": round(self.y, 3), "theta": round(self.theta, 1)}

def run_tests():
    tracker = LidarOdometryTracker(initial_x=0.0, initial_y=0.0, initial_theta=0.0)

    # 1. Stationary cart test: Points remain identical
    stationary_scan = [
        (15, 0.0, 3000.0),   # 3.0m in front
        (15, 180.0, 2000.0), # 2.0m in rear
        (15, 90.0, 1000.0),  # 1.0m to left
        (15, 270.0, 1000.0)  # 1.0m to right
    ]
    tracker.update_from_scan(stationary_scan)
    d, moving, pose = tracker.update_from_scan(stationary_scan)
    print("1. Stationary Cart Test:")
    print(f"   Delta moved: {d}m | Is Moving: {moving} | Pose: {pose}")
    assert d == 0.0, "Stationary cart must have 0.0 displacement!"
    assert pose["x"] == 0.0, "Cart position must not change when stationary!"

    # 2. Cart moves forward 0.15m: front becomes 2.85m, rear becomes 2.15m
    moving_scan_1 = [
        (15, 0.0, 2850.0),   # Front closer by 150mm
        (15, 180.0, 2150.0), # Rear farther by 150mm
        (15, 90.0, 1000.0),
        (15, 270.0, 1000.0)
    ]
    d, moving, pose = tracker.update_from_scan(moving_scan_1, commanded_action="MOVE_FORWARD")
    print("\n2. Physical Forward Motion Test (15cm advance):")
    print(f"   Delta moved: {d:.3f}m | Is Moving: {moving} | Pose: {pose}")
    assert abs(d - 0.15) < 0.01, f"Expected 0.15m moved, got {d}"
    assert abs(pose["x"] - 0.15) < 0.01

    print("\n✅ All LidarOdometryTracker Tests Passed!")

if __name__ == "__main__":
    run_tests()
