# SDHB · FILE MAP — Suite v4.2 (BUS v4.2)

## Archivos (SDHB bus split)
- `sdhb/sdhb_bus_helpers_v4_2.yaml` — helpers (input_boolean/input_select/input_text/input_number/input_datetime)
- `sdhb/suite_dynamic_home_bus_v4_2.yaml` — core logic (scripts + template sensors)
- `sdhb/sdhb_bus_automations_v4_2.yaml` — automations (winner-change, feedback reset, etc.)

## Qué contiene (alto nivel)
- Helpers globales (enable + slots por source)
- Scripts API (publish_intent / clear_intent / heartbeat / feedback)
- Winners por target (sensor.sdhb_winner_*)
- Arbitraje (prioridad + TTL)
- Health (summary + code)
- Error counter (counter.sdhb_error_count + sensor.sdhb_error_count) + reset diario
- Feedback summary (sensor.sdhb_feedback_summary)
- Guard payload truncation en publish_intent (>250 chars → sdhb_error)

## Secciones internas (resumen)
- input_select: intents por source
- input_text: target/payload/feedback details
- input_number: priority/ttl/last_seen_ts/métricas
- input_datetime: ts/expires_at
- template sensors: winner_global + winners por target + health/stats/version
- automations: orquestación de winner y resets

## Tests (opcionales)
- `sdhb/sdhb_testing_integration_optional_v4_2.yaml` — SDHB integration tests (bus E2E within SDHB)
- `sdhb/sdhb_testing_e2e_optional_v4_2.yaml` — E2E integration tests
- `sdhb/sdhb_testing_recovery_optional_v4_2.yaml` — Recovery tests (TTL expiry, fallbacks)



## Cambios recientes (v4.2 · hotfix bus)

### Estructura (Refactor A)
El BUS se divide en 3 packages (no se clona):
- `sdhb_bus_helpers_v4_2.yaml` — helpers (input_* y counters)
- `suite_dynamic_home_bus_v4_2.yaml` — lógica: scripts + template winners/health
- `sdhb_bus_automations_v4_2.yaml` — automations del BUS

### Observabilidad/robustez (B)
- `counter.sdhb_error_count` + reset diario (00:00).
- Guard de truncado de `payload` (>250 chars): emite `sdhb_error` (`payload_truncated`) y guarda un payload seguro.
- `sensor.sdhb_feedback_summary`: agregación de feedback_applied (conteo + lista).

### Rendimiento (C1)
- `sdhb_publish_intent`: si el slot ya contiene el mismo `{intent,priority,ttl,payload}` y el publish llega dentro de 1s, **no reescribe** helpers.

### ACK anti‑spam (D)
- `input_number.sdhb_feedback_ack_cooldown_s` (default 90s).
- `sdhb_feedback`: si llega el mismo ACK (status+intent+reason+applied) dentro del cooldown, se ignora.

### Rate‑limit de eventos (C2)
- `input_number.sdhb_winner_event_rate_limit_s` (default 1s).
- `sdhb_winner_change_event`: rate‑limit por **target** del evento `sdhb_winner_changed`.



Roadmap extra aplicado:
- sdhb_ttl_cleanup_5m: limpia slots expirados cada 5 min (cosmético + claridad de helpers)
- sdhb_startup_feedback_guard: limpia feedback_applied sucios al arrancar
- sensor.sdhb_intent_history: historial corto (~15) de cambios de winner (via evento sdhb_winner_changed)
