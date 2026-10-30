#!/usr/bin/env python3
import time
import sys
import math
import json
from communication.mqtt_client import CartMateMQTTClient
from navigation.obstacle_detector import ObstacleDetector
from navigation.path_planner import PathPlanner
from navigation.lidar_mapper import LidarMapper
from navigation.odometry import LidarOdometryTracker
from monitoring.web_visualizer import WebVisualizer, is_navigation_cancelled, reset_navigation_cancel
from hardware.arduino_bridge import ArduinoBridge
from hardware.esp32_arm_bridge import ESP32ArmBridge
from integration.product_detection_service import ProductDetector

def main():
    print("==================================================")
    print("🛒 CartMate Full Autonomous Navigation Engine")
    print("==================================================")

    # 1. Arduino Motor Controller Bridge
    arduino = ArduinoBridge(port='/dev/ttyACM0', baudrate=115200)
    if not arduino.connect():
        print("⚠️ Running without Arduino Serial link (Simulation mode).")

    # 2. MQTT Client
    mqtt_node = CartMateMQTTClient()
    mqtt_node.start()

    # 3. RPLiDAR Obstacle Detector (20cm Wall & Obstacle Threshold)
    obstacle_detector = ObstacleDetector(port='/dev/ttyUSB0', safe_distance_m=0.20)
    if not obstacle_detector.connect():
        print("❌ RPLiDAR connection failed! Exiting...")
        mqtt_node.stop()
        sys.exit(1)

    # 4. 2D LiDAR Real-time Mapper & Shelf Alignment Engine
    lidar_mapper = LidarMapper(map_range_m=6.0)

    # 5. Remote Web Visualizer (Port 8080) for MacBook / Phone
    visualizer = WebVisualizer(host="0.0.0.0", port=8080)
    visualizer.start()

    # 6. Raspberry Pi Camera Product Detection Engine
    product_detector = ProductDetector(output_dir="detections")

    # 7. ESP32 Robotic Arm Controller Bridge (never probe /dev/ttyUSB0 or /dev/ttyACM0)
    esp32_arm = ESP32ArmBridge(port='/dev/ttyUSB1', baudrate=115200, mqtt_client=mqtt_node, exclude_ports=['/dev/ttyUSB0', '/dev/ttyACM0'])
    esp32_arm.connect()

    # 8. Path Planner & Real-Time LiDAR Motion Tracker
    cart_x = 0.0
    cart_y = 0.0
    cart_theta = 0.0
    path_planner = PathPlanner(current_x=cart_x, current_y=cart_y, current_theta=cart_theta)
    lidar_tracker = LidarOdometryTracker(initial_x=cart_x, initial_y=cart_y, initial_theta=cart_theta)

    print("\n🟢 CartMate System Ready! Waiting for Waypoints...")
    print("🌐 Open http://10.104.67.204:8080 in your Mac browser to view the 2D Live HUD!\n")

    current_waypoint_index = 0
    last_processed_order = None
    last_loop_time = time.time()

    # Closed-Loop Navigation & Command Execution State Variables
    obstacle_state = "IDLE"  # "IDLE", "STOPPED", "REVERSING", "AVOIDING"
    state_timer = 0.0
    avoid_cmd = "TURN_LEFT"
    command_in_progress = "IDLE"
    is_initial_forward = False
    initial_forward_accum = 0.0
    initial_forward_timeout = 0.0
    last_wp_idx = -1
    last_map_render_time = 0.0
    last_lidar_warn_time = 0.0
    # Frozen target coordinates (locked once REACHED — prevents arrow jitter after arrival)
    frozen_target_x = None
    frozen_target_y = None

    try:
        while True:
            now = time.time()
            dt = max(0.01, min(now - last_loop_time, 0.5))
            last_loop_time = now

            waypoints = mqtt_node.get_waypoints()

            # Read thread-safe complete 360° RPLiDAR scan
            scan = obstacle_detector.get_latest_scan()

            cart_pose = {"x": cart_x, "y": cart_y, "theta": cart_theta}

            # Update 2D LiDAR map points
            if scan:
                lidar_mapper.update_scan(scan, cart_pose)
            elif now - last_lidar_warn_time > 3.0:
                print("⚠️ [LiDAR] Waiting for 360° scan data from RPLiDAR...")
                last_lidar_warn_time = now

            is_blocked = False
            min_dist = 0.0
            if scan:
                is_blocked, min_dist = obstacle_detector.check_front_obstacle(scan)

            current_action = "IDLE"
            dist_to_target = 0.0
            angle_err = 0.0

            if is_navigation_cancelled():
                if waypoints or current_action != "CANCELLED":
                    print("⛔ [Cancel] Navigation cancelled by user! Clearing all waypoints & stopping Cart.")
                    arduino.send_command("EMERGENCY_STOP")
                    mqtt_node.clear_waypoints()
                    waypoints = []
                    current_waypoint_index = 0
                current_action = "CANCELLED"
                current_order_id = "CANCELLED"
                dist_to_target = 0.0
                angle_err = 0.0
            elif waypoints:
                raw_payload = mqtt_node.raw_payload
                current_order_id = raw_payload.get("order_id", "ORD_0001") if raw_payload else "ORD_0001"
                cart_id = raw_payload.get("cart_id", "CART_01") if raw_payload else "CART_01"

                if current_order_id != last_processed_order:
                    current_waypoint_index = 0
                    last_processed_order = current_order_id
                    reset_navigation_cancel()  # New order resets any previous cancel
                    obstacle_state = "IDLE"
                    is_initial_forward = True
                    initial_forward_accum = 0.0
                    initial_forward_timeout = now + 4.0
                    command_in_progress = "MOVE_FORWARD"
                    # Reset pose & mapping state for new order to prevent angle drift/map rotation
                    cart_x = 0.0
                    cart_y = 0.0
                    cart_theta = 0.0
                    lidar_tracker.reset(0.0, 0.0, 0.0)
                    path_planner.update_pose(0.0, 0.0, 0.0)
                    lidar_mapper.history.clear()
                    lidar_mapper.aligned_shelves.clear()
                    # Reset frozen target for fresh order
                    frozen_target_x = None
                    frozen_target_y = None
                    print(f"🚀 [NEW ORDER] Pose reset to (0.0m, 0.0m, 0.0°). Starting Initial Forward Launch...")

                if current_waypoint_index < len(waypoints):
                    if current_waypoint_index != last_wp_idx:
                        last_wp_idx = current_waypoint_index
                        obstacle_state = "IDLE"
                        is_initial_forward = True
                        initial_forward_accum = 0.0
                        initial_forward_timeout = now + 4.0
                        command_in_progress = "MOVE_FORWARD"
                        # Reset frozen target for next waypoint
                        frozen_target_x = None
                        frozen_target_y = None
                        print(f"🚀 [NEXT WAYPOINT] Starting Initial Forward Launch for waypoint {current_waypoint_index + 1}...")

                    target_wp = waypoints[current_waypoint_index]
                    target_x = target_wp['target_x']
                    target_y = target_wp['target_y']
                    shelf_id = target_wp['shelf_id']

                    # 🎯 Real-time Shelf Alignment using LiDAR Map
                    # NOTE: Freeze alignment once REACHED to prevent arrow jitter after cart stops
                    if command_in_progress == "REACHED" and frozen_target_x is not None:
                        # Already arrived — reuse locked coordinates, skip re-averaging
                        aligned_shelf = {"x": frozen_target_x, "y": frozen_target_y, "confirmed": True, "pts_count": 0}
                        eff_target_x = frozen_target_x
                        eff_target_y = frozen_target_y
                    else:
                        aligned_shelf = lidar_mapper.align_shelf_target(target_x, target_y, shelf_id=shelf_id)
                        eff_target_x = aligned_shelf["x"]
                        eff_target_y = aligned_shelf["y"]

                    # 🧭 Update Path Planner with real-time Cart Pose
                    path_planner.update_pose(cart_x, cart_y, cart_theta)
                    dist_to_target, angle_err = path_planner.calculate_heading_and_distance(eff_target_x, eff_target_y)

                    # =========================================================
                    # 🎯 Real-Time Closed-Loop Navigation & Shelf Recognition
                    # =========================================================
                    # Check if the front obstacle detected by LiDAR is actually the target shelf!
                    is_shelf = False
                    dist_obs_to_shelf = 9.99
                    if is_blocked:
                        is_shelf, _, dist_obs_to_shelf = path_planner.is_shelf_obstacle(
                            min_dist, eff_target_x, eff_target_y, arrival_threshold=0.85
                        )

                    # 1. Target Shelf Arrival Check:
                    # Cart reaches target coordinates (<= 0.25m) OR front obstacle is recognized as the target shelf!
                    if dist_to_target <= 0.25 or (is_blocked and is_shelf):
                        cmd = "REACHED"
                        obstacle_state = "IDLE"
                        is_initial_forward = False
                        command_in_progress = "REACHED"
                        # 🔒 Lock effective target coordinates to prevent post-arrival arrow jitter
                        frozen_target_x = eff_target_x
                        frozen_target_y = eff_target_y
                        arrival_reason = f"LiDAR identified target shelf obstacle at {min_dist:.2f}m" if (is_blocked and is_shelf) else f"Target coordinate reached ({dist_to_target:.2f}m)"
                        print(f"🎯 [SHELF ARRIVAL] {arrival_reason} -> Stopping at {shelf_id}!")

                    # 2. Midway Obstacle Detected (Roadblock along the aisle, NOT the shelf):
                    elif is_blocked and not is_shelf:
                        is_initial_forward = False
                        if obstacle_state == "IDLE":
                            obstacle_state = "STOPPED"
                            state_timer = now + 0.35  # Brief halt
                            cmd = "EMERGENCY_STOP"
                            command_in_progress = cmd
                            print(f"🚨 [MIDWAY OBSTACLE at {min_dist:.2f}m] Blockage on path to {shelf_id} ({dist_to_target:.2f}m remaining). Halting Cart!")
                        elif obstacle_state == "STOPPED":
                            if now < state_timer:
                                cmd = "EMERGENCY_STOP"
                            else:
                                obstacle_state = "REVERSING"
                                state_timer = now + 1.0  # Reverse 1.0s to gain safe clearance
                                cmd = "MOVE_BACKWARD"
                                command_in_progress = cmd
                                print(f"⬅️ [OBSTACLE RECOVERY] Reversing to clear midway obstacle...")
                        elif obstacle_state == "REVERSING":
                            if now < state_timer and min_dist < 0.35:
                                cmd = "MOVE_BACKWARD"
                            else:
                                # Reversing complete: Check LiDAR side clearances
                                sectors = obstacle_detector.get_sector_clearances(scan) if scan else {}
                                left_clear = sectors.get("left", 0.0)
                                right_clear = sectors.get("right", 0.0)
                                avoid_cmd = "TURN_LEFT" if left_clear >= right_clear else "TURN_RIGHT"
                                obstacle_state = "AVOIDING"
                                state_timer = now + 0.9  # Turn towards open clearance
                                cmd = avoid_cmd
                                command_in_progress = cmd
                                print(f"🔄 [OBSTACLE RECOVERY] Clearance (L:{left_clear:.2f}m, R:{right_clear:.2f}m) -> Steering {avoid_cmd} to bypass...")
                        elif obstacle_state == "AVOIDING":
                            if now < state_timer:
                                cmd = avoid_cmd
                            else:
                                obstacle_state = "IDLE"
                                cmd, dist_to_target, angle_err = path_planner.generate_steering_command(eff_target_x, eff_target_y)
                                command_in_progress = cmd

                    # 3. Initial Forward Launch (Order Start / Waypoint Start):
                    elif is_initial_forward:
                        cmd = "MOVE_FORWARD"
                        command_in_progress = "MOVE_FORWARD"
                        # Check if cart physically launched into the corridor (accumulated forward displacement >= 0.25m or timeout)
                        if initial_forward_accum >= 0.25 or now >= initial_forward_timeout:
                            is_initial_forward = False
                            print(f"🚀 [INITIAL LAUNCH COMPLETE] Cart moved forward into corridor! Transitioning to Real-Time Guidance.")

                    # 4. Closed-Loop Real-Time Steering Commands:
                    else:
                        # If a turning maneuver is in progress, hold the turn until aligned
                        if command_in_progress in ("TURN_LEFT", "TURN_RIGHT"):
                            if abs(angle_err) <= 8.0:
                                # Turn completed and aligned! Resume forward
                                cmd = "MOVE_FORWARD"
                                command_in_progress = "MOVE_FORWARD"
                                print(f"✅ [TURN COMPLETED] Cart aligned (Error: {angle_err:.1f}°). Resuming MOVE_FORWARD!")
                            else:
                                cmd = command_in_progress
                        else:
                            # Cart is moving forward: check if heading has drifted significantly (> 18°)
                            if abs(angle_err) > 18.0:
                                turn_cmd = "TURN_LEFT" if angle_err > 0 else "TURN_RIGHT"
                                cmd = turn_cmd
                                command_in_progress = turn_cmd
                                print(f"🔄 [HEADING DRIFT] Heading error {angle_err:.1f}°. Commanding {turn_cmd} until aligned.")
                            else:
                                cmd = "MOVE_FORWARD"
                                command_in_progress = "MOVE_FORWARD"

                    current_action = cmd

                    # Real-time status print
                    confirm_tag = " [LiDAR Confirmed!]" if aligned_shelf.get("confirmed") else ""
                    scan_pts_info = f"{len(scan)} pts" if scan else "0 pts (waiting)"
                    obs_tag = f" [Blocked: {min_dist:.2f}m {'(Shelf)' if is_shelf else '(Midway)'}]" if is_blocked else " [Path Clear]"
                    print(f"📍 Goal [{current_waypoint_index + 1}/{len(waypoints)}] -> {shelf_id}{confirm_tag} | Target: ({eff_target_x:.2f}m, {eff_target_y:.2f}m)")
                    print(f"   Cart: ({cart_x:.2f}m, {cart_y:.2f}m, {cart_theta:.1f}°) | Dist: {dist_to_target:.2f}m | Angle Err: {angle_err:.1f}° | Action: 🚀 [{cmd}]{obs_tag} | 📡 LiDAR: {scan_pts_info}")

                    # Send command to Arduino
                    ack = arduino.send_command(cmd)
                    if ack:
                        print(f"   📥 [Arduino Response]: {ack}")

                    # Physical motion tracking directly from LiDAR (no fake increments!)
                    is_actively_moving = (cmd in ("MOVE_FORWARD", "MOVE_BACKWARD", "TURN_LEFT", "TURN_RIGHT"))
                    delta_moved, is_moving, pose = lidar_tracker.update_from_scan(
                        scan, commanded_action=cmd, dt=dt, is_executing=is_actively_moving
                    )
                    cart_x = pose["x"]
                    cart_y = pose["y"]
                    cart_theta = pose["theta"]
                    if is_initial_forward:
                        initial_forward_accum += abs(delta_moved)

                    path_planner.update_pose(cart_x, cart_y, cart_theta)

                    if cmd == "REACHED":
                        section_num = target_wp.get('section', 1)
                        target_items = target_wp.get('items', [])
                        print(f"✅ [REACHED GOAL] Arrived at Shelf: {shelf_id} (Section {section_num})!")
                        ack = arduino.send_command("REACHED")
                        if ack:
                            print(f"   📥 [Arduino Response]: {ack}")

                        # 📸 1. Update Live Web HUD status to Product Inspection
                        visualizer.update_telemetry(
                            order_id=current_order_id,
                            cart_id=cart_id,
                            cart_pose={"x": cart_x, "y": cart_y, "theta": cart_theta},
                            lidar_points=snapshot["world_points"] if 'snapshot' in locals() and snapshot else [],
                            waypoints=waypoints if waypoints else [],
                            active_waypoint_index=current_waypoint_index,
                            current_action=f"CAMERA_DETECTING_PRODUCT ({shelf_id} - Sec {section_num})",
                            distance_to_target=0.0,
                            angle_error=0.0,
                            is_blocked=False,
                            min_obstacle_dist=min_dist
                        )

                        # 📸 2. Trigger Raspberry Pi Camera Product & QR Detection
                        det_summary = product_detector.inspect_shelf_and_section(
                            shelf_id=shelf_id,
                            section=section_num,
                            target_items=target_items,
                            duration_sec=2.5
                        )

                        # 🦾 3. When OpenCV / Camera verifies product, signal ESP32 to PICK!
                        arm_picked = False
                        if det_summary["target_matched"] or det_summary["detected_products"]:
                            # Determine matched product name
                            target_product = target_items[0] if target_items else "product"
                            if det_summary["detected_products"]:
                                target_product = det_summary["detected_products"][0]["class"]

                            # Update HUD visualizer display for active pick action
                            visualizer.update_telemetry(
                                order_id=current_order_id,
                                cart_id=cart_id,
                                cart_pose={"x": cart_x, "y": cart_y, "theta": cart_theta},
                                lidar_points=snapshot["world_points"] if 'snapshot' in locals() and snapshot else [],
                                waypoints=waypoints if waypoints else [],
                                active_waypoint_index=current_waypoint_index,
                                current_action=f"ROBOTIC_ARM_PICKING ({target_product})",
                                distance_to_target=0.0,
                                angle_error=0.0,
                                is_blocked=False,
                                min_obstacle_dist=min_dist
                            )

                            # Send PICK signal to ESP32 Robotic Arm Controller
                            arm_res = esp32_arm.send_pick_command(
                                product_name=target_product,
                                shelf_id=shelf_id,
                                section=section_num
                            )
                            arm_picked = arm_res.get("success", False)
                        else:
                            print(f"⚠️ [Product Verification] Target product not confirmed on {shelf_id}. Skipping Arm Pick.")

                        # 📡 4. Publish Verification Status to Mobile App via MQTT
                        if mqtt_node and hasattr(mqtt_node, "client") and mqtt_node.client:
                            try:
                                status_topic = f"cartmate/cart/{cart_id}/status"
                                status_payload = json.dumps({
                                    "order_id": current_order_id,
                                    "cart_id": cart_id,
                                    "state": "picked" if (det_summary["target_matched"] or arm_picked) else "picking",
                                    "shelf_id": shelf_id,
                                    "section": section_num,
                                    "items": target_items,
                                    "arm_status": "picked" if arm_picked else "skipped",
                                    "detected": det_summary["detected_products"],
                                    "qr_verified": det_summary["verified_qr_codes"],
                                    "timestamp": time.time()
                                })
                                mqtt_node.client.publish(status_topic, status_payload)
                                print(f"📡 [MQTT Status Published] -> {status_topic} (State: {'picked' if arm_picked else 'picking'})")
                            except Exception as e:
                                print(f"⚠️ Error publishing MQTT status: {e}")

                        current_waypoint_index += 1
                else:
                    current_action = "ALL_GOALS_REACHED"
            else:
                current_order_id = "WAITING_FOR_APP"
                cart_id = "CART_01"
                current_action = "WAITING_FOR_WAYPOINTS"

            # Update Web Visualizer Telemetry continuously
            snapshot = lidar_mapper.get_snapshot()
            visualizer.update_telemetry(
                order_id=current_order_id,
                cart_id=cart_id,
                cart_pose={"x": cart_x, "y": cart_y, "theta": cart_theta},
                lidar_points=snapshot["world_points"],
                waypoints=waypoints if waypoints else [],
                active_waypoint_index=current_waypoint_index,
                current_action=current_action,
                distance_to_target=dist_to_target,
                angle_error=angle_err,
                is_blocked=is_blocked,
                min_obstacle_dist=min_dist
            )

            # Save Hi-Res Map Image (rate-limited to every 2 seconds to avoid CPU stall)
            if now - last_map_render_time >= 2.0:
                lidar_mapper.save_map_image(
                    file_path="map.png",
                    cart_pose={"x": cart_x, "y": cart_y, "theta": cart_theta},
                    waypoints=waypoints if waypoints else [],
                    active_idx=current_waypoint_index
                )
                last_map_render_time = now

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n🛑 Shutting down Engine...")
        arduino.send_command("EMERGENCY_STOP")
        arduino.close()
        obstacle_detector.stop()
        mqtt_node.stop()
        visualizer.stop()
        product_detector.close()
        esp32_arm.close()

if __name__ == "__main__":
    main()