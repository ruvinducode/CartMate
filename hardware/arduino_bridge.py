import serial
import time
import glob
import os

def find_arduino_port():
    """Auto-detect connected Arduino port (/dev/ttyACM* or /dev/ttyUSB*)."""
    by_id = glob.glob('/dev/serial/by-id/*')
    for p in by_id:
        if any(name in p for name in ["FIREPHX", "Arduino", "USB_SER", "USB"]):
            return os.path.realpath(p)

    acm_ports = sorted(glob.glob('/dev/ttyACM*'))
    if acm_ports:
        return acm_ports[0]

    usb_ports = sorted(glob.glob('/dev/ttyUSB*'))
    if usb_ports:
        return usb_ports[0]

    return '/dev/ttyACM0'

class ArduinoBridge:
    def __init__(self, port=None, baudrate=115200):
        if port is None or not os.path.exists(port):
            self.port = find_arduino_port()
        else:
            self.port = port
        self.baudrate = baudrate
        self.serial_conn = None

    def connect(self):
        try:
            # Re-verify port exists before connecting
            if not os.path.exists(self.port):
                self.port = find_arduino_port()

            print(f"🔌 Connecting to Arduino on {self.port}...")
            self.serial_conn = serial.Serial(self.port, self.baudrate, timeout=1)
            time.sleep(2)  # Arduino Reset delay
            if self.serial_conn.is_open:
                self.serial_conn.reset_input_buffer()
            print("✅ Arduino Connected Successfully!")
            return True
        except Exception as e:
            print(f"❌ Arduino Connection Failed: {e}")
            return False

    @property
    def serial(self):
        return self.serial_conn

    def send_command(self, command):
        if self.serial_conn and self.serial_conn.is_open:
            try:
                # Flush any old unread messages from buffer
                self.serial_conn.reset_input_buffer()

                # Command එක Arduino එකට යැවීම
                full_cmd = f"{command}\n"
                self.serial_conn.write(full_cmd.encode('utf-8'))
                
                # Arduino එකෙන් එන Response එක Read කිරීම
                start_wait = time.time()
                while self.serial_conn.in_waiting == 0 and (time.time() - start_wait) < 0.2:
                    time.sleep(0.01)
                
                if self.serial_conn.in_waiting > 0:
                    response = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    return response
            except Exception as e:
                print(f"❌ Serial Write Error: {e}")
        return None
        
    def close(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.send_command("EMERGENCY_STOP")
            self.serial_conn.close()
            print("🔌 Arduino Connection Closed.")