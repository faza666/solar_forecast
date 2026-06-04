"""Solar power production forecast for a rooftop PV system.

Fetches hourly weather data from Open-Meteo and estimates power output
for today and tomorrow.

System configuration (hardcoded for this installation):
  Location  : Uzhgorod, Ukraine  (48.621°N, 22.288°E)
  Peak power: 8 kW
  Tilt      : 45°
  Azimuth   : 0° (south-facing)

Open-Meteo is a free, no-auth API — no credentials needed.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime
from typing import List

import requests

# ---------------------------------------------------------------------------
# System constants
# ---------------------------------------------------------------------------

LATITUDE = 48.621025
LONGITUDE = 22.288229
TIMEZONE = "Europe/Kyiv"
PEAK_KW = 8.0
TILT = 45          # degrees from horizontal
AZIMUTH = 0        # 0 = south (Open-Meteo convention)
PERFORMANCE_RATIO = 0.80   # accounts for inverter losses, wiring, soiling, etc.

# Temperature coefficient of power (typical c-Si panel: -0.4 %/°C)
TEMP_COEFF = -0.004
# Reference temperature at standard test conditions (STC)
STC_TEMP = 25.0
# Simplified cell-temperature rise above ambient (NOCT model)
NOCT_RISE = 25.0

API_URL = "https://api.open-meteo.com/v1/forecast"

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
        return round(self.gti / 1000.0 * PEAK_KW * PERFORMANCE_RATIO * temp_correction, 3)

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
