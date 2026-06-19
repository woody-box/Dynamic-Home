SDHB · Documentación final (Suite v4.2 · BUS v4.2)
===================================================

Incluye:
- manuales_docx/sdhb_manual_v4_2.docx
- txt_md/sdhb_index_v4_2.txt
- txt_md/sdhb_quickstart_v4_2.txt
- txt_md/filemap_sdhb_v4_2.md
- sdhb/sdhb_bus_helpers_v4_2.yaml
- sdhb/suite_dynamic_home_bus_v4_2.yaml
- sdhb/sdhb_bus_automations_v4_2.yaml


Added optional package: sdhb_testing_e2e_optional_v4_2.yaml (DC→SDHB→DS end-to-end tests)


Roadmap extra aplicado:
- sdhb_ttl_cleanup_5m: limpia slots expirados cada 5 min (cosmético + claridad de helpers)
- sdhb_startup_feedback_guard: limpia feedback_applied sucios al arrancar
- sensor.sdhb_intent_history: historial corto (~15) de cambios de winner (via evento sdhb_winner_changed)
