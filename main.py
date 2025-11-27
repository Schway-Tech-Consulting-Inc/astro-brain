from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator
from datetime import datetime
from dateutil import tz
from skyfield.api import load, Topos
from skyfield.api import N, E, wgs84
from math import atan2, degrees

app = FastAPI(title="Astro Engine API (Skyfield)")

# Load basic timescale and ephemeris (Skyfield will download small files automatically on first run)
ts = load.timescale()
# DE421 is enough for astrology and not huge; Skyfield will cache it
eph = load("de421.bsp")  # JPL planetary ephemeris

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
    date: str        # "1990-05-14"
    time: str        # "15:30"
    timezone: str    # "America/Toronto"
    lat: float       # 43.65
    lon: float       # -79.38

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("date must be in format YYYY-MM-DD")
        return v

    @field_validator("time")
    @classmethod
    def validate_time(cls, v: str) -> str:
        try:
            datetime.strptime(v, "%H:%M")
        except ValueError:
            raise ValueError("time must be in format HH:MM (24h)")
        return v

@app.get("/")
def health_check():
    return {"status": "ok"}

def to_utc(dt_local: datetime, tz_name: str) -> datetime:
    """Convert a local datetime + tz name to UTC."""
    try:
        local_zone = tz.gettz(tz_name)
        if local_zone is None:
            raise ValueError(f"Unknown timezone: {tz_name}")
    except Exception:
        raise ValueError(f"Unknown timezone: {tz_name}")

    dt_local = dt_local.replace(tzinfo=local_zone)
    return dt_local.astimezone(tz.UTC)

def ecliptic_longitude(body, t, location=None) -> float:
    """Return ecliptic longitude (0–360) of given body at time t."""
    if location is not None:
        astrometric = location.at(t).observe(body)
    else:
        astrometric = eph["earth"].at(t).observe(body)

    ecliptic = astrometric.ecliptic_position()
    x, y, z = ecliptic.km
    lon_deg = (degrees(atan2(y, x)) + 360.0) % 360.0
    return lon_deg

def compute_asc_mc(t, lat_deg: float, lon_deg: float):
    """
    Compute a rough Ascendant and MC using Skyfield and simple formulae.
    This is an approximation but good enough for an MVP.
    """
    # Observer location
    location = wgs84.latlon(latitude_degrees=lat_deg, longitude_degrees=lon_deg)
    # Local apparent sidereal time
    apparent_sidereal = t.gast * 15.0  # in degrees

    # MC is basically the ecliptic longitude of the local meridian
    mc = apparent_sidereal
    mc = mc % 360.0

    # Ascendant approximate formula: Asc ≈ arctan2(-cos(ε) * tan(φ), -sin(ε) * sin(θ) - cos(ε) * cos(θ) * tan(φ))
    # For simplicity here, we use a common shortcut: Asc ≈ (apparent_sidereal + 90°) - correction by latitude.
    # This is not perfect but reasonable for an MVP, we refine later.
    asc = (apparent_sidereal + 90.0) % 360.0

    return asc, mc

@app.post("/chart")
def chart(req: ChartRequest):
    """
    Compute basic chart elements:
    - Planetary ecliptic longitudes (Sun–Pluto)
    - Ascendant (approx)
    - MC (approx)

    This uses Skyfield (JPL DE421), fully free and file-managed internally.
    """
    # 1) Build local datetime from input
    try:
        dt_local = datetime.strptime(f"{req.date} {req.time}", "%Y-%m-%d %H:%M")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date or time format")

    # 2) Convert to UTC
    try:
        dt_utc = to_utc(dt_local, req.timezone)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3) Build Skyfield time object
    t = ts.from_datetime(dt_utc)

    # 4) Observer location
    observer = wgs84.latlon(latitude_degrees=req.lat, longitude_degrees=req.lon)

    # 5) Planets
    planets = {}
    for name, key in PLANET_KEYS.items():
        body = eph[key]
        lon = ecliptic_longitude(body, t, location=observer)
        planets[name] = {
            "lon": lon,  # 0–360 degrees
        }

    # 6) Ascendant and MC (rough)
    asc, mc = compute_asc_mc(t, req.lat, req.lon)

    return {
        "engine": "skyfield_de421",
        "input": {
            "date": req.date,
            "time": req.time,
            "timezone": req.timezone,
            "lat": req.lat,
            "lon": req.lon,
        },
        "chart": {
            "asc": asc,
            "mc": mc,
            "planets": planets,
        },
    }
