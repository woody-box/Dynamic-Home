# SDHB Contracts (v4.2)

Este documento define el **contrato canónico** de la suite (DC / DV / DS) para:
- Targets
- Diccionario de intents
- Prioridades
- TTL/cooldowns recomendados
- Esquema de feedback ACK

## Targets

- **DC zonas**: `dc_zone01..dc_zone08`
- **DS ventanas**: `ds_w1..ds_w8`
- **DS fachadas (convención)**: `ds_f000..ds_f359` (azimut 000–359, 3 dígitos)
- **DV**: `dv` (VMC única)

> Nota: hoy se recomienda que el **publisher (DC)** expanda `ds_fXXX → ds_wX`.  

## Intents (canónicos)

- `request_weather_protect`
- `request_preheat` (anticipación térmica)
- `request_solar_gain` (favorecer ganancia solar)
- `request_solar_shield`
- `request_privacy`
- `request_quiet`
- `request_eco`
- `request_normal`
- `request_boost`
- `request_freecool` (futuro / opcional)

> Nota: el contrato es el **superconjunto** del vocabulario del bus. Algunos intents pueden no usarse aún en todos los módulos.

## Prioridades globales (recomendadas)

| Intent | Priority |
|---|---:|
| request_weather_protect | 100 |
| request_solar_shield | 80 |
| request_privacy | 70 |
| request_quiet | 60 |
| request_eco | 20 |
- `request_solar_shield`
- `request_privacy`
- `request_quiet`
- `request_eco`
- `request_freecool` (futuro / opcional)

## TTL / cooldown (guía)

- weather_protect: 300–900s  
- solar_shield: 300–1800s  
- privacy: 1800–7200s  
- quiet/eco: 600–3600s  

## Feedback ACK (consumer → bus)

Campos recomendados:
- `source`, `target`, `intent`
- `status`: `accepted | ignored | blocked | none`
- `applied`: `true|false`
- `reason`: `bus_disabled`, `consume_disabled`, `weather_protect`, `wind_cap`, etc.
- `ts`

Buenas prácticas:
- Enviar ACK **solo si cambia** `status/reason`.
- Añadir **cooldown** para evitar spam.
