"""Check the Airwallet login and print the machine status, outside Home Assistant.

Run in your own terminal (the PIN is asked without echo and is never printed):

    .venv/bin/python scripts/check_login.py
"""

import asyncio
import getpass
import importlib.util
import sys
import time
from datetime import datetime
from pathlib import Path

import aiohttp

API_PATH = Path(__file__).resolve().parent.parent / "custom_components" / "airwallet" / "api.py"
spec = importlib.util.spec_from_file_location("airwallet_api", API_PATH)
api = importlib.util.module_from_spec(spec)
sys.modules["airwallet_api"] = api
spec.loader.exec_module(api)


async def main() -> None:
    phone = input("Phone number (+31...): ").strip()
    pin = getpass.getpass("PIN: ").strip()
    async with aiohttp.ClientSession() as session:
        client = api.AirwalletClient(session, phone, pin)
        try:
            await client.login()
        except api.AirwalletAuthError:
            print("Login FAILED: wrong phone number or PIN.")
            return
        print("Login OK.")
        location_id = await client.get_favorite_location_id()
        print(f"Favorite laundry room: {location_id}")
        location = await client.get_location(location_id)
        mine = api.my_machine_ids(location, await client.get_recent_orders())
        now = time.time()
        print(f"\n{location.name}")
        for m in sorted(location.machines.values(), key=lambda m: m.name):
            if m.in_use(now):
                state = f"IN USE until {datetime.fromtimestamp(m.last_used):%H:%M}" + (" (mine)" if m.id in mine else "")
            else:
                state = "free"
            print(f"  {m.name:<16} {m.product_type:<7} {state}")


asyncio.run(main())
