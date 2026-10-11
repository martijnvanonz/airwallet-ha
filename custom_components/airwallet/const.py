"""Constants for the Airwallet integration."""

from datetime import timedelta

DOMAIN = "airwallet"

CONF_PHONE = "phone"
CONF_PIN = "pin"
CONF_LOCATION_ID = "location_id"
CONF_REFRESH_TOKEN = "refresh_token"

SCAN_INTERVAL = timedelta(seconds=60)

EVENT_FINISHED = "airwallet_machine_finished"
EVENT_STARTED = "airwallet_machine_started"

STATE_AVAILABLE = "available"
STATE_IN_USE = "in_use"
STATE_MINE = "mine"
STATE_MAINTENANCE = "maintenance"
