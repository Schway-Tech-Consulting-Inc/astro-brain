from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime, timedelta
from dateutil import tz
from skyfield.api import load, wgs84
from math import atan2, degrees

app = FastAPI(title="Astro Engine API (Skyfield)")

# Load timescale & ephemeris (Skyfield downloads DE421 automatically)
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
    "pluto": "pluto barycenter"
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
        except:
            raise ValueError("date must be YYYY-MM-DD")

    @field_validator("time")
    @classmethod
    def validate_time(cls, v):
        try:
            datetime.strptime(v, "%H:%M")
            return v
        except:
            raise ValueError("time must be HH:MM")

@app.get("/")
def health_check():
    return {"status": "ok"}

def to_utc(dt_local, tz_name):
    local_zone = tz.gettz(tz_name)
    if local_zone is None:
        raise ValueError(f"Unknown timezone: {tz_name}")
    return dt_local.replace(tzinfo=local_zone).astimezone(tz.UTC)

def ecliptic_longitude(body, t, observer):
    """Compute ecliptic longitude from observer location."""
    astrometric = observer.at(t).observe(body)
    eclip = astrometric.ecliptic_position()
    x, y, z = eclip.km
    lon = (degrees(atan2(y, x)) + 360) % 360
    return lon

def compute_asc_mc(t, lat, lon):
    """
    Approximate ASC and MC for MVP.

    For now:
    - MC ≈ local sidereal time (in degrees)
    - ASC ≈ MC + 90°
    This is a simplification; we can refine later.
    """
    lst_deg = t.gast * 15.0  # Greenwich apparent sidereal time → degrees
    mc = lst_deg % 360
    asc = (lst_deg + 90) % 360
    return asc, mc

@app.post("/chart")
def chart(req: ChartRequest):
    # Build datetime
    try:
        dt_local = datetime.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
    except:
        raise HTTPException(status_code=400, detail="Invalid date/time")

    # Convert to UTC
    try:
        dt_utc = to_utc(dt_local, req.timezone)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Skyfield times: now and one hour earlier (for retrograde check)
    t = ts.from_datetime(dt_utc)
    t_prev = ts.from_datetime(dt_utc - timedelta(hours=1))

    # Observer on Earth
    location = wgs84.latlon(req.lat, req.lon)
    observer = eph["earth"] + location

    # Compute planets + retrograde
    planets = {}
    for name, key in PLANET_KEYS.items():
        body = eph[key]

        # longitude now
        lon_now = ecliptic_longitude(body, t, observer)
        # longitude 1 hour earlier
        lon_prev = ecliptic_longitude(body, t_prev, observer)

        # compute delta in forward direction
        delta = (lon_now - lon_prev + 540) % 360 - 180  # range -180..+180
        retro = delta < 0  # going backwards in zodiac

        planets[name] = {
            "lon": lon_now,
            "retrograde": retro
        }

    # Compute ASC & MC
    asc, mc = compute_asc_mc(t, req.lat, req.lon)

    return {
        "engine": "skyfield_de421",
        "input": req.model_dump(),
        "chart": {
            "asc": asc,
            "mc": mc,
            "planets": planets,
            # Placeholders we will fill later with proper math or a library:
            "houses": None,
            "true_node": None
        }
    }
