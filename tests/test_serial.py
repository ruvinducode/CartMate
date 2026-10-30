#!/usr/bin/env python3
import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import time
from hardware.arduino_bridge import ArduinoBridge

def test():
    arduino = ArduinoBridge(port=None, baudrate=115200)
    if not arduino.connect():
        print("❌ Could not connect to Arduino.")
        sys.exit(1)

    print("\nSelect command to send to Arduino:")
    print("1. MOVE_FORWARD (1 sec)")
    print("2. MOVE_BACKWARD (1 sec)")
    print("3. TURN_LEFT (1 sec)")
    print("4. TURN_RIGHT (1 sec)")
    print("5. TEST_LEFT (Only Left motor forward 1 sec)")
    print("6. TEST_RIGHT (Only Right motor forward 1 sec)")
    print("7. EMERGENCY_STOP")
    
    cmd = sys.argv[1] if len(sys.argv) > 1 else "MOVE_FORWARD"
    print(f"\nSending {cmd}...")
    res = arduino.send_command(cmd)
    print(f"Response: {res}")
    time.sleep(1.0)
    print("Sending EMERGENCY_STOP...")
    arduino.send_command("EMERGENCY_STOP")
    arduino.close()
    print("Done!")

if __name__ == "__main__":
    test()
