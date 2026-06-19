# Dynamic Climate (DC) · v4.2 (compact · fix_final)

Dynamic Climate es un **motor de consigna dinámica** para Home Assistant, pensado sobre todo para sistemas con **mucha inercia** (suelo radiante/refrescante).  
En lugar de usar una consigna “fija”, DC **calcula** una consigna objetivo en función de contexto (interior/exterior, tendencia, ventilación, aportes solares, seguridad por rocío, etc.) y la aplica periódicamente a la zona.

> Licencia: MIT · Autor original del proyecto: Woodbox (origen)  
> Esta versión está **alineada a estructura compacta v4.2** y naming determinista `dc_zone01..dc_zone08`.

---

## Por qué DC (qué lo diferencia de un termostato normal)

Un termostato típico hace: `si T < consigna → ON` y `si T > consigna → OFF`.  
En alta inercia eso suele provocar **sobre-impulsos**, lentitud de reacción y poca eficiencia.

DC añade:

- **Pipeline de cálculo** (paso a paso) para construir el target final (trazable).
- **Anticipación por tendencia/inercia** (reduce overshoot y oscilaciones).
- **Contexto multi-sensor** (T/H interior, exterior, ventilación, etc.).
- **Seguridad por rocío/condensación** (clave en refrescante).
- **Integración por BUS/SDHB** con otros módulos (DS/DV) para coordinar confort/eficiencia.
- **Producto clonable** por zonas (`dc_zone01..dc_zone08`), con backups y “factory reset”.

---

## Cómo funciona (visión rápida)

1) DC calcula un **target_raw** a partir de la situación actual (interior/exterior/tendencia/inputs).
2) Aplica **bias/limitaciones** (p. ej. por BUS/SDHB, por seguridad, por límites de usuario).
3) Obtiene un **target_final** y lo aplica con un loop periódico (automations/scripts).
4) Publica/consume señales por SDHB para coordinarse con persianas (DS) y ventilación (DV).

---

## Instalación rápida (DC solo)

Copia a `/config/packages/` los YAML obligatorios:

### Common
- `dc_common_inputs.yaml`
- `dc_common_logic.yaml`
- `dc_common_scripts.yaml`

### Zone01
- `dc_zone01_inputs.yaml`
- `dc_zone01_core.yaml`
- `dc_zone01_automations.yaml`
- `dc_zone01_sdhb.yaml`
- `dc_zone01_observability.yaml`

Opcional:
- `dc_testing_optional.yaml` (tests/sim)

Si vas a usar **backup/restore**, copia también los `.py` a `/config/AppDaemons/` y activa en `configuration.yaml`:
```yaml
AppDaemon:
```

---

## Estructura real de archivos (v4.2 compact)

### Common (obligatorios)
- `dc_common_inputs.yaml`  
  Helpers globales (labels de zonas, toggles, notify target, etc.).
- `dc_common_logic.yaml`  
  Contratos/checks comunes (onboarding y checks de hw_map/startup).
- `dc_common_scripts.yaml`  
  Scripts comunes (factory, backup/restore common y masters) + stats comunes.

### Zone01 (obligatorios)
- `dc_zone01_inputs.yaml`  
  Inputs/defaults de la zona.
- `dc_zone01_core.yaml`  
  Pipeline principal de cálculo (core/runtime).
- `dc_zone01_automations.yaml`  
  Loop de aplicación y automatizaciones.
- `dc_zone01_sdhb.yaml`  
  Integración SDHB (consume/publish/bias).
- `dc_zone01_observability.yaml`  
  Salud/diagnóstico/audit.

### Opcional
- `dc_testing_optional.yaml`  
  Simulador/tests.

---

## Regla importante (producto)

`dc_zones_total = N` implica que existen **zone01..zoneN**.

- Si instalas solo `zone01`, deja `dc_zones_total = 1`.
- Los scripts master (`dc_init_fabrica_all`, `dc_backup_all_*`) **asumen** que existen las zonas declaradas.

---

## BUS/SDHB (Suite Dynamic Home)

DC no incluye el BUS en su paquete. Debe instalarse como archivo independiente:

- `suite_dynamic_home_bus_v4_2.yaml`

---

## Licencia
MIT.


## Hardware map (instalación)
Este paquete requiere rellenar `sensor.dc_zone01_hw_map` sustituyendo los valores `REPLACE_*` por tus entity_id reales.
