#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

const int RED_PIN = 9;
const int YELLOW_PIN = 10;
const int GREEN_PIN = 11;

const int TRIG_PIN = 2;
const int ECHO_PIN = 3;

const int BUZZER_PIN = 6;
const int POT_PIN = A0;

int stateFromDistance(int distanceCm) {
  if (distanceCm <= 5) return 2;
  if (distanceCm <= 15) return 1;
  return 0;
}

void setOutputs(int state, int brightness) {
  analogWrite(RED_PIN, 0);
  analogWrite(YELLOW_PIN, 0);
  analogWrite(GREEN_PIN, 0);
  noTone(BUZZER_PIN);

  if (state == 2) {
    analogWrite(RED_PIN, brightness);
    tone(BUZZER_PIN, 1200);
    return;
  }

  if (state == 1) {
    analogWrite(YELLOW_PIN, brightness);
    return;
  }

  analogWrite(GREEN_PIN, brightness);
}

void setup() {
  pinMode(RED_PIN, OUTPUT);
  pinMode(YELLOW_PIN, OUTPUT);
  pinMode(GREEN_PIN, OUTPUT);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(BUZZER_PIN, OUTPUT);

  Serial.begin(9600);

  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("System startet");
  delay(1200);
  lcd.clear();
}

void loop() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Timeout avoids long blocking if sensor has no echo.
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  int distance = (duration > 0) ? int(duration * 0.034 / 2.0) : 400;

  int potValue = analogRead(POT_PIN);
  int brightness = map(potValue, 0, 1023, 0, 255);

  int state = stateFromDistance(distance);
  setOutputs(state, brightness);

  lcd.setCursor(0, 0);
  lcd.print("Abstand: ");
  lcd.print(distance);
  lcd.print(" cm   ");

  lcd.setCursor(0, 1);
  if (state == 2) {
    lcd.print("BUBU          ");
  } else if (state == 1) {
    lcd.print("ACHTUNG       ");
  } else {
    lcd.print("ALLES OK      ");
  }

  // Machine-readable format expected by server: distance,state
  Serial.print(distance);
  Serial.print(",");
  Serial.println(state);

  delay(120);
}
