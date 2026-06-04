# Solar Power Forecast

Fetches an hourly weather forecast from [Open-Meteo](https://open-meteo.com) and estimates the power output of a rooftop solar PV system for **today and tomorrow**.

**No API key or login required** — Open-Meteo is a free, open-source service.

---

## System configuration

| Parameter | Value |
|---|---|
| Location | Uzhgorod, Ukraine (48.621°N, 22.288°E) |
| Peak power | 8 kW |
| Panel orientation | South-facing (azimuth 0°) |
| Panel tilt | 45° |
| Performance ratio | 0.80 (inverter losses, wiring, soiling) |
| Temperature coefficient | –0.4 %/°C (standard c-Si) |

---

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python solar_forecast.py
```

### Sample output

```
==============================================================================
  Solar Power Forecast — Uzhgorod, Ukraine
  8 kW south-facing array, tilt 45°  |  Performance ratio: 80%  |  Temp coeff: -0.4%/°C
==============================================================================

TODAY — Wednesday, 2026-06-04
──────────────────────────────────────────────────────────────────────────────
   Hour      GTI  Cloud    Temp     Power  Chart (0–8 kW)
──────────────────────────────────────────────────────────────────────────────
  05:00       38    20%   13.5°C    0.23 kW  
  06:00      210    15%   14.2°C    1.26 kW  ████
  07:00      480    10%   15.8°C    2.88 kW  ██████████
  ...
  13:00      820     5%   24.0°C    4.68 kW  ████████████████
  ...
  20:00       18    55%   20.1°C    0.10 kW  
──────────────────────────────────────────────────────────────────────────────
  Total: 34.6 kWh  |  Peak: 4.85 kW at 13:00  |  Sunshine: 13h 10m
```

---

## Power model

```
cell_temp    = ambient_temp + 25°C          (simplified NOCT model)
temp_factor  = 1 + (−0.004) × (cell_temp − 25)
Power (kW)   = GTI (W/m²) ÷ 1000 × 8 kW × 0.80 × temp_factor
Energy (kWh) = Power (kW) × 1 h
```

`global_tilted_irradiance` (GTI) is computed by Open-Meteo for the exact panel angle and orientation — no manual geometric correction needed.

The performance ratio (0.80) accounts for:
- Inverter conversion efficiency (~96%)
- Wiring and connection losses (~2%)
- Soiling / shading / mismatch (~5%)
- Remaining system overhead
