"""Minimal Airwallet client.

Airwallet has no public API. The app uses Firebase:
- Auth: email/password, where email is "<E.164 phone>@airwallet.net" and the password is the 4-digit app PIN
  padded with leading zeros to 6 digits.
- Data: Firebase Realtime Database, read over the REST API with the Firebase ID token.

This module has no Home Assistant imports, so scripts/check_login.py can use it directly.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

API_KEY = "AIzaSyD5otTplwRaSVJr2PCkVooOOI6fIW7fvoc"  # public key, embedded in the iOS app
BUNDLE_ID = "Airwallet"
DB_URL = "https://airwallet-685ff.firebaseio.com"
SIGN_IN_URL = "https://www.googleapis.com/identitytoolkit/v3/relyingparty/verifyPassword"
REFRESH_URL = "https://securetoken.googleapis.com/v1/token"
EMAIL_DOMAIN = "airwallet.net"

HEADERS = {"x-ios-bundle-identifier": BUNDLE_ID}
TIMEOUT = aiohttp.ClientTimeout(total=20)

PUSH_CHARS = "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"


class AirwalletError(Exception):
    """Generic API error."""


class AirwalletAuthError(AirwalletError):
    """Login failed (wrong phone number or PIN)."""


def phone_to_email(phone: str) -> str:
    """Convert a phone number to the Firebase login email that the app uses."""
    digits = "".join(c for c in phone if c.isdigit())
    if phone.strip().startswith("00"):
        digits = digits[2:]
    elif digits.startswith("06") and len(digits) == 10:  # Dutch mobile without country code
        digits = "31" + digits[1:]
    return f"+{digits}@{EMAIL_DOMAIN}"


def pin_to_password(pin: str) -> str:
    """The app pads the 4-digit PIN with leading zeros to the 6-digit Firebase password (1234 -> 001234)."""
    pin = pin.strip()
    return pin.zfill(6) if pin.isdigit() else pin


def push_id_time(push_id: str) -> float | None:
    """Return the creation time (epoch seconds) encoded in a Firebase push ID."""
    if len(push_id) < 8:
        return None
    ms = 0
    for c in push_id[:8]:
        idx = PUSH_CHARS.find(c)
        if idx < 0:
            return None
        ms = ms * 64 + idx
    return ms / 1000


@dataclass
class Machine:
    """One washer or dryer."""

    id: str
    name: str
    product_type: str  # WASHER, DRYER, ...
    last_payment: int
    last_used: int  # "busy until": pay time + max duration, then the real end time when the box detects it
    maintenance: bool
    price: int | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict)

    def in_use(self, now: float | None = None) -> bool:
        return (now or time.time()) < self.last_used

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Machine:
        return cls(
            id=data["id"],
            name=data.get("name") or data["id"],
            product_type=(data.get("product_type") or "OTHER").upper(),
            last_payment=int(data.get("last_payment_timestamp") or 0),
            last_used=int(data.get("last_used") or 0),
            maintenance=bool(data.get("maintenance")),
            price=data.get("price"),
            raw=data,
        )


@dataclass
class Location:
    id: str
    name: str
    machines: dict[str, Machine]


class AirwalletClient:
    """Login, token refresh and database reads."""

    def __init__(self, session: aiohttp.ClientSession, phone: str, pin: str, refresh_token: str | None = None) -> None:
        self._session = session
        self._email = phone_to_email(phone)
        self._password = pin_to_password(pin)
        self.refresh_token = refresh_token
        self.uid: str | None = None
        self._id_token: str | None = None
        self._expires = 0.0

    async def login(self) -> None:
        async with self._session.post(
            SIGN_IN_URL,
            params={"key": API_KEY},
            headers=HEADERS,
            json={"email": self._email, "password": self._password, "returnSecureToken": True, "clientType": "CLIENT_TYPE_IOS"},
            timeout=TIMEOUT,
        ) as resp:
            data = await resp.json(content_type=None)
        if resp.status != 200:
            message = (data.get("error") or {}).get("message", "") if isinstance(data, dict) else ""
            if resp.status == 400 and any(m in message for m in ("INVALID", "EMAIL_NOT_FOUND", "USER_DISABLED")):
                raise AirwalletAuthError(message)
            raise AirwalletError(f"login failed: {resp.status} {message}")
        self._store(data["idToken"], data["refreshToken"], data["localId"], data["expiresIn"])

    async def _refresh(self) -> None:
        async with self._session.post(
            REFRESH_URL,
            params={"key": API_KEY},
            headers=HEADERS,
            json={"grantType": "refresh_token", "refreshToken": self.refresh_token},
            timeout=TIMEOUT,
        ) as resp:
            data = await resp.json(content_type=None)
        if resp.status != 200:
            raise AirwalletAuthError("refresh failed")
        self._store(data["id_token"], data["refresh_token"], data["user_id"], data["expires_in"])

    def _store(self, id_token: str, refresh_token: str, uid: str, expires_in: str) -> None:
        self._id_token = id_token
        self.refresh_token = refresh_token
        self.uid = uid
        self._expires = time.time() + int(expires_in) - 120

    async def _token(self) -> str:
        if self._id_token and time.time() < self._expires:
            return self._id_token
        if self.refresh_token:
            try:
                await self._refresh()
                return self._id_token  # type: ignore[return-value]
            except AirwalletAuthError:
                pass  # fall back to a full login with the PIN
        await self.login()
        return self._id_token  # type: ignore[return-value]

    async def _get(self, path: str, **params: str) -> Any:
        token = await self._token()
        async with self._session.get(f"{DB_URL}/{path}.json", params={"auth": token, **params}, timeout=TIMEOUT) as resp:
            data = await resp.json(content_type=None)
        if resp.status == 401:
            self._id_token = None
            raise AirwalletAuthError("database rejected the token")
        if resp.status != 200:
            raise AirwalletError(f"GET {path}: {resp.status} {data}")
        return data

    async def get_favorite_location_id(self) -> str | None:
        await self._token()
        fav = await self._get(f"users/{self.uid}/details/favorite_location")
        return fav.get("id") if isinstance(fav, dict) else None

    async def get_location(self, location_id: str) -> Location:
        data = await self._get(f"locations/{location_id}")
        if not isinstance(data, dict):
            raise AirwalletError(f"location {location_id} not found")
        machines = {k: Machine.from_dict({"id": k, **v}) for k, v in (data.get("devices") or {}).items()}
        return Location(id=location_id, name=data.get("name") or location_id, machines=machines)

    async def get_recent_orders(self, limit: int = 10) -> dict[str, dict[str, Any]]:
        await self._token()
        data = await self._get(f"users/{self.uid}/orders", orderBy='"$key"', limitToLast=str(limit))
        return data if isinstance(data, dict) else {}


def my_machine_ids(location: Location, orders: dict[str, dict[str, Any]], window: int = 600) -> set[str]:
    """Machines whose current run was paid by this user.

    An order is matched to a machine when the order time (from the push ID) is close to the machine's
    last payment time. This avoids marking a machine as "mine" after someone else started it.
    """
    mine = set()
    for order_id, order in orders.items():
        machine = location.machines.get(order.get("device_id") or "")
        created = push_id_time(order_id)
        if machine and created and abs(created - machine.last_payment) <= window:
            mine.add(machine.id)
    return mine
