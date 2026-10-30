#!/usr/bin/env python3
"""
CartMate Interactive Keyboard Teleoperation & Motor Test Script
Allows manual driving and testing of the cart using keyboard keys.
"""

import os
import sys

# Ensure project root is in sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import tty
import termios
import time
from hardware.arduino_bridge import ArduinoBridge

def get_char():
    """Reads a single keypress without requiring the Enter key."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else None
    bridge = ArduinoBridge(port=port, baudrate=115200)

    if not bridge.connect():
        print(f"❌ Failed to connect on {port}. Please verify your USB connection and port permissions.")
        return

    print("\n" + "=" * 55)
    print("      CARTMATE INTERACTIVE KEYBOARD MOTOR TEST")
    print("=" * 55)
    print(" Control Keys (Press directly, NO Enter needed):")
    print("   [W] : Move Forward       (Both motors forward)")
    print("   [S] : Move Backward      (Both motors reverse)")
    print("   [A] : Turn Left          (Right faster, Left slower)")
    print("   [D] : Turn Right         (Left faster, Right slower)")
    print("   [X] / [Space] : Stop Motors")
    print("-------------------------------------------------------")
    print(" Individual Motor Diagnosis:")
    print("   [1] : Test Left Motor Forward   (1.5s pulse)")
    print("   [2] : Test Right Motor Forward  (1.5s pulse)")
    print("   [3] : Test Left Motor Reverse   (1.5s pulse)")
    print("   [4] : Test Right Motor Reverse  (1.5s pulse)")
    print("-------------------------------------------------------")
    print("   [Q] : Quit test script")
    print("=" * 55)

    try:
        while True:
            key = get_char().lower()

            if key == 'w':
                res = bridge.send_command("MOVE_FORWARD")
                print(f"\r➡️ [MOVE FORWARD] -> Arduino: {res}           \n", end="", flush=True)
            elif key == 's':
                res = bridge.send_command("MOVE_BACKWARD")
                print(f"\r⬅️ [MOVE BACKWARD] -> Arduino: {res}          \n", end="", flush=True)
            elif key == 'a':
                res = bridge.send_command("TURN_LEFT")
                print(f"\r🔄 [TURN LEFT] -> Arduino: {res}              \n", end="", flush=True)
            elif key == 'd':
                res = bridge.send_command("TURN_RIGHT")
                print(f"\r🔄 [TURN RIGHT] -> Arduino: {res}             \n", end="", flush=True)
            elif key in ('x', ' '):
                res = bridge.send_command("EMERGENCY_STOP")
                print(f"\r🛑 [STOPPED] -> Arduino: {res}                \n", end="", flush=True)
            elif key == '1':
                print("\n⚙️ Testing LEFT Motor Forward for 1.5s...", flush=True)
                res = bridge.send_command("TEST_LEFT")
                print(f"Response: {res}", flush=True)
            elif key == '2':
                print("\n⚙️ Testing RIGHT Motor Forward for 1.5s...", flush=True)
                res = bridge.send_command("TEST_RIGHT")
                print(f"Response: {res}", flush=True)
            elif key == '3':
                print("\n⚙️ Testing LEFT Motor Reverse for 1.5s...", flush=True)
                res = bridge.send_command("3")
                print(f"Response: {res}", flush=True)
            elif key == '4':
                print("\n⚙️ Testing RIGHT Motor Reverse for 1.5s...", flush=True)
                res = bridge.send_command("4")
                print(f"Response: {res}", flush=True)
            elif key == 'q':
                print("\nExiting and stopping motors...", flush=True)
                bridge.send_command("EMERGENCY_STOP")
                break
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        bridge.close()
        print("Disconnected cleanly.")

if __name__ == "__main__":
    main()
