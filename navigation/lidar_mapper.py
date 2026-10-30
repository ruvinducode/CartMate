#!/usr/bin/env python3
"""
CartMate 2D LiDAR Mapping & Shelf Alignment Engine
Converts RPLiDAR 360° scans to 2D Cartesian map coordinates,
aligns App MQTT waypoints with real-world physical shelf surfaces,
and renders visual map artifacts.
"""

import math
import time
import threading
import numpy as np
try:
    import matplotlib
    matplotlib.use('Agg')  # Headless backend for Raspberry Pi / SSH
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

class LidarMapper:
    def __init__(self, map_range_m=6.0, grid_resolution_m=0.05):
        self.map_range_m = map_range_m
        self.grid_resolution_m = grid_resolution_m
        self.lock = threading.Lock()
        
        # Latest 2D point cloud in World Coordinates: [(x, y), ...]
        self.world_points = []
        # Latest point cloud in Robot Coordinates: [(x, y), ...]
        self.robot_points = []
        
        # Shelf alignment cache: {shelf_id: {"x": ..., "y": ..., "confirmed": bool, "detected_pts": int}}
        self.aligned_shelves = {}
        
        # Multi-scan persistence buffer (rolling 3 full revolutions)
        self.history = []
        
        # Last map generation timestamp
        self.last_map_save_time = 0.0

    def polar_to_cartesian(self, angle_deg, dist_mm):
        """Converts RPLiDAR polar reading (angle in degrees, distance in mm) to meters (x, y)"""
        dist_m = dist_mm / 1000.0
        angle_rad = math.radians(angle_deg)
        # Standard robot frame: 0° forward (+X), 90° left (+Y), 180° rear (-X), 270° right (-Y)
        rx = dist_m * math.cos(angle_rad)
        ry = dist_m * math.sin(angle_rad)
        return rx, ry

    def update_scan(self, scan_data, cart_pose):
        """
        Updates map points using current LiDAR scan and Cart Pose.
        cart_pose: dict with 'x', 'y', 'theta' (theta in degrees)
        """
        if not scan_data:
            return

        cx = cart_pose.get("x", 0.0)
        cy = cart_pose.get("y", 0.0)
        ctheta_rad = math.radians(cart_pose.get("theta", 0.0))
        cos_t = math.cos(ctheta_rad)
        sin_t = math.sin(ctheta_rad)

        new_robot_pts = []
        new_world_pts = []

        for point in scan_data:
            quality, angle, dist_mm = point
            if dist_mm <= 60.0 or dist_mm > (self.map_range_m * 1000.0):  # Ignore body frame < 6cm
                continue

            rx, ry = self.polar_to_cartesian(angle, dist_mm)
            new_robot_pts.append((round(rx, 3), round(ry, 3)))

            # Transform into Global World coordinates based on Cart Pose
            wx = cx + (rx * cos_t - ry * sin_t)
            wy = cy + (rx * sin_t + ry * cos_t)
            new_world_pts.append((round(wx, 3), round(wy, 3)))

        self.history.append(new_world_pts)
        if len(self.history) > 2:  # Keep last 2 revolutions (2 × ~100pts = ~200pts max)
            self.history.pop(0)

        # Merge recent revolutions for dense 360° coverage
        all_pts = []
        for s in self.history:
            all_pts.extend(s)

        # Voxel-grid deduplication: snap to 5cm grid, keep unique cells only
        # This removes near-duplicate points from overlapping scans without losing wall detail
        seen = set()
        deduped = []
        for wx, wy in all_pts:
            cell = (int(wx / 0.05), int(wy / 0.05))
            if cell not in seen:
                seen.add(cell)
                deduped.append((wx, wy))

        with self.lock:
            self.robot_points = new_robot_pts
            self.world_points = deduped

    def align_shelf_target(self, target_x, target_y=0.0, shelf_id="SHELF", search_radius=0.75):
        """
        Verifies if physical LiDAR points exist near the App's target coordinates.
        Refines target coordinates in 2D space while preserving original coordinates when unclustered.
        """
        with self.lock:
            pts = list(self.world_points)

        nearby_pts = []
        for wx, wy in pts:
            # Cluster points within search_radius of target (x, y)
            if math.hypot(wx - target_x, wy - target_y) <= search_radius:
                nearby_pts.append((wx, wy))

        if len(nearby_pts) >= 4:
            # Physical shelf detected by LiDAR in real-time
            avg_x = sum(p[0] for p in nearby_pts) / len(nearby_pts)
            avg_y = sum(p[1] for p in nearby_pts) / len(nearby_pts)
            
            result = {
                "shelf_id": shelf_id,
                "x": round(avg_x, 2),
                "y": round(avg_y, 2),
                "original_x": target_x,
                "original_y": target_y,
                "confirmed": True,
                "pts_count": len(nearby_pts)
            }
        else:
            # Target is still beyond immediate LiDAR cluster or unobstructed
            result = {
                "shelf_id": shelf_id,
                "x": target_x,
                "y": target_y,
                "original_x": target_x,
                "original_y": target_y,
                "confirmed": False,
                "pts_count": len(nearby_pts)
            }

        with self.lock:
            self.aligned_shelves[shelf_id] = result

        return result

    def get_snapshot(self):
        """Returns thread-safe copy of points and shelf status for Web Visualizer"""
        with self.lock:
            return {
                "world_points": list(self.world_points),
                "robot_points": list(self.robot_points),
                "aligned_shelves": dict(self.aligned_shelves)
            }

    def save_map_image(self, file_path="map.png", cart_pose=None, waypoints=None, active_idx=0):
        """Renders 2D Map image to disk using Matplotlib"""
        if not HAS_MATPLOTLIB:
            return
        now = time.time()
        if now - self.last_map_save_time < 0.5:
            return  # Rate limit map render to 2 FPS max

        self.last_map_save_time = now

        with self.lock:
            pts = list(self.world_points)

        if not pts and not cart_pose:
            return

        plt.figure(figsize=(7, 7), dpi=100)
        plt.style.use('dark_background')
        ax = plt.gca()
        ax.set_facecolor('#0d1117')

        # 1. Plot LiDAR points (walls, obstacles, shelves)
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.scatter(xs, ys, s=3, c='#00ffcc', alpha=0.7, label='LiDAR Scans')

        # 2. Plot Cart Pose
        cx = cart_pose.get("x", 0.0) if cart_pose else 0.0
        cy = cart_pose.get("y", 0.0) if cart_pose else 0.0
        ctheta = cart_pose.get("theta", 0.0) if cart_pose else 0.0

        ax.scatter([cx], [cy], s=120, c='#38ef7d', marker='o', edgecolors='white', label='CartMate (Robot)')
        
        # Draw heading direction vector
        arrow_len = 0.4
        dx = arrow_len * math.cos(math.radians(ctheta))
        dy = arrow_len * math.sin(math.radians(ctheta))
        ax.arrow(cx, cy, dx, dy, head_width=0.15, head_length=0.1, fc='#38ef7d', ec='#38ef7d')

        # 3. Plot Waypoints & Shelves
        if waypoints:
            for i, wp in enumerate(waypoints):
                wx = wp.get("target_x", wp.get("x", 0.0))
                wy = wp.get("target_y", wp.get("y", 0.0))
                shelf_id = wp.get("shelf_id", f"WP_{i+1}")
                is_active = (i == active_idx)

                color = '#ff3366' if is_active else '#ffbb00'
                marker = 's' if is_active else '^'
                size = 140 if is_active else 90

                ax.scatter([wx], [wy], s=size, c=color, marker=marker, edgecolors='white')
                ax.text(wx + 0.1, wy + 0.1, f"{shelf_id}", color=color, fontsize=10, weight='bold')

                if is_active:
                    # Draw trajectory path line from Cart to active target
                    ax.plot([cx, wx], [cy, wy], '--', color='#ff3366', alpha=0.8, linewidth=1.5, label='Active Path')

        # Dynamic bounding box: Ensure all shelves and cart are visible
        all_xs = [cx - 2.0, cx + 2.0]
        all_ys = [cy - 2.0, cy + 2.0]
        if waypoints:
            for wp in waypoints:
                all_xs.append(wp.get("target_x", wp.get("x", 0.0)))
                all_ys.append(wp.get("target_y", wp.get("y", 0.0)))

        min_x, max_x = min(all_xs) - 1.0, max(all_xs) + 1.0
        min_y, max_y = min(all_ys) - 1.0, max(all_ys) + 1.0

        ax.set_title("CartMate Real-Time 2D LiDAR Map", fontsize=12, color='#ffffff', pad=12)
        ax.set_xlabel("X Coordinate (Meters)", color='#8b949e')
        ax.set_ylabel("Y Coordinate (Meters)", color='#8b949e')
        ax.grid(True, color='#21262d', linestyle='--', linewidth=0.5)
        ax.set_xlim(min_x, max_x)
        ax.set_ylim(min_y, max_y)
        ax.legend(loc='upper right', facecolor='#161b22', edgecolor='#30363d', fontsize=8)

        plt.tight_layout()
        plt.savefig(file_path, bbox_inches='tight')
        plt.close()
