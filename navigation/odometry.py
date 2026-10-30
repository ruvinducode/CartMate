"""
Odometry Integrator Module (CartMate Subsystem 1)
Calculates real-time Cart Pose (x, y, theta) using wheel encoder ticks from Arduino
and heading updates from IMU.
"""

import math
import time
import logging
from config import WHEEL_RADIUS, TRACK_WIDTH, ENCODER_TPR

logger = logging.getLogger("CartMate.Odometry")

class CartOdometry:
    def __init__(self, wheel_radius=WHEEL_RADIUS, track_width=TRACK_WIDTH, tpr=ENCODER_TPR):
        self.R = wheel_radius
        self.L = track_width
        self.TPR = tpr

        # Robot Pose State: x (m), y (m), theta (rad)
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0

        # Encoder tracking
        self.last_left_ticks = 0
        self.last_right_ticks = 0
        self.is_first_update = True
        self.last_time = time.time()

        # Distance per pulse
        self.dist_per_tick = (2.0 * math.pi * self.R) / float(self.TPR)

    def update(self, current_left_ticks: int, current_right_ticks: int, imu_yaw_rad: float = None):
        """
        Updates the cart pose based on new encoder tick measurements.
        Optionally fuses external IMU yaw angle if available.
        """
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        if self.is_first_update:
            self.last_left_ticks = current_left_ticks
            self.last_right_ticks = current_right_ticks
            self.is_first_update = False
            return self.get_pose()

        # Calculate pulse differences
        delta_left_ticks = current_left_ticks - self.last_left_ticks
        delta_right_ticks = current_right_ticks - self.last_right_ticks

        self.last_left_ticks = current_left_ticks
        self.last_right_ticks = current_right_ticks

        # Distance traveled by each wheel
        d_left = delta_left_ticks * self.dist_per_tick
        d_right = delta_right_ticks * self.dist_per_tick

        # Center displacement and angular change
        d_center = (d_right + d_left) / 2.0
        d_theta = (d_right - d_left) / self.L

        # Pose integration using Midpoint Method
        if imu_yaw_rad is not None:
            # Fuse IMU heading directly for orientation correction
            self.theta = imu_yaw_rad
        else:
            self.theta += d_theta

        # Normalize theta between -pi and +pi
        self.theta = math.atan2(math.sin(self.theta), math.cos(self.theta))

        # Update spatial coordinates (x, y)
        self.x += d_center * math.cos(self.theta)
        self.y += d_center * math.sin(self.theta)

        return self.get_pose()

    def get_pose(self):
        """Returns current pose dictionary."""
        return {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "theta": round(self.theta, 3)
        }

    def reset_pose(self, x=0.0, y=0.0, theta=0.0):
        """Resets pose coordinates to specified baseline."""
        self.x = x
        self.y = y
        self.theta = theta
        self.is_first_update = True
        logger.info(f"Odometry pose reset to x:{x}, y:{y}, theta:{theta}")


