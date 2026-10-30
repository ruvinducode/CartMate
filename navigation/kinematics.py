"""
Differential Drive Kinematics Module
Translates high-level linear velocity (v) and angular velocity (w) 
into left/right wheel Target RPMs using physical cart geometry.
"""

import math
from config import WHEEL_RADIUS, TRACK_WIDTH, MAX_LINEAR_VELOCITY, MAX_ANGULAR_VELOCITY

class DifferentialKinematics:
    def __init__(self, wheel_radius=WHEEL_RADIUS, track_width=TRACK_WIDTH):
        self.R = wheel_radius
        self.L = track_width

    def clamp(self, value, min_val, max_val):
        return max(min_val, min(value, max_val))

    def twist_to_wheel_speeds(self, linear_v: float, angular_w: float):
        """
        Converts (v, w) into left and right wheel RPM values.
        
        :param linear_v: Linear velocity in m/s (forward/backward)
        :param angular_w: Angular velocity in rad/s (rotation)
        :return: Tuple (left_rpm, right_rpm)
        """
        # Clamp velocity inputs within safe hardware thresholds
        v = self.clamp(linear_v, -MAX_LINEAR_VELOCITY, MAX_LINEAR_VELOCITY)
        w = self.clamp(angular_w, -MAX_ANGULAR_VELOCITY, MAX_ANGULAR_VELOCITY)

        # Differential drive inverse kinematics formula:
        # w_left  = (v - (w * L / 2)) / R  [rad/s]
        # w_right = (v + (w * L / 2)) / R  [rad/s]
        w_left_rad = (v - (w * self.L / 2.0)) / self.R
        w_right_rad = (v + (w * self.L / 2.0)) / self.R

        # Convert Angular Velocity (rad/s) to Revolutions Per Minute (RPM)
        # RPM = (rad/s) * (60 / 2pi)
        rad_to_rpm = 60.0 / (2.0 * math.pi)
        left_rpm = w_left_rad * rad_to_rpm
        right_rpm = w_right_rad * rad_to_rpm

        return round(left_rpm, 2), round(right_rpm, 2)