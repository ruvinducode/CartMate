/*
 * ============================================================================
 * CartMate Autonomous & Manual Motor Controller (Verified Polarity & Speed)
 * Board: Arduino Uno / Nano / Mega
 * Motor Driver: 2 x BTS7960 (LEN & REN tied to 5V)
 * Baud Rate: 115200 baud
 * ============================================================================
 * Hardware Wiring:
 *  - Both Drivers VCC, L_EN, R_EN  -> Arduino 5V
 *  - Both Drivers GND              -> Arduino GND
 *  - Left Driver L_PWM             -> Arduino Pin 5 (PWM)
 *  - Left Driver R_PWM             -> Arduino Pin 6 (PWM)
 *  - Right Driver L_PWM            -> Arduino Pin 3 (PWM)
 *  - Right Driver R_PWM            -> Arduino Pin 11 (PWM)
 *  - Left Driver M+/M-             -> Left Motor (+ / -)
 *  - Right Driver M+/M-            -> Right Motor (+ / -)
 * ============================================================================
 */

// ==================================================
// 1. PWM PIN DEFINITIONS (Only 4 PWM Pins Needed)
// ==================================================
// Left Motor Driver (Driver 1)
const int LEFT_L_PWM   = 5;   // Arduino PWM Pin (~5)
const int LEFT_R_PWM   = 6;   // Arduino PWM Pin (~6)

// Right Motor Driver (Driver 2)
const int RIGHT_L_PWM  = 3;   // Arduino PWM Pin (~3)
const int RIGHT_R_PWM  = 11;  // Arduino PWM Pin (~11)

// ==================================================
// 2. MOTOR POLARITY CONFIGURATION
// ==================================================
// මෝටර් දෙක Cart එකේ දෙපැත්තට මුහුණලා (opposite facing) සවි කර ඇති නිසා
// සහ ඔබ Driver දෙකේම M+/M- මෝටර් වලට කෙලින්ම දී ඇති නිසා:
// රෝද දෙකම එකම ඉදිරි දිශාවට (Forward) කැරකැවීමට Right Motor එක Invert කල යුතුය:
const bool INVERT_LEFT_MOTOR  = false;
const bool INVERT_RIGHT_MOTOR = true;  // Guarantees both wheels rotate forward together

// ==================================================
// 3. SPEED CONFIGURATION (PWM: 0 to 255)
// ==================================================
// Cart එක පාලනය කරගත හැකි සාමාන්‍ය හොඳ වේගයක් (Smooth & Controlled) ලබා දී ඇත:
const int BASE_SPEED        = 180;  // ඉදිරියට යන වේගය (160 - 200 අතර සුදුසුයි)
const int REVERSE_SPEED     = 160;  // පස්සට (Reverse) එන වේගය
const int TURN_FAST_SPEED   = 190;  // හැරෙන විට පිටත රෝදයේ වේගය
const int TURN_SLOW_SPEED   = 90;   // හැරෙන විට ඇතුළත රෝදයේ වේගය

// ==================================================
// 4. SAFETY WATCHDOG
// ==================================================
unsigned long lastCommandTime = 0;
const unsigned long SAFETY_TIMEOUT_MS = 1500; // තත්පර 1.5ක් සිග්නල් නැතිනම් ස්වයංක්‍රීයව නවතී

char serialBuffer[32];
byte bufferIdx = 0;
char currentDirection = 'S'; // 'F', 'B', 'L', 'R', 'S'

// ==================================================
// 5. LOW-LEVEL MOTOR DRIVER FUNCTIONS
// ==================================================
void driveLeftMotor(int speed) {
  speed = constrain(speed, -255, 255);
  if (INVERT_LEFT_MOTOR) speed = -speed;

  if (speed > 0) {
    analogWrite(LEFT_L_PWM, speed);
    analogWrite(LEFT_R_PWM, 0);
  } else if (speed < 0) {
    analogWrite(LEFT_L_PWM, 0);
    analogWrite(LEFT_R_PWM, -speed);
  } else {
    analogWrite(LEFT_L_PWM, 0);
    analogWrite(LEFT_R_PWM, 0);
  }
}

void driveRightMotor(int speed) {
  speed = constrain(speed, -255, 255);
  if (INVERT_RIGHT_MOTOR) speed = -speed;

  if (speed > 0) {
    analogWrite(RIGHT_L_PWM, speed);
    analogWrite(RIGHT_R_PWM, 0);
  } else if (speed < 0) {
    analogWrite(RIGHT_L_PWM, 0);
    analogWrite(RIGHT_R_PWM, -speed);
  } else {
    analogWrite(RIGHT_L_PWM, 0);
    analogWrite(RIGHT_R_PWM, 0);
  }
}

// MOSFETs ආරක්ෂා කරගැනීමට දිශාව මාරු වන විට 25ms පොඩි විරාමයක් ලබාදීම
void safeDirectionSwitch(char newDir) {
  if (currentDirection != newDir && currentDirection != 'S') {
    driveLeftMotor(0);
    driveRightMotor(0);
    delay(25);
  }
  currentDirection = newDir;
}

// ==================================================
// 6. HIGH-LEVEL MOTION FUNCTIONS
// ==================================================
void stopMotors() {
  driveLeftMotor(0);
  driveRightMotor(0);
  currentDirection = 'S';
}

void moveForward() {
  safeDirectionSwitch('F');
  driveLeftMotor(BASE_SPEED);
  driveRightMotor(BASE_SPEED);
}

void moveBackward() {
  safeDirectionSwitch('B');
  driveLeftMotor(-REVERSE_SPEED);
  driveRightMotor(-REVERSE_SPEED);
}

// වමට හැරීම: දකුණු රෝදය වේගයෙන් (190), වම් රෝදය හෙමින් (90) -> Cart එක වමට කැරකේ
void turnLeft() {
  safeDirectionSwitch('L');
  driveLeftMotor(TURN_SLOW_SPEED);
  driveRightMotor(TURN_FAST_SPEED);
}

// දකුණට හැරීම: වම් රෝදය වේගයෙන් (190), දකුණු රෝදය හෙමින් (90) -> Cart එක දකුණට කැරකේ
void turnRight() {
  safeDirectionSwitch('R');
  driveLeftMotor(TURN_FAST_SPEED);
  driveRightMotor(TURN_SLOW_SPEED);
}

// ==================================================
// 7. DIAGNOSTIC & MANUAL TESTING MENU
// ==================================================
void printHelpMenu() {
  Serial.println(F("\n=================================================="));
  Serial.println(F("       CARTMATE MOTOR CONTROLLER READY            "));
  Serial.println(F("=================================================="));
  Serial.println(F("  [w / F]  -> MOVE FORWARD  (රෝද දෙකම ඉදිරියට)"));
  Serial.println(F("  [s / B]  -> MOVE BACKWARD (රෝද දෙකම පස්සට)"));
  Serial.println(F("  [a / L]  -> TURN LEFT     (වමට හැරීම)"));
  Serial.println(F("  [d / R]  -> TURN RIGHT    (දකුණට හැරීම)"));
  Serial.println(F("  [x / S]  -> STOP          (නැවතීම)"));
  Serial.println(F("--------------------------------------------------"));
  Serial.println(F("  [1]      -> TEST LEFT MOTOR FORWARD (1.5s)"));
  Serial.println(F("  [2]      -> TEST RIGHT MOTOR FORWARD (1.5s)"));
  Serial.println(F("  [3]      -> TEST LEFT MOTOR REVERSE (1.5s)"));
  Serial.println(F("  [4]      -> TEST RIGHT MOTOR REVERSE (1.5s)"));
  Serial.println(F("=================================================="));
}

// ==================================================
// 8. COMMAND PROCESSOR
// ==================================================
void processCommand(const char* cmd) {
  if (strcmp(cmd, "MOVE_FORWARD") == 0 || strcmp(cmd, "w") == 0) {
    moveForward();
    Serial.println(F("ACK: EXECUTING_MOVE_FORWARD"));
  }
  else if (strcmp(cmd, "MOVE_BACKWARD") == 0 || strcmp(cmd, "s") == 0) {
    moveBackward();
    Serial.println(F("ACK: EXECUTING_MOVE_BACKWARD"));
  }
  else if (strcmp(cmd, "TURN_LEFT") == 0 || strcmp(cmd, "a") == 0) {
    turnLeft();
    Serial.println(F("ACK: EXECUTING_TURN_LEFT"));
  }
  else if (strcmp(cmd, "TURN_RIGHT") == 0 || strcmp(cmd, "d") == 0) {
    turnRight();
    Serial.println(F("ACK: EXECUTING_TURN_RIGHT"));
  }
  else if (strcmp(cmd, "EMERGENCY_STOP") == 0 || strcmp(cmd, "REACHED") == 0 || strcmp(cmd, "x") == 0) {
    stopMotors();
    Serial.println(F("ACK: EXECUTING_STOP"));
  }
  else if (strcmp(cmd, "TEST_LEFT") == 0 || strcmp(cmd, "1") == 0) {
    stopMotors();
    Serial.println(F("ACK: TESTING_LEFT_MOTOR_FORWARD"));
    driveLeftMotor(BASE_SPEED);
    delay(1500);
    stopMotors();
    Serial.println(F("ACK: LEFT_MOTOR_TEST_COMPLETED"));
  }
  else if (strcmp(cmd, "TEST_RIGHT") == 0 || strcmp(cmd, "2") == 0) {
    stopMotors();
    Serial.println(F("ACK: TESTING_RIGHT_MOTOR_FORWARD"));
    driveRightMotor(BASE_SPEED);
    delay(1500);
    stopMotors();
    Serial.println(F("ACK: RIGHT_MOTOR_TEST_COMPLETED"));
  }
  else if (strcmp(cmd, "3") == 0) {
    stopMotors();
    Serial.println(F("ACK: TESTING_LEFT_MOTOR_REVERSE"));
    driveLeftMotor(-REVERSE_SPEED);
    delay(1500);
    stopMotors();
    Serial.println(F("ACK: LEFT_MOTOR_TEST_COMPLETED"));
  }
  else if (strcmp(cmd, "4") == 0) {
    stopMotors();
    Serial.println(F("ACK: TESTING_RIGHT_MOTOR_REVERSE"));
    driveRightMotor(-REVERSE_SPEED);
    delay(1500);
    stopMotors();
    Serial.println(F("ACK: RIGHT_MOTOR_TEST_COMPLETED"));
  }
  else if (strcmp(cmd, "h") == 0 || strcmp(cmd, "?") == 0 || strcmp(cmd, "HELP") == 0) {
    printHelpMenu();
  }
}

// ==================================================
// 9. SETUP & MAIN LOOP
// ==================================================
void setup() {
  Serial.begin(115200);

  pinMode(LEFT_L_PWM, OUTPUT);
  pinMode(LEFT_R_PWM, OUTPUT);
  pinMode(RIGHT_L_PWM, OUTPUT);
  pinMode(RIGHT_R_PWM, OUTPUT);

  stopMotors();
  Serial.println(F("ARDUINO_MOTOR_CONTROLLER_READY"));
  printHelpMenu();
  lastCommandTime = millis();
}

void loop() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\n' || c == '\r') {
      if (bufferIdx > 0) {
        serialBuffer[bufferIdx] = '\0';
        lastCommandTime = millis();
        processCommand(serialBuffer);
        bufferIdx = 0;
      }
    } else {
      if (bufferIdx < sizeof(serialBuffer) - 1) {
        serialBuffer[bufferIdx++] = c;
      }
    }
  }

  // Safety Watchdog: තත්පර 1.5කට වඩා Signal නැතිනම් Motors නවත්වයි
  if (millis() - lastCommandTime > SAFETY_TIMEOUT_MS) {
    if (currentDirection != 'S') {
      stopMotors();
    }
  }
}
