# IntelliDwell Sprinkler Controller for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![Release](https://img.shields.io/github/v/release/TannerNelson16/ha-intellidwell)](https://github.com/TannerNelson16/ha-intellidwell/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Official Home Assistant custom integration for the **[IntelliDwell Smart Sprinkler Controller](https://www.intellidwell.net)**.

Control your irrigation zones, monitor run-time countdowns, configure rain delays, and manage watering schedules directly within Home Assistant with 100% local communication.

---

## Features

- 💧 **10 Zone Switches**: Instant manual on/off control for all 10 solenoid valves.
- ⏱️ **Timer Sensors & Quick Timers**:
  - Countdown sensor for each zone showing remaining watering time.
  - Quick-start services (`intellidwell.start_timer`, `intellidwell.cancel_timer`) to run zones for a specified number of minutes.
- 🌧️ **Rain Delay**: Set rain delay suspensions (0 to 5 days) via a native Number entity.
- 📅 **Lovelace Scheduler Card**: Includes the `intellidwell-scheduler-card` frontend card for managing on-device recurring watering schedules.
- 🔒 **100% Local Polling**: Talks directly to the controller on your local Wi-Fi network via HTTP REST API (`pyintellidwell`). No cloud dependencies.

---

## Installation

### Method 1: HACS (Recommended)

1. Ensure [HACS (Home Assistant Community Store)](https://hacs.xyz/) is installed.
2. In Home Assistant, open **HACS** > **Integrations**.
3. Click the top-right three dots menu (⋮) and select **Custom repositories**.
4. In the dialog, enter:
   - **Repository:** `https://github.com/TannerNelson16/ha-intellidwell`
   - **Category:** `Integration`
5. Click **Add**, then find **IntelliDwell Sprinkler Controller** and click **Download**.
6. Restart Home Assistant.

### Method 2: Manual Installation

1. Download the latest release `.zip` from the [Releases](https://github.com/TannerNelson16/ha-intellidwell/releases) page.
2. Copy the `custom_components/intellidwell` folder into your Home Assistant `<config>/custom_components/` directory.
3. Restart Home Assistant.

---

## Configuration

1. In Home Assistant, navigate to **Settings** > **Devices & Services**.
2. Click **Add Integration** in the bottom right corner.
3. Search for **IntelliDwell Sprinkler Controller**.
4. Enter the device IP address (e.g. `192.168.1.150` or hostname `sprinklers.local`) and port (`80`).
5. Click **Submit**. All 10 zones and configuration entities will be automatically created.

---

## Entities Provided

| Entity Type | Identifier | Description |
|---|---|---|
| `switch` | `switch.zone_{1..10}_power` | Manual zone valve control |
| `sensor` | `sensor.zone_{1..10}_timer_remaining` | Active timer countdown in minutes |
| `number` | `number.rain_delay` | Active rain delay days (0–5) |

---

## Services

### `intellidwell.start_timer`
Start watering a zone with an automatic shut-off timer.

```yaml
action: intellidwell.start_timer
target:
  device_id: <intellidwell_device_id>
data:
  zone: 1
  minutes: 15
```

### `intellidwell.cancel_timer`
Immediately cancel an active zone timer and turn off the valve.

```yaml
action: intellidwell.cancel_timer
target:
  device_id: <intellidwell_device_id>
data:
  zone: 1
```

---

## Interactive Scheduler Card

This integration includes the built-in `intellidwell-scheduler-card`. To add it to your dashboard:

1. Edit your Lovelace dashboard.
2. Add a **Manual** card.
3. Enter:

```yaml
type: custom:intellidwell-scheduler-card
device_id: <YOUR_INTELLIDWELL_DEVICE_ID>
```

---

## Reporting Issues & Feedback

Encountered an issue or have a feature request? Please report it on our [GitHub Issue Tracker](https://github.com/TannerNelson16/ha-intellidwell/issues).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
