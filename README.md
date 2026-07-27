# Ben Gurion Airport for Home Assistant

Track Ben Gurion Airport arrivals, departures, and specific flights in Home Assistant.

This custom integration uses the official Israel Open Data `flydata` feed from
[data.gov.il](https://data.gov.il/he/datasets/airport_authority/flydata).

## Features

- Live arrivals and departures board sensors
- Config flow and options flow in the Home Assistant UI
- Search action for finding flights by flight code, airline, city, airport code, or route text
- Dynamic tracked-flight sensors for individual flights
- Configurable refresh interval, board size, and completed-flight filtering
- Resilient fetches with retries for transient data.gov.il gateway failures
- HACS-ready repository layout and release versioning

## Install

### HACS

1. Open HACS in Home Assistant.
2. Open the menu in the top-right corner and choose **Custom repositories**.
3. Add this repository URL.
4. Select **Integration** as the category.
5. Download the integration.
6. Restart Home Assistant.
7. Go to **Settings > Devices & services > Add integration**.
8. Search for **Ben Gurion Airport**.

### Manual

Copy `custom_components/ben_gurion_airport` into your Home Assistant
`custom_components` directory, then restart Home Assistant.

## Configure

During setup, choose:

- **Name**: device and entity display name.
- **Refresh interval**: how often Home Assistant asks for airport data.
- **Flights to expose per board**: number of rows stored in each board sensor's `flights` attribute.
- **Include completed flights**: whether departed, landed, and canceled rows remain visible.

You can change these later from **Settings > Devices & services > Ben Gurion Airport > Configure**.

The upstream dataset reports an update cadence of about 15 minutes. Polling more often can make Home Assistant notice changes quickly, but it cannot make the source feed update faster.

## Entities

After setup, the integration creates these sensors:

- `sensor.<name>_departures_board`
- `sensor.<name>_arrivals_board`
- `sensor.<name>_last_update`

Tracked-flight sensors are created only after you track a specific flight.

### Board Sensors

The arrivals and departures board sensors use their state for the number of matching flights. Detailed flight data is exposed as attributes:

- `delayed_count`
- `next_flight`
- `flights`

Each flight object can include:

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

### Last Update Sensor

`sensor.<name>_last_update` reports the timestamp of the most recent successful refresh.

Attributes:

- `refresh_minutes`
- `board_limit`
- `include_completed`

## Search Flights

Use the **Search flights** action when you want to find the exact flight to track.

1. Go to **Developer tools > Actions**.
2. Select **Ben Gurion Airport: Search flights**.
3. Enter a search query.
4. Run the action and inspect the response.

Example:

```yaml
action: ben_gurion_airport.search_flights
data:
  query: W6 2098 from TLV to KRK
  direction: departure
  include_completed: true
  limit: 10
```

The action accepts natural route text. Words such as `from` and `to` are ignored, and local airport aliases such as `TLV`, `Ben Gurion`, and `Tel Aviv` are treated as the local airport context.

The response includes a `flights` list. Each result includes the values needed by the tracking action:

```yaml
flight_code: W62098
flight_date: "2026-07-29"
direction: departure
scheduled_time: "2026-07-29T11:05:00"
status: ON TIME
airport_code: KRK
city: KRAKOW
```

## Track a Flight

Use **Track flight** after you find the flight you want.

```yaml
action: ben_gurion_airport.track_flight
data:
  flight_code: W62098
  flight_date: "2026-07-29"
  direction: departure
  name: W6 2098 to Krakow
```

The integration creates a tracked-flight sensor for that specific flight code, date, and direction.

To stop tracking it:

```yaml
action: ben_gurion_airport.untrack_flight
data:
  flight_code: W62098
  flight_date: "2026-07-29"
  direction: departure
```

### Tracked-Flight Sensor State

Each tracked-flight sensor:

- Represents one configured flight on one specific date
- Uses the current flight status as its state
- Updates attributes whenever the upstream feed changes
- Remains useful after delays, departure, landing, or cancellation
- Exposes a `change_token` attribute that changes whenever the matched flight payload changes

Tracked-flight attributes include:

- `tracked_flight_code`
- `tracked_flight_date`
- `tracked_direction`
- `matched`
- `match_count`
- `change_token`
- `last_refresh`

When a match is found, the full flight object is also exposed as sensor attributes.

## Automations

Home Assistant uses **actions** in automations and scripts. The examples below use the modern plural automation keys: `triggers`, `conditions`, and `actions`.

### Notify When a Tracked Flight Changes

```yaml
alias: "Ben Gurion: tracked flight changed"
triggers:
  - trigger: state
    entity_id: sensor.w6_2098_to_krakow
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Tracked flight updated"
      message: >
        {{ state_attr('sensor.w6_2098_to_krakow', 'flight_code') }}
        is now {{ states('sensor.w6_2098_to_krakow') }}.
        Scheduled: {{ state_attr('sensor.w6_2098_to_krakow', 'scheduled_time') }}.
        Updated: {{ state_attr('sensor.w6_2098_to_krakow', 'updated_time') }}.
        Gate: {{ state_attr('sensor.w6_2098_to_krakow', 'gate') or 'TBD' }}.
```

### Trigger Only When Any Flight Field Changes

```yaml
alias: "Ben Gurion: tracked flight payload changed"
triggers:
  - trigger: state
    entity_id: sensor.w6_2098_to_krakow
    attribute: change_token
actions:
  - action: notify.mobile_app_your_phone
    data:
      message: >
        {{ state_attr('sensor.w6_2098_to_krakow', 'flight_code') }}
        changed in the airport feed.
```

### Notify When the Next Departure Is Delayed

```yaml
alias: "Ben Gurion: next departure delayed"
triggers:
  - trigger: state
    entity_id: sensor.ben_gurion_airport_departures_board
conditions:
  - condition: template
    value_template: >
      {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight') is mapping }}
  - condition: template
    value_template: >
      {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').is_delayed }}
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Departure delay"
      message: >
        {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').flight_code }}
        to
        {{ state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight').city }}
        is delayed.
```

### Send a Morning Arrivals Summary

```yaml
alias: "Ben Gurion: morning arrivals summary"
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Ben Gurion arrivals"
      message: >
        There are {{ states('sensor.ben_gurion_airport_arrivals_board') }} arrivals on the board,
        including {{ state_attr('sensor.ben_gurion_airport_arrivals_board', 'delayed_count') }} delayed flights.
```

### Create a Template Sensor for the Next Departure City

```yaml
template:
  - sensor:
      - name: "Ben Gurion Next Departure City"
        state: >
          {% set flight = state_attr('sensor.ben_gurion_airport_departures_board', 'next_flight') %}
          {{ flight.city if flight else 'Unknown' }}
```

### Alert When the Feed Is Stale

```yaml
alias: "Ben Gurion: stale feed warning"
triggers:
  - trigger: template
    value_template: >
      {{
        (as_timestamp(now()) - as_timestamp(states('sensor.ben_gurion_airport_last_update')))
        > 1800
      }}
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Ben Gurion feed warning"
      message: "The airport data feed has not refreshed in the last 30 minutes."
```

### Dashboard Markdown Card

```yaml
type: markdown
content: >
  {% for flight in state_attr('sensor.ben_gurion_airport_departures_board', 'flights')[:5] %}
  - {{ flight.scheduled_time[11:16] }} | {{ flight.flight_code }} | {{ flight.city }} | {{ flight.status }}
  {% endfor %}
```

## Troubleshooting

### HACS Does Not Show the Latest Version

HACS can download releases when the repository has full GitHub releases. A tag alone is not enough for the best HACS update experience.

If a new release does not appear:

1. Confirm the release exists on GitHub and is not a draft or prerelease.
2. In HACS, open the repository menu and choose **Update information**.
3. If needed, open the repository and choose **Redownload** to select a specific version.
4. Restart Home Assistant after updating a custom integration.

HACS refreshes repository metadata separately from the files already downloaded into Home Assistant.

### Search Returns No Flights

Try a narrower query first:

```yaml
action: ben_gurion_airport.search_flights
data:
  query: W6 2098 KRK
  direction: departure
  include_completed: true
```

If a flight has already departed or landed, keep **Include completed flights** enabled.

### Board Sensor State Is Only a Number

That is expected. The board sensor state is the count. Detailed rows are in the `next_flight` and `flights` attributes.

### Gateway Errors From data.gov.il

The integration retries transient `429`, `502`, `503`, and `504` responses. If filtered API requests keep failing, it retries without API-side filters and applies filtering locally.

## Data Source

- Dataset: `flydata`
- Resource ID: `e83f763b-b7d7-479e-b172-ae981ddc6de5`
- API: `https://data.gov.il/api/3/action/datastore_search`

## Development

Useful local checks:

```bash
python -m compileall custom_components/ben_gurion_airport
git diff --check
```

For HACS-friendly publishing, create a full GitHub release for each version you want users to download from HACS.
