# ABC4201 - Dual Constant-Current LED Driver

**Manufacturer:** ACME Semiconductor (Fictional)
**Datasheet:** example-fictional-component.pdf
**Extracted:** 2026-01-04

> **DISCLAIMER:** This is a fictional example for demonstration purposes only. This component does not exist. Use this as a template reference for the expected output format when extracting real datasheets.

---

## 1. Circuit Design Information

**Component Family:** ABC4201

**Full Part Name:** ABC4201 Dual 150mA Constant-Current LED Driver with PWM Dimming

**Function:** Dual-channel constant-current LED driver with independent PWM dimming control for each channel. Regulates up to 150mA per channel with ±3% accuracy using external resistors.

### Pinout

| Pin | Name | Type | Active | Voltage | Description |
|-----|------|------|--------|---------|-------------|
| 1 | VIN | Power | - | 6-40V | Supply voltage input |
| 2 | PWM1 | Input | HIGH | 3.3V/5V | PWM dimming control for channel 1 (TTL/CMOS compatible) |
| 3 | RSET1 | Analog | - | - | Current setting resistor connection for channel 1 |
| 4 | GND | Power | - | 0V | Ground reference |
| 5 | RSET2 | Analog | - | - | Current setting resistor connection for channel 2 |
| 6 | PWM2 | Input | HIGH | 3.3V/5V | PWM dimming control for channel 2 (TTL/CMOS compatible) |
| 7 | OUT2 | Output | - | VIN | Constant-current output for LED channel 2 |
| 8 | OUT1 | Output | - | VIN | Constant-current output for LED channel 1 |

### Power Requirements

- **Supply voltage:** 6.0V to 40V (typical: 12V)
- **Supply current:** 2.5mA typical when both channels active (40µA quiescent when PWM LOW)
- **Logic HIGH threshold:** >2.0V (PWM inputs)
- **Logic LOW threshold:** <0.8V (PWM inputs)
- **Output current:** 10mA to 150mA per channel (set by external resistor)

### Package

**Package:** SOIC (8-pin, 5.0mm × 4.0mm)

---

## 2. Microcontroller Code Information

### Communication Interface

**Type:** GPIO Control

- **PWM1 (Pin 2):** PWM dimming control for LED channel 1 (active HIGH)
- **PWM2 (Pin 6):** PWM dimming control for LED channel 2 (active HIGH)
- **RSET1 (Pin 3):** Connect current-setting resistor to GND (ILED = 120mV / RSET)
- **RSET2 (Pin 5):** Connect current-setting resistor to GND (ILED = 120mV / RSET)

### Initialization Sequence

1. Connect VIN (pin 1) to supply voltage (6V to 40V) and GND (pin 4) to ground
2. Connect RSET resistors from pins 3 and 5 to GND to set desired LED current using formula: **ILED = 120mV / RSET**
   - Example: RSET = 800Ω gives 150mA, RSET = 1.2kΩ gives 100mA, RSET = 2.4kΩ gives 50mA
3. Connect LED strings to OUT1 (pin 8) and OUT2 (pin 7), with LED cathodes to ground
4. Wait for VIN to stabilize (no specific delay required)
5. Set PWM inputs (pins 2, 6) HIGH to enable outputs, or LOW to disable

### Operating Modes

- **Normal Mode (PWM HIGH):** Output actively regulates constant current through LED string. Current determined by RSET resistor value.

- **PWM Dimming Mode:** Apply PWM signal (100Hz to 20kHz recommended) to PWM inputs. LED brightness is proportional to PWM duty cycle. Output turns on after ~15µs when PWM goes HIGH, turns off after ~8µs when PWM goes LOW.

- **Shutdown Mode (PWM LOW):** Output enters high-impedance state. Quiescent current <50µA per channel. Apply HIGH to re-enable.

- **Thermal Protection:** If junction temperature exceeds 165°C, both outputs automatically disable. Device resumes when temperature drops below 145°C (automatic restart).

**Note:** PWM frequencies between 200Hz-2kHz recommended for best LED lifetime. Higher frequencies (>5kHz) reduce perceived flicker.

---

**End of Datasheet Extraction**

> **REMINDER:** This is a fictional component created for demonstration purposes. When extracting real datasheets, always verify critical information (pinouts, electrical characteristics, timing) with the original manufacturer's datasheet. This example demonstrates the focused, goal-oriented format optimized for circuit design and microcontroller code development.
