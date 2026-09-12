"""Solar power production forecast for a rooftop PV system.

Fetches hourly weather data from Open-Meteo and estimates power output
for today and tomorrow.

System configuration (hardcoded for this installation):
  Location  : Uzhgorod, Ukraine  (48.621°N, 22.288°E)
  Peak power: 9 kW (two strings, ESE and SSE; modelled as one SE plane)
  Tilt      : 45°
  Azimuth   : -45° (south-east)
  Shading   : a building to the ESE shades the row until the sun passes
              azimuth ~112° (string 1) / ~126° (string 2)

Open-Meteo is a free, no-auth API — no credentials needed.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

import requests

# ---------------------------------------------------------------------------
# System constants
# ---------------------------------------------------------------------------

LATITUDE = 48.621025
LONGITUDE = 22.288229
TIMEZONE = "Europe/Kyiv"
# PEAK_KW, AZIMUTH and PERFORMANCE_RATIO were fitted 2026-09-12 against Home
# Assistant's uncurtailed PV hours (Aug 14 - Sep 11): the data pins down
# PEAK_KW * PERFORMANCE_RATIO ~= 7.7 kW at azimuth -45 (RMSE 0.24 kW vs 1.0 kW
# at azimuth 0). The array is actually two strings, ESE (~-60, 3.4 kW) and
# SSE (~-30, 4.4 kW); -45 is the single-plane approximation. Observed string
# peaks sum to 9.45 kW DC, so 9.0 kW is a lower bound on the nameplate size -
# if the real panel total is known, put it here and set PR = 7.7 / PEAK_KW.
PEAK_KW = 9.0
TILT = 45          # degrees from horizontal
AZIMUTH = -45      # 0 = south, negative = east (Open-Meteo convention)
PERFORMANCE_RATIO = 0.85   # accounts for inverter losses, wiring, soiling, etc.
# The Deye's "Max Solar Power" setting (number.*_pv_power in HA) caps PV input.
INVERTER_MAX_KW = 9.0

# Morning shading. The panels are one row in a built-up area; a building to
# the ESE shades them until the sun swings far enough south. Measured from HA
# 5-minute data on clear days (2026-09-02..09): string 1 (ESE, ~44 % of the
# array) clears when the sun's azimuth passes ~112 deg, string 2 (SSE) at
# ~126 deg. While shaded a string yields ~20 % of expected (diffuse light only).
# A pure azimuth rule is exact for Aug-Sep; it likely over-shades in summer
# (sun high enough to clear the roofline earlier) and under-shades in winter
# (sun barely above the horizon at these azimuths).
SHADE_CLEAR_AZ_PV1 = 112.0   # sun azimuth (deg from N, clockwise) at which string 1 clears
SHADE_CLEAR_AZ_PV2 = 126.0   # ... string 2
PV1_SHARE = 0.44             # string 1's share of PEAK_KW (3.4 of 7.8 kW effective)
SHADED_FRACTION = 0.20       # output of a shaded string relative to unshaded

# Temperature coefficient of power (typical c-Si panel: -0.4 %/°C)
TEMP_COEFF = -0.004
# Reference temperature at standard test conditions (STC)
STC_TEMP = 25.0
# Simplified cell-temperature rise above ambient (NOCT model)
NOCT_RISE = 25.0

API_URL = "https://api.open-meteo.com/v1/forecast"

# ---------------------------------------------------------------------------
# Sun position and shading
# ---------------------------------------------------------------------------

_TZ = ZoneInfo(TIMEZONE)


def sun_azimuth(dt_local: datetime) -> float:
    """Sun azimuth in degrees clockwise from north (NOAA approximation, ~0.5 deg)."""
    utc = dt_local.replace(tzinfo=_TZ).astimezone(timezone.utc)
    hrs = utc.hour + utc.minute / 60.0
    g = math.radians(360.0 / 365.0 * (utc.timetuple().tm_yday - 1 + (hrs - 12) / 24.0))
    eqt = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                    - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g)
            - 0.006758 * math.cos(2 * g) + 0.000907 * math.sin(2 * g)
            - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    ha = math.radians((hrs * 60 + eqt + 4 * LONGITUDE) / 4 - 180)
    lat = math.radians(LATITUDE)
    el = math.asin(math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha))
    az = math.acos((math.sin(decl) * math.cos(lat) - math.cos(decl) * math.sin(lat) * math.cos(ha))
                   / math.cos(el))
    return math.degrees(2 * math.pi - az if ha > 0 else az)


def shading_factor(slot_start: datetime) -> float:
    """Fraction of unshaded output for the hour starting at slot_start (local time).

    Sampled every 10 minutes so an edge inside the hour shades only part of it.
    """
    total = 0.0
    for m in range(5, 60, 10):
        az = sun_azimuth(slot_start + timedelta(minutes=m))
        pv1 = 1.0 if az >= SHADE_CLEAR_AZ_PV1 else SHADED_FRACTION
        pv2 = 1.0 if az >= SHADE_CLEAR_AZ_PV2 else SHADED_FRACTION
        total += PV1_SHARE * pv1 + (1.0 - PV1_SHARE) * pv2
    return total / 6


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class HourSlot:
    dt: datetime
    gti: float          # global tilted irradiance W/m²
    cloud: float        # cloud cover %
    temp: float         # ambient temperature °C
    sunshine: float     # sunshine duration this hour, seconds

    @property
    def power_kw(self) -> float:
        """Estimated AC power output in kW."""
        if self.gti <= 0:
            return 0.0
        cell_temp = self.temp + NOCT_RISE
        temp_correction = 1.0 + TEMP_COEFF * (cell_temp - STC_TEMP)
        dc_kw = self.gti / 1000.0 * PEAK_KW * PERFORMANCE_RATIO * temp_correction
        dc_kw *= shading_factor(self.dt)
        return round(min(dc_kw, INVERTER_MAX_KW), 3)

    @property
    def energy_kwh(self) -> float:
        """Energy produced in this 1-hour slot (kWh)."""
        return self.power_kw  # 1 h × kW = kWh


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------

def fetch_forecast() -> List[HourSlot]:
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "hourly": ",".join([
            "global_tilted_irradiance",
            "temperature_2m",
            "cloud_cover",
            "sunshine_duration",
        ]),
        "tilt": TILT,
        "azimuth": AZIMUTH,
        "forecast_days": 2,
        "timezone": TIMEZONE,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: Could not reach Open-Meteo API: {exc}", file=sys.stderr)
        sys.exit(1)

    raw = resp.json()
    hourly = raw["hourly"]

    slots: List[HourSlot] = []
    for i, ts in enumerate(hourly["time"]):
        slots.append(HourSlot(
            dt=datetime.fromisoformat(ts),
            gti=hourly["global_tilted_irradiance"][i] or 0.0,
            temp=hourly["temperature_2m"][i] or 0.0,
            cloud=hourly["cloud_cover"][i] or 0.0,
            sunshine=hourly["sunshine_duration"][i] or 0.0,
        ))
    return slots


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

BAR_MAX_WIDTH = 28   # characters for 8 kW (full bar)

def _bar(power_kw: float) -> str:
    filled = round(power_kw / PEAK_KW * BAR_MAX_WIDTH)
    return "#" * filled


def _fmt_duration(seconds: float) -> str:
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    return f"{h}h {m:02d}m"


def _print_day(day_label: str, slots: List[HourSlot]) -> None:
    separator = "-" * 78
    print(f"\n{day_label}")
    print(separator)
    print(f"  {'Hour':>5}  {'GTI':>7}  {'Cloud':>5}  {'Temp':>6}  {'Power':>8}  Chart (0-{PEAK_KW:.0f} kW)")
    print(separator)

    total_kwh = 0.0
    peak_power = 0.0
    peak_hour = ""
    total_sunshine = 0.0

    for s in slots:
        total_kwh += s.energy_kwh
        total_sunshine += s.sunshine
        if s.power_kw > peak_power:
            peak_power = s.power_kw
            peak_hour = s.dt.strftime("%H:%M")

        # Only print hours with any meaningful data or daylight context
        if s.gti > 0 or (6 <= s.dt.hour <= 20):
            bar = _bar(s.power_kw)
            print(
                f"  {s.dt.strftime('%H:%M'):>5}  "
                f"{s.gti:>7.0f}  "
                f"{s.cloud:>4.0f}%  "
                f"{s.temp:>5.1f}C   "
                f"{s.power_kw:>7.2f} kW  "
                f"{bar}"
            )

    print(separator)
    print(
        f"  Total: {total_kwh:.1f} kWh  |  "
        f"Peak: {peak_power:.2f} kW at {peak_hour}  |  "
        f"Sunshine: {_fmt_duration(total_sunshine)}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print(f"  Solar Power Forecast - Uzhgorod, Ukraine")
    print(f"  {PEAK_KW:.0f} kW south-facing array, tilt {TILT} deg  |  "
          f"Performance ratio: {PERFORMANCE_RATIO:.0%}  |  "
          f"Temp coeff: {TEMP_COEFF*100:.1f}%/degC")
    print("=" * 78)

    slots = fetch_forecast()

    today = date.today()
    tomorrow = date.fromordinal(today.toordinal() + 1)

    today_slots = [s for s in slots if s.dt.date() == today]
    tomorrow_slots = [s for s in slots if s.dt.date() == tomorrow]

    day_names = {today: today.strftime("TODAY - %A, %Y-%m-%d"),
                 tomorrow: tomorrow.strftime("TOMORROW - %A, %Y-%m-%d")}

    for day_date, day_slots in [(today, today_slots), (tomorrow, tomorrow_slots)]:
        if day_slots:
            _print_day(day_names[day_date], day_slots)
        else:
            print(f"\nNo data available for {day_date}.")

    print()


if __name__ == "__main__":
    main()
