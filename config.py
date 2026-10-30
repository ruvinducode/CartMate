"""
CartMate System Configuration Module
Centralized parameters for physical robot geometry, serial protocols,
safety thresholds, and sensor configurations.
"""

import os

# ==========================================
# 1. HARDWARE & SERIAL CONFIGURATION (Ruvindu)
# ==========================================
# USB Serial Port connecting Raspberry Pi 5 to Arduino Uno
SERIAL_PORT = os.getenv("CARTMATE_SERIAL_PORT", "/dev/ttyACM0")
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT_SEC = 1.0

# ==========================================
# 2. PHYSICAL ROBOT GEOMETRY (Cart Dynamics)
# ==========================================
# All linear measurements in METERS
WHEEL_RADIUS = 0.065       # 6.5 cm wheel radius (Verify with physical cart)
TRACK_WIDTH = 0.380        # 38.0 cm distance between left and right wheels
ENCODER_TPR = 1920         # Ticks Per Revolution (Encoder CPR * Gearbox Ratio)

# Speed limits for physical safety
MAX_LINEAR_VELOCITY = 0.8   # Maximum target linear speed (m/s)
MAX_ANGULAR_VELOCITY = 1.5  # Maximum target rotation speed (rad/s)

# ==========================================
# 3. SAFETY THRESHOLDS
# ==========================================
ULTRASONIC_STOP_DIST_CM = 20.0   # Emergency stop if obstacle closer than 20cm
ULTRASONIC_SLOW_DIST_CM = 50.0   # Slow down threshold
COMMAND_TIMEOUT_SEC = 0.5        # Stop motors if no new command received within 500ms

# ==========================================
# 4. MQTT & BACKEND COMMUNICATION
# ==========================================
MQTT_BROKER_HOST = os.getenv("MQTT_HOST", "10.104.67.54")
MQTT_BROKER_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_CLIENT_ID = "cartmate_pi5_core"

# Topics
TOPIC_NAVIGATION_TARGET = os.getenv("MQTT_TOPIC_TARGET", "cartmate/navigation/target")
TOPIC_TASK_ASSIGN = "cartmate/cart_01/task/assign"
TOPIC_TELEMETRY = "cartmate/cart_01/telemetry"
TOPIC_EMERGENCY = "cartmate/cart_01/emergency"

# ==========================================
# 5. I2C SENSOR CONFIGURATION
# ==========================================
IMU_I2C_BUS = 1
IMU_I2C_ADDRESS = 0x68    # Standard address for MPU6050 (0x28 for BNO055)