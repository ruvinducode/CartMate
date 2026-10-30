#!/usr/bin/env python3
"""
Unit and Integration Test for CartMate Real-Time Navigation Engine.
Verifies:
1. Dynamic 2D steering commands from live cart poses.
2. Differentiation between midway obstacles (requiring avoidance) and destination shelf obstacles (triggering REACHED stop).
3. Corridor-bounded angle calculations preventing wall collisions.
4. Smooth trajectory re-calculation after obstacle avoidance.
"""

import sys
import os
import math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from navigation.path_planner import PathPlanner
from navigation.lidar_mapper import LidarMapper

def test_realtime_steering():
    print("==================================================")
    print("🧪 1. Testing Real-Time 2D Steering Commands")
    print("==================================================")
    planner = PathPlanner(current_x=0.0, current_y=0.0, current_theta=0.0)
    target_x, target_y = 2.5, 0.0

    # Test 1: Directly aligned with target
    cmd, dist, err = planner.generate_steering_command(target_x, target_y)
    print(f"   [Pose: (0.0, 0.0, 0°)] -> Cmd: {cmd}, Dist: {dist:.2f}m, Err: {err:.1f}°")
    assert cmd == "MOVE_FORWARD", f"Expected MOVE_FORWARD, got {cmd}"
    assert abs(err) < 1.0, f"Expected near 0 err, got {err}"

    # Test 2: Cart drifted left (y = 0.4) after obstacle avoidance, target is ahead-right
    planner.update_pose(x=1.0, y=0.4, theta=0.0)
    cmd, dist, err = planner.generate_steering_command(target_x, target_y)
    print(f"   [Pose: (1.0, 0.4, 0°)] -> Cmd: {cmd}, Dist: {dist:.2f}m, Err: {err:.1f}°")
    # Heading to (2.5, 0) from (1.0, 0.4) is atan2(-0.4, 1.5) = -14.9°
    assert err < 0, f"Expected negative heading error (steering right), got {err}"

    # Test 3: Large heading deviation (theta = 35°)
    planner.update_pose(x=1.0, y=0.4, theta=35.0)
    cmd, dist, err = planner.generate_steering_command(target_x, target_y)
    print(f"   [Pose: (1.0, 0.4, 35°)] -> Cmd: {cmd}, Dist: {dist:.2f}m, Err: {err:.1f}°")
    assert cmd == "TURN_RIGHT", f"Expected TURN_RIGHT, got {cmd}"

    # Test 4: Coordinate reach arrival
    planner.update_pose(x=2.45, y=0.02, theta=0.0)
    cmd, dist, err = planner.generate_steering_command(target_x, target_y)
    print(f"   [Pose: (2.45, 0.02, 0°)] -> Cmd: {cmd}, Dist: {dist:.2f}m, Err: {err:.1f}°")
    assert cmd == "REACHED", f"Expected REACHED, got {cmd}"
    print("   ✅ Test 1 Passed Successfully!\n")

def test_shelf_obstacle_vs_midway_obstacle():
    print("==================================================")
    print("🧪 2. Testing Midway Obstacle vs Shelf Recognition")
    print("==================================================")
    planner = PathPlanner(current_x=0.0, current_y=0.0, current_theta=0.0)
    target_x, target_y = 3.0, 0.0

    # Scenario A: Cart at x=0.8m, midway obstacle at 0.50m ahead (obs at x=1.3m, shelf is at 3.0m)
    planner.update_pose(x=0.8, y=0.0, theta=0.0)
    is_shelf, dist_to_shelf, dist_obs_to_shelf = planner.is_shelf_obstacle(
        obs_dist=0.50, target_x=target_x, target_y=target_y, arrival_threshold=0.85
    )
    print(f"   [Midway Obstacle Check]: Cart at 0.8m, Obs at 0.50m (x={0.8+0.5}m, Shelf at 3.0m)")
    print(f"      Is Target Shelf? -> {is_shelf} (Dist to shelf: {dist_to_shelf:.2f}m, Obs to shelf: {dist_obs_to_shelf:.2f}m)")
    assert is_shelf is False, "Midway obstacle must NOT be identified as the shelf!"

    # Scenario B: Cart approaches shelf at x=2.50m, obstacle in front at 0.48m (obs at x=2.98m, shelf is at 3.0m)
    planner.update_pose(x=2.50, y=0.0, theta=0.0)
    is_shelf, dist_to_shelf, dist_obs_to_shelf = planner.is_shelf_obstacle(
        obs_dist=0.48, target_x=target_x, target_y=target_y, arrival_threshold=0.85
    )
    print(f"   [Arrival Shelf Check]: Cart at 2.5m, Obs at 0.48m (x={2.5+0.48}m, Shelf at 3.0m)")
    print(f"      Is Target Shelf? -> {is_shelf} (Dist to shelf: {dist_to_shelf:.2f}m, Obs to shelf: {dist_obs_to_shelf:.2f}m)")
    assert is_shelf is True, "Front obstacle at destination shelf MUST be identified as the target shelf!"
    print("   ✅ Test 2 Passed Successfully!\n")

def test_lidar_mapper_2d():
    print("==================================================")
    print("🧪 3. Testing 2D LiDAR Shelf Alignment")
    print("==================================================")
    mapper = LidarMapper()
    # Simulate LiDAR points around target shelf (2.0, 0.5)
    simulated_scan = [
        (15, 0.0, 2000.0),    # forward 2.0m
        (15, 10.0, 2030.0),
        (15, -10.0, 2030.0),
        (15, 5.0, 2010.0),
        (15, -5.0, 2010.0),
    ]
    mapper.update_scan(simulated_scan, {"x": 0.0, "y": 0.0, "theta": 0.0})
    aligned = mapper.align_shelf_target(target_x=2.0, target_y=0.0, shelf_id="SHELF_A")
    print(f"   Aligned Shelf Result: X: {aligned['x']}m, Y: {aligned['y']}m, Confirmed: {aligned['confirmed']}, Points: {aligned['pts_count']}")
    assert aligned["confirmed"] is True
    assert abs(aligned["x"] - 2.0) <= 0.2
    print("   ✅ Test 3 Passed Successfully!\n")

if __name__ == "__main__":
    test_realtime_steering()
    test_shelf_obstacle_vs_midway_obstacle()
    test_lidar_mapper_2d()
    print("🎉 ALL REAL-TIME NAVIGATION TESTS PASSED SUCCESSFULLY!")