class LidarOdometryTracker:
    """
    Physical Real-Time Motion & Displacement Tracker using RPLiDAR 360° Scans.
    Guarantees that the Cart pose updates ONLY when the physical robot actually moves.
    Eliminates fake clock-based coordinate drift ('nikanuth command maru wena eka').
    """
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
        self.last_update_time = time.time()

    def reset(self, x=0.0, y=0.0, theta=0.0):
        self.x = x
        self.y = y
        self.theta = theta
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
            if len(pt) < 3:
                continue
            q, angle, dist_mm = pt[0], pt[1], pt[2]
            if dist_mm < 150 or dist_mm > 8000:
                continue
            dist_m = dist_mm / 1000.0

            # Front cone: 340° to 20°
            if angle >= 340.0 or angle <= 20.0:
                front_pts.append(dist_m)
            # Rear cone: 160° to 200°
            elif 160.0 <= angle <= 200.0:
                rear_pts.append(dist_m)
            # Left cone: 70° to 110°
            elif 70.0 <= angle <= 110.0:
                left_pts.append(dist_m)
            # Right cone: 250° to 290°
            elif 250.0 <= angle <= 290.0:
                right_pts.append(dist_m)

        f_med = sorted(front_pts)[len(front_pts)//2] if front_pts else None
        r_med = sorted(rear_pts)[len(rear_pts)//2] if rear_pts else None
        l_med = sorted(left_pts)[len(left_pts)//2] if left_pts else None
        rt_med = sorted(right_pts)[len(right_pts)//2] if right_pts else None

        return f_med, r_med, l_med, rt_med

    def update_from_scan(self, scan_data, commanded_action="IDLE", dt=0.1, is_executing=False):
        """
        Calculates physical displacement ONLY from real RPLiDAR scan changes.
        
        Key guarantee: If cart is stationary (no physical movement), delta_forward = 0.0
        and cart_x / cart_y do NOT change — no fake drift, no map creep.
        
        Turns (TURN_LEFT / TURN_RIGHT): Cart rotates in-place (differential drive).
        Position (x, y) does NOT change during a turn; only theta changes.
        """
        now = time.time()
        if dt <= 0:
            dt = max(0.01, min(now - self.last_update_time, 0.5))
        self.last_update_time = now

        f_med, r_med, l_med, rt_med = self._extract_sector_medians(scan_data) if scan_data else (None, None, None, None)

        # Detect action transition (e.g. TURN -> MOVE_FORWARD or start of new action)
        # Re-seed baseline reference distances so perspective shift is never mistaken for physical forward motion
        if getattr(self, "last_action", None) != commanded_action:
            self.last_front_dist = f_med
            self.last_rear_dist = r_med
            self.last_left_dist = l_med
            self.last_right_dist = rt_med
            self.last_action = commanded_action
            return 0.0, False, {
                "x": round(self.x, 3),
                "y": round(self.y, 3),
                "theta": round(self.theta, 1)
            }
        self.last_action = commanded_action

        delta_forward = 0.0
        deltas = []

        # Front distance decreasing = cart moving forward
        if self.last_front_dist is not None and f_med is not None:
            df = self.last_front_dist - f_med
            if -0.25 <= df <= 0.25:   # Plausible per-scan motion window
                deltas.append(df)

        # Rear distance increasing = cart moving forward
        if self.last_rear_dist is not None and r_med is not None:
            dr = r_med - self.last_rear_dist
            if -0.25 <= dr <= 0.25:
                deltas.append(dr)

        if deltas:
            delta_forward = sum(deltas) / len(deltas)
            # Deadband: ignore sub-8mm jitter (vibration / sensor noise)
            if abs(delta_forward) < 0.008:
                delta_forward = 0.0

        # Update LiDAR baseline references for next cycle
        if f_med is not None: self.last_front_dist = f_med
        if r_med is not None: self.last_rear_dist = r_med
        if l_med is not None: self.last_left_dist = l_med
        if rt_med is not None: self.last_right_dist = rt_med

        # ⚠️ NO fake fallback here.
        # If LiDAR sees no displacement → delta_forward stays 0.0.
        # Cart position NEVER advances from a clock/timer alone.

        self.is_moving = abs(delta_forward) > 0.005

        # Differential-drive turns: in-place rotation only (x, y unchanged)
        if commanded_action == "TURN_LEFT" and is_executing:
            self.theta += 20.0 * dt
        elif commanded_action == "TURN_RIGHT" and is_executing:
            self.theta -= 20.0 * dt

        while self.theta > 180.0: self.theta -= 360.0
        while self.theta < -180.0: self.theta += 360.0

        # Update Cartesian pose ONLY when LiDAR confirms actual physical movement
        if abs(delta_forward) > 0.0 and commanded_action in ("MOVE_FORWARD", "MOVE_BACKWARD"):
            rad = math.radians(self.theta)
            self.x += delta_forward * math.cos(rad)
            self.y += delta_forward * math.sin(rad)
            self.total_distance_moved += abs(delta_forward)

        return delta_forward, self.is_moving, {
            "x": round(self.x, 3),
            "y": round(self.y, 3),
            "theta": round(self.theta, 1)
        }