#!/usr/bin/env python3
import math
import time

class PathPlanner:
    def __init__(self, current_x=0.0, current_y=0.0, current_theta=0.0):
        # Cart pose: current_x is distance along track, current_theta is heading angle
        self.current_x = current_x
        self.current_y = current_y
        self.current_theta = current_theta
        self._is_turning = False  # Hysteresis state to prevent oscillating turns

    def update_pose(self, x, y, theta):
        """Update current estimated cart pose"""
        self.current_x = x
        self.current_y = y
        self.current_theta = theta

    def calculate_heading_and_distance(self, target_x, target_y=0.0, max_corridor_angle=15.0):
        """
        Calculates real-time Euclidean distance and heading error from current cart pose
        (x, y, theta) towards target coordinates (target_x, target_y).
        Caps maximum corridor heading to prevent sharp turns into aisle walls.
        """
        dx = target_x - self.current_x
        dy = target_y - self.current_y
        distance = math.hypot(dx, dy)

        # Target angle in world frame
        raw_target_heading = math.degrees(math.atan2(dy, dx))

        # Corridor bound: If moving primarily along X corridor (dx >= 0), limit desired angle
        # so cart smoothly merges towards target without crashing into side shelves
        if dx >= 0:
            desired_heading = max(-max_corridor_angle, min(max_corridor_angle, raw_target_heading))
        else:
            # Reversing or navigating backward along corridor (-X)
            rev_angle = 180.0 if raw_target_heading >= 0 else -180.0
            desired_heading = rev_angle

        # Heading error relative to cart's current real-time orientation (-180° to +180°)
        heading_error = desired_heading - self.current_theta
        while heading_error > 180.0:
            heading_error -= 360.0
        while heading_error < -180.0:
            heading_error += 360.0

        return distance, heading_error

    def is_shelf_obstacle(self, obs_dist, target_x, target_y=0.0, arrival_threshold=0.85):
        """
        Determines whether a front obstacle detected by LiDAR is the target shelf itself
        or an unexpected midway obstacle.
        Returns (is_shelf, dist_to_target, dist_obs_to_shelf)
        """
        dx = target_x - self.current_x
        dy = target_y - self.current_y
        dist_to_target = math.hypot(dx, dy)

        # Compute obstacle position in global frame based on current cart pose
        rad = math.radians(self.current_theta)
        obs_x = self.current_x + obs_dist * math.cos(rad)
        obs_y = self.current_y + obs_dist * math.sin(rad)

        dist_obs_to_shelf = math.hypot(target_x - obs_x, target_y - obs_y)

        # Considered the target shelf if cart has approached within arrival threshold
        # and the detected obstacle matches the shelf location
        is_shelf = (dist_to_target <= arrival_threshold) and (dist_obs_to_shelf <= 0.75 or obs_dist <= 0.65)
        return is_shelf, dist_to_target, dist_obs_to_shelf

    def generate_steering_command(self, target_x, target_y=0.0, angle_tolerance=18.0, reach_tolerance=0.25):
        """ 
        Generates real-time steering command based on current live cart position.
        Commands: MOVE_FORWARD, TURN_LEFT, TURN_RIGHT, REACHED
        """
        distance, heading_error = self.calculate_heading_and_distance(target_x, target_y)

        # 1. Target Reached Check
        if distance <= reach_tolerance:
            self._is_turning = False
            return "REACHED", distance, 0.0

        abs_err = abs(heading_error)

        # 2. Hysteresis steering to prevent rapid twitching
        exit_tolerance = min(8.0, angle_tolerance * 0.5)

        if self._is_turning:
            # Continue gentle turn until within exit tolerance
            if abs_err <= exit_tolerance:
                self._is_turning = False
                return "MOVE_FORWARD", distance, heading_error
            else:
                cmd = "TURN_LEFT" if heading_error > 0 else "TURN_RIGHT"
                return cmd, distance, heading_error
        else:
            # If well-aligned with target vector, drive forward
            if abs_err <= angle_tolerance:
                return "MOVE_FORWARD", distance, heading_error
            else:
                self._is_turning = True
                cmd = "TURN_LEFT" if heading_error > 0 else "TURN_RIGHT"
                return cmd, distance, heading_error


# Standalone Testing Block
if __name__ == "__main__":
    planner = PathPlanner(current_x=0.0, current_y=0.0, current_theta=0.0)
    
    # Example Target: Shelf A (X: 1.8m, Y: 0.2m)
    target_x, target_y = 1.8, 0.2
    print(f"🗺️ Path Planner Initialized at (0.0m, 0.0m, 0.0°)")
    print(f"🎯 Target Point: (X: {target_x}m, Y: {target_y}m)\n")

    cmd, dist, angle_err = planner.generate_steering_command(target_x, target_y)
    print(f"📡 Real-time Navigation Calculations:")
    print(f"   Distance to Target : {dist:.2f}m")
    print(f"   Heading Angle Error: {angle_err:.2f}°")
    print(f"   Steering Command   : 🚀 [{cmd}]")

    # Test shelf arrival obstacle detection
    planner.update_pose(x=1.3, y=0.1, theta=5.0)
    is_shelf, d_target, d_obs = planner.is_shelf_obstacle(obs_dist=0.52, target_x=target_x, target_y=target_y)
    print(f"\n🎯 Shelf Obstacle Check (at cart pose 1.3m):")
    print(f"   Is Obstacle the Shelf? -> {is_shelf} (Dist to target: {d_target:.2f}m, Obs to shelf: {d_obs:.2f}m)")