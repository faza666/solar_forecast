# Apps/solar_forecast/

Open-Meteo → PV output forecast; prints an ASCII chart. Run with `python solar_forecast.py`. Own git repo. Read-only against a public API — no key, no side effects.

Two files: `solar_forecast.py` (forecast, prints an ASCII chart) and `solar_history.py` (same model against the Open-Meteo archive API, writes `solar_history.json` — 30 days of daily and hourly modelled output). Site parameters (48.621°N/22.288°E, 9 kW, 45° tilt, azimuth −45 = south-east, performance ratio 0.85, temp coeff −0.4 %/°C, 9 kW inverter clip) are module-level constants at the top of `solar_forecast.py`; `solar_history.py` imports them — change them there, not via flags.

## Where the site parameters come from

`PEAK_KW`, `AZIMUTH` and `PERFORMANCE_RATIO` were **fitted on 2026-09-12** against Home Assistant's recorder statistics for `sensor.stuff_room_192_168_0_5_pv_power` (uncurtailed clear hours, 2026-08-14 → 09-11), not taken from a datasheet. The data fixes only the product `PEAK_KW × PERFORMANCE_RATIO ≈ 7.7 kW` at azimuth −45; 9.0 / 0.85 is one consistent split. If the real panel nameplate total is ever known, put it in `PEAK_KW` and set PR = 7.7 / PEAK_KW.

The array is really **two strings facing differently** — PV1 ≈ 45°/−60° (~3.4 kW effective), PV2 ≈ 45°/−30° (~4.4 kW effective); azimuth −45 is the single-plane approximation (RMSE 0.24 kW vs 1.0 kW for due south). A two-string model would need two GTI queries.

## Morning shading model

The panels are a single row in a built-up area and a building to the ESE shades them every morning. Measured from HA 5-minute statistics on clear days (2026-09-02 → 09-09): **string 1 clears when the sun's azimuth passes ~112°, string 2 at ~126°** (09:40 / 10:40 local in early September, stable to ±5 min day to day); while shaded a string gives ~20 % of expected (diffuse light). The transition is a one- or two-step jump, as expected for a shadow edge sweeping along series-connected panels.

`solar_forecast.py` implements this as `shading_factor()` — a stdlib NOAA sun-azimuth calculation and a three-level factor (0.20 / 0.55 / 1.00) sampled every 10 min within each hour. Constants: `SHADE_CLEAR_AZ_PV1/PV2`, `PV1_SHARE`, `SHADED_FRACTION`. With it, clear-day mornings match HA to within ~10 % per hour.

**Caveat:** one season of data fixes the obstruction's azimuth but not its height. The pure azimuth rule over-shades in summer (sun high enough to clear the roofline earlier — mid-August 10:00 slots already come out ~25 % low) and under-shades in winter (sun at 0–6° elevation at those azimuths). Re-measure the edges in December and June from HA 5-minute data (`recorder/statistics_during_period`, period `5minute`, kept ~10 days) to add an elevation term.

No afternoon or evening shading was detectable; those hours are mostly hidden by curtailment (below).

## Why actual production is far below the model

The Deye runs in **`Zero Export To Load`** with export off, so once the battery is full the inverter throttles PV to the house load. In Aug–Sep 2026 that made actual production ~55 % of the modelled 30-day total, with mornings matching the model (ratio 1.03) and afternoons at ~36 %. That is a load/battery effect, not a weather one — no irradiance-based constant can reproduce it. Max PV input is also capped at 9 kW by the inverter's `pv_power` setting (`INVERTER_MAX_KW`).

Relies on Open-Meteo's `global_tilted_irradiance`, so no manual sun-geometry math is needed.

The site parameters describe the same 8 kW Deye inverter that `HomeAssistant/` monitors — if the physical array changes, both need updating.
