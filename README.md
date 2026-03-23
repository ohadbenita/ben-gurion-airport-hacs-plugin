# Ben Gurion Airport for Home Assistant

HACS custom integration for Ben Gurion Airport arrivals and departures using the official [data.gov.il](https://data.gov.il/he/datasets/airport_authority/flydata) feed.

## Features

- HACS-ready custom integration
- Config flow from the Home Assistant UI
- Polls the official `datastore_search` API with the required `User-Agent`
- Creates arrivals and departures board sensors
- Exposes the next flight and the visible board rows as sensor attributes
- Lets you control refresh interval, board length, and whether completed flights stay on the board

## Entities

After setup, the integration creates:

- `sensor.<name>_departures_board`
- `sensor.<name>_arrivals_board`
- `sensor.<name>_last_update`
- Dynamic tracked-flight sensors created through the `ben_gurion_airport.track_flight` service

Board sensors use their state for the number of matching flights and expose:

- `delayed_count`
- `next_flight`
- `flights`

Each flight row includes the airline, flight code, city, country, terminal, gate, check-in zone, scheduled time, updated time, and both English and Hebrew status labels.

## Exposed sensors

### `sensor.<name>_departures_board`

- State: total number of departure flights currently returned by the feed
- Attributes:
  - `delayed_count`
  - `next_flight`
  - `flights`

### `sensor.<name>_arrivals_board`

- State: total number of arrival flights currently returned by the feed
- Attributes:
  - `delayed_count`
  - `next_flight`
  - `flights`

### `sensor.<name>_last_update`

- State: timestamp of the most recent successful refresh
- Attributes:
  - `refresh_minutes`
  - `board_limit`
  - `include_completed`

### Tracked-flight sensors

Tracked-flight sensors are created on demand for a specific flight code, direction, and date.

Create one from Home Assistant Developer Tools using:

```yaml
action: ben_gurion_airport.track_flight
data:
  flight_code: LY1027
  flight_date: "2026-03-24"
  direction: departure
  name: Newark flight
```

Remove it later with:

```yaml
action: ben_gurion_airport.untrack_flight
data:
  flight_code: LY1027
  flight_date: "2026-03-24"
  direction: departure
```

Each tracked-flight sensor:

- Represents one configured flight on one specific date
- Uses the current flight status as its state
- Updates its attributes whenever any tracked flight field changes upstream
- Stays in sync even after the flight changes to delayed, departed, or canceled
- Exposes a `change_token` attribute that changes whenever any flight field changes

Tracked-flight attributes include:

- `tracked_flight_code`
- `tracked_flight_date`
- `tracked_direction`
- `matched`
- `match_count`
- `change_token`
- `last_refresh`

When a match is found, the sensor also exposes the full flight payload, including:

- `flight_code`
- `flight_number`
- `airline_code`
- `airline_name`
- `direction`
- `airport_code`
- `city`
- `city_hebrew`
- `city_raw`
- `country`
- `country_hebrew`
- `scheduled_time`
- `updated_time`
- `terminal`
- `gate`
- `checkin_zone`
- `status`
- `status_hebrew`
- `is_delayed`

### Flight object structure

The `next_flight` attribute and each item inside `flights` expose:

- `flight_code`
- `flight_number`
- `airline_code`
- `airline_name`
- `direction`
- `airport_code`
- `city`
- `city_hebrew`
- `city_raw`
- `country`
- `country_hebrew`
- `scheduled_time`
- `updated_time`
- `terminal`
- `gate`
- `checkin_zone`
- `status`
- `status_hebrew`
- `is_delayed`

## Automation ideas

Because the integration exposes both a summary count and full board rows, it works well with Home Assistant automations, template sensors, and dashboards.

### 1. Notify when the next departure becomes delayed

```yaml
automation:
  - alias: "Ben Gurion: next departure delayed"
    trigger:
      - platform: state
        entity_id: sensor.ben_gurion_airport_departures_board
    condition:
      - condition: template
        value_template: >
          {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight') is mapping }}
      - condition: template
        value_template: >
          {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').is_delayed }}
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Departure delay"
          message: >
            {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').flight_code }}
            to
            {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').city }}
            is delayed.
```

### 2. Send a morning arrivals summary

```yaml
automation:
  - alias: "Ben Gurion: morning arrivals summary"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Ben Gurion arrivals"
          message: >
            There are {{ states('sensor.ben_gurion_airport_arrivals_board') }} arrivals on the board,
            including {{ state_attr('sensor.ben_gurion_airport_arrivals_board', 'delayed_count') }} delayed flights.
```

### 3. Create a template sensor for the next departure destination

```yaml
template:
  - sensor:
      - name: "Ben Gurion Next Departure City"
        state: >
          {% set flight = state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight') %}
          {{ flight.city if flight else 'Unknown' }}
```

### 4. Alert when no data has refreshed recently

```yaml
automation:
  - alias: "Ben Gurion: stale feed warning"
    trigger:
      - platform: template
        value_template: >
          {{
            (as_timestamp(now()) - as_timestamp(states('sensor.ben_gurion_airport_last_update')))
            > 1800
          }}
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Ben Gurion feed warning"
          message: "The airport data feed has not refreshed in the last 30 minutes."
```

### 5. Build a Lovelace markdown card from the first few flights

```yaml
type: markdown
content: >
  {% for flight in state_attr('sensor.ben_gurion_airport_departures_board', 'flights')[:5] %}
  - {{ flight.scheduled_time[11:16] }} | {{ flight.flight_code }} | {{ flight.city }} | {{ flight.status }}
  {% endfor %}
```

### 6. Track a specific departure and notify on any change

First create the tracked flight:

```yaml
action: ben_gurion_airport.track_flight
data:
  flight_code: LY1027
  flight_date: "2026-03-24"
  direction: departure
  name: Newark flight
```

Then trigger on the tracked entity whenever its data changes:

```yaml
automation:
  - alias: "Ben Gurion: tracked flight changed"
    trigger:
      - platform: state
        entity_id: sensor.newark_flight
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Tracked flight updated"
          message: >
            {{ state_attr('sensor.newark_flight', 'flight_code') }}
            is now {{ states('sensor.newark_flight') }}.
            Scheduled: {{ state_attr('sensor.newark_flight', 'scheduled_time') }}.
            Updated: {{ state_attr('sensor.newark_flight', 'updated_time') }}.
            Gate: {{ state_attr('sensor.newark_flight', 'gate') or 'TBD' }}.
```

### 7. Trigger only when any tracked-flight field changes

If you want a dedicated change token, use the `change_token` attribute:

```yaml
automation:
  - alias: "Ben Gurion: tracked flight change token"
    trigger:
      - platform: state
        entity_id: sensor.newark_flight
        attribute: change_token
    action:
      - service: notify.mobile_app_your_phone
        data:
          message: >
            {{ state_attr('sensor.newark_flight', 'flight_code') }}
            changed in the airport feed.
```

### Notes for automations

- The board sensor state is a count, not a flight code or status.
- The detailed flight data lives in the `next_flight` and `flights` attributes.
- Tracked-flight sensors are the best option when you want a dedicated entity for one specific flight on one specific date.
- If you disable completed flights, landed, departed, and canceled rows will be filtered out before they reach Home Assistant.
- The upstream dataset metadata says it updates every 15 minutes, even if you choose a shorter polling interval in Home Assistant.

## Installation

1. Add this repository as a custom repository in HACS.
2. Install the integration.
3. Restart Home Assistant.
4. Go to `Settings -> Devices & Services -> Add Integration`.
5. Search for `Ben Gurion Airport`.

## Data source

- Dataset: `flydata`
- Resource ID: `e83f763b-b7d7-479e-b172-ae981ddc6de5`
- API: `https://data.gov.il/api/3/action/datastore_search`

The official dataset metadata reports an update cadence of every 15 minutes. The integration can poll more frequently, but the upstream feed itself may not change faster than that.
