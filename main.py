from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime, timedelta
from dateutil import tz
from skyfield.api import load, wgs84
from math import atan2, degrees

app = FastAPI(title="Astro Engine API (Skyfield)")

# Load timescale & ephemeris (Skyfield downloads DE421 automatically and caches it)
ts = load.timescale()
eph = load('de421.bsp')

PLANET_KEYS = {
    "sun": "sun",
    "moon": "moon",
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
    "pluto": "pluto barycenter",
}


class ChartRequest(BaseModel):
    date: str
    time: str
    timezone: str
    lat: float
    lon: float

    @field_validator("date")
    @classmethod
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except Exception:
            raise ValueError("date must be YYYY-MM-DD")

    @field_validator("time")
    @classmethod
    def validate_time(cls, v):
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except Exception:
            raise ValueError("time must be HH:MM (24h)")


@app.get("/")
def health_check():
    return {"status": "ok"}


def to_utc(dt_local: datetime, tz_name: str) -> datetime:
    local_zone = tz.gettz(tz_name)
    if local_zone is None:
        raise ValueError(f"Unknown timezone: {tz_name}")
    return dt_local.replace(tzinfo=local_zone).astimezone(tz.UTC)


def ecliptic_longitude(body, t, observer) -> float:
    """Compute ecliptic longitude (0–360) from given observer."""
    astrometric = observer.at(t).observe(body)
    eclip = astrometric.ecliptic_position()
    x, y, z = eclip.km
    lon = (degrees(atan2(y, x)) + 360.0) % 360.0
    return lon


def compute_asc_mc(t, lat_deg: float, lon_deg: float):
    """
    Approximate ASC and MC for MVP.
    - MC ≈ local sidereal time (in degrees)
    - ASC ≈ MC + 90°
    We can refine later.
    """
    lst_deg = t.gast * 15.0  # Greenwich apparent sidereal time in degrees
    mc = lst_deg % 360.0
    asc = (lst_deg + 90.0) % 360.0
    return asc, mc


@app.post("/chart")
def chart(req: ChartRequest):
    # 1) Build local datetime
    try:
        dt_local = datetime.strptime(
            f"{req.date} {req.time}", "%Y-%m-%d %H:%M"
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    # 2) Convert to UTC
    try:
        dt_utc = to_utc(dt_local, req.timezone)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3) Build Skyfield times: now and one hour earlier (for retrograde check)
    t = ts.from_datetime(dt_utc)
    t_prev = ts.from_datetime(dt_utc - timedelta(hours=1))

    # 4) Observer on Earth
    location = wgs84.latlon(req.lat, req.lon)
    observer = eph["earth"] + location

    # 5) Planets: longitude + retrograde
    planets = {}
    for name, key in PLANET_KEYS.items():
        body = eph[key]

        lon_now = ecliptic_longitude(body, t, observer)
        lon_prev = ecliptic_longitude(body, t_prev, observer)

        # Change in longitude (normalized to -180..+180)
        delta = (lon_now - lon_prev + 540.0) % 360.0 - 180.0
        retrograde = delta < 0  # moving backwards through zodiac

        planets[name] = {
            "lon": lon_now,
            "retrograde": retrograde,
        }

    # 6) ASC & MC
    asc, mc = compute_asc_mc(t, req.lat, req.lon)

    # 7) Return data; houses and true_node are placeholders for future
    return {
        "engine": "skyfield_de421",
        "input": req.model_dump(),
        "chart": {
            "asc": asc,
            "mc": mc,
            "planets": planets,
            "houses": None,
            "true_node": None,
        },
    }
