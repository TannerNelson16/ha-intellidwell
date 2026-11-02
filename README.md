# IntelliDwell Sprinkler Controller for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/default)
[![Release](https://img.shields.io/github/v/release/TannerNelson16/ha-intellidwell)](https://github.com/TannerNelson16/ha-intellidwell/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Official Home Assistant custom integration for the **[IntelliDwell Smart Sprinkler Controller](https://www.intellidwell.net)**.

Control your irrigation zones, monitor run-time countdowns, configure rain delays, and manage watering schedules directly within Home Assistant with 100% local communication.

---

## Features

- 💧 **10 Zone Switches**: Instant manual on/off control for all 10 solenoid valves.
- ⏱️ **Timer & Status Sensors**:
  - `Active Zone` sensor reporting which zone is watering or "Idle".
  - `Watering Time Remaining` timestamp sensor for live countdown display in the Home Assistant UI.
- ⚡ **Quick Timers & Services**: Run zones for a custom duration (`start_timer`) or stop active runs (`cancel_timer`).
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
4. Enter the device IP address (e.g. `192.168.1.150` or hostname `sprinklers.local`).
5. Click **Submit**. All 10 zones and configuration entities will be automatically created.

---

## Entities Provided

| Entity Type | Entity ID Pattern | Description |
|---|---|---|
| `switch` | `switch.intellidwell_sprinkler_controller_zone_{1..10}` | Individual zone valve control |
| `sensor` | `sensor.intellidwell_sprinkler_controller_active_zone` | Currently active watering zone name (or `Idle`) |
| `sensor` | `sensor.intellidwell_sprinkler_controller_watering_time_remaining` | Timestamp when current watering ends (live countdown) |
| `number` | `number.intellidwell_sprinkler_controller_rain_delay` | Active rain delay days (0–5) |

> [!NOTE]
> If custom zone names are configured on the controller (e.g., "Front Lawn"), the default entity name will incorporate the zone label while preserving numerical ordering. Users can also rename entities in Home Assistant, and custom renames will be preserved.

---

## Services

IntelliDwell provides actions/services to manage watering runs and schedules. These services take parameters directly under `data:` (services do not require a `target: device_id`; if multiple controllers are present, you may optionally pass `config_entry_id`).

### Timer Services

#### `intellidwell.start_timer`
Start watering a zone with an automatic shut-off timer.

```yaml
action: intellidwell.start_timer
data:
  zone: 1
  duration_mins: 15
```

#### `intellidwell.cancel_timer`
Immediately cancel an active zone timer and turn off the valve.

```yaml
action: intellidwell.cancel_timer
data:
  zone: 1 # Optional: cancels active run for this zone, or any active zone if omitted
```

---

### Schedule Services

#### `intellidwell.add_schedule`
Add a recurring watering schedule rule for a zone.

```yaml
action: intellidwell.add_schedule
data:
  zone: 1
  days: ["Mon", "Wed", "Fri"]
  on_time: "06:00"
  duration_mins: 20 # Or specify off_time: "06:20"
```

#### `intellidwell.edit_schedule`
Modify an existing schedule rule for a zone.

```yaml
action: intellidwell.edit_schedule
data:
  zone: 1
  schedule_id: "sch_123456_7890"
  days: ["Tue", "Thu", "Sat"]
  on_time: "05:30"
  duration_mins: 25 # Or specify off_time: "05:55"
```

#### `intellidwell.delete_schedule`
Remove a scheduled watering rule from a zone.

```yaml
action: intellidwell.delete_schedule
data:
  zone: 1
  schedule_id: "sch_123456_7890"
```

#### `intellidwell.toggle_schedule_item`
Enable or disable an individual schedule rule without deleting it.

```yaml
action: intellidwell.toggle_schedule_item
data:
  zone: 1
  schedule_id: "sch_123456_7890"
  enabled: false
```

#### `intellidwell.toggle_zone_schedule`
Enable or disable scheduled watering master control for a zone.

```yaml
action: intellidwell.toggle_zone_schedule
data:
  zone: 1
  enabled: true
```

---

## Interactive Scheduler Card

The integration automatically serves and registers the frontend `intellidwell-scheduler-card`. The card discovers all configured sprinkler zones automatically without needing device IDs.

To add the card to your dashboard:

1. Edit your Lovelace dashboard and click **Add Card**.
2. Select **IntelliDwell Sprinkler Scheduler Card** from the card picker (or choose **Manual**).
3. Use the visual editor or enter the following YAML:

```yaml
type: custom:intellidwell-scheduler-card
title: Sprinkler Schedules # Optional
show_zone_filter: true # Optional
```

---

## Reporting Issues & Feedback

Encountered an issue or have a feature request? Please report it on our [GitHub Issue Tracker](https://github.com/TannerNelson16/ha-intellidwell/issues).

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
