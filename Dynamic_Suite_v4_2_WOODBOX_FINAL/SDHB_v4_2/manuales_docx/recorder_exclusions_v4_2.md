# Recorder (MariaDB) · Exclusiones recomendadas (v4.2)

Copia y pega este bloque en tu `configuration.yaml`.

```yaml
recorder:
  purge_keep_days: 7
  exclude:
    entity_globs:
      # Versiones
      - sensor.*_version
      - sensor.suite_dynamic_home_bus_version

      # SDHB (payloads/arrays grandes)
      - input_number.sdhb_*_ts
      - input_number.sdhb_*_last_seen_ts
      - input_text.sdhb_*_payload
      - input_text.sdhb_*_details
      - input_datetime.sdhb_*_expires_at
      - sensor.sdhb_winner_*
      - sensor.sdhb_intent_effective

      # DC (JSON grandes + runtime churn)
      - input_text.dc_zone*_telemetry_ring
      - sensor.dc_zone*_params_table
      - sensor.dc_zone*_auditoria_payload
      - sensor.dc_zone*_backup_storage
      - sensor.dc_zone*_selftest_storage
      - input_text.dc_zone*_sim_golden_json
      - sensor.dc_install_eval
      - input_number.dc_zone*_tendencia_*
      - input_number.dc_zone*_rt_off_*
      - input_number.dc_zone*_rt_on_*
      - input_number.dc_zone*_learn_*
      - input_number.dc_zone*_last_good_*

      # DV (debug/tests y semáforos rápidos)
      - sensor.dv_vmc_backup_storage
      - sensor.dv_vmc_fabrica_keys
      - sensor.dv_vmc_modules_catalog
      - sensor.dv_vmc_decision_debug
      - sensor.dv_vmc_degradation_events
      - input_text.dv_vmc_sim_golden_json
      - input_text.dv_vmc_golden_last*
      - input_text.dv_vmc_*_last_result
      - input_boolean.dv_vmc_driver_busy

      # DS (decision JSON y tests)
      - sensor.ds_w*_target_decision_json
      - sensor.ds_w*_decision_debug_json
      - sensor.ds_w*_tests_summary_json
      - sensor.ds_w*_backup_storage
      - sensor.ds_w*_fabrica_keys
      - input_text.ds_w*_tests_last_report
      - input_text.ds_w*_golden_last_report
      - input_text.ds_w*_golden_last_result
```
