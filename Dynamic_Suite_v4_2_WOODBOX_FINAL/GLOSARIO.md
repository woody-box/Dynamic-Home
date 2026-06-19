# Glosario (Suite Dynamic Home)

## Conceptos comunes
- **Suite**: conjunto de módulos DC (clima), DV (ventilación), DS (persianas) coordinados por SDHB (bus).
- **Package (HA)**: archivo YAML cargado como paquete en Home Assistant (`/config/packages/...`).

## SDHB (BUS)
- **Intent**: petición/objetivo publicada al bus (ej. `request_solar_shield`, `request_quiet`).
- **Source**: emisor del intent (ej. `dc_zone01`, `ds_w1`, `dv_vmc`).
- **Target**: destino del intent (ej. `ds`, `ds_w1`, `dv_vmc`).
- **Slot**: espacio por source donde vive su intent actual; se reemplaza si el source publica otro.
- **TTL**: tiempo de vida de un intent; al expirar, el slot se vacía y el winner puede cambiar.
- **Winner**: intent ganador por target (resultado del arbitraje).
- **ACK / Feedback**: confirmación desde un módulo (ej. DS) de si aplicó o ignoró el winner.

## DC (Dynamic Climate)
- **Target**: consigna final que DC quiere aplicar (temperatura objetivo).
- **Target step**: cuantización del target (ej. 0.5°C).
- **Bias**: corrección aplicada al target por condiciones (exterior, fachadas, VMC, tendencia…).
- **Lead**: ajuste para anticipar inercia (subir/bajar antes para no pasarse).
- **Dew risk**: riesgo de condensación; puede forzar OFF o limitar frío.

## DV (Dynamic Ventilation)
- **IAQ**: calidad de aire interior (CO₂, PM2.5…).
- **Driver**: capa que aplica la velocidad real (V1/V2/V3).
- **Startup grace**: ventana de arranque para evitar falsos KO mientras se resuelven entidades.

## DS (Dynamic Shutter)
- **Target position**: posición objetivo de persiana (0–100%).
- **Reason code**: motivo seleccionado para la decisión final (trazabilidad).
- **Facade / Zone**: asignación de ventana a fachada y zona climática.

## Contratos / Onboarding
- **hw_map**: mapa de entidades hardware (la “HAL” del módulo).
- **REPLACE_***: placeholder sin resolver en hw_map; debe sustituirse por entity_id reales.
- **Contract OK**: sensor/binario que indica si el módulo tiene hardware/config suficiente para operar.


## EMA (Exponential Moving Average)
- Filtro de media móvil exponencial para estabilizar señales (CO₂/PM2.5). En DV se controla con toggles `*_ema_enabled`.


## health_summary / health_code
- Sensores de estado corto para diagnóstico rápido (OK/WARN/FAIL) sin depender de JSON grandes.


## invalid_payload_json
- Error del bus SDHB cuando un `payload` que parece JSON no puede parsearse; el slot no se escribe y se emite `sdhb_error`.
