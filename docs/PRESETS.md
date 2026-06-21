# Dynamic Home — Inventario de valores / presets

> Generado desde el catálogo de opciones (`options_spec`), los motores (`*_engine`) y los presets (`presets.py`). Solo números, sin entidades.

Cada parámetro es ajustable por UI (Ajustes → la integración → Configurar). Los marcados **(av.)** solo aparecen con el **Modo avanzado** de Home Assistant. Para cargar un perfil de golpe: menú de opciones → **Aplicar un preset**.


## DC · Dynamic Climate

Dos columnas: **Default** (valor genérico del motor) y **Preset Salón** (perfil *suelo radiante / fuente comunitaria*, cosechado de la suite YAML). Vacío en Preset = igual que el default.


### Consignas base

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Base calor (°C) | 22.5 | 22 | Punto de partida en calefacción de día. Alimenta la Base activa y, en cascada, el target. Ajústala a tu confort real (ej. 22,0–22,8 °C) y deja que los biases hagan el resto. |
| Base frío (°C) | 26.5 | 26.5 | Punto de partida en refrigeración de día. Empieza conservador (26–27 °C) para evitar enfriamientos agresivos y oscilaciones. |
| Atenuación nocturna (°C) | 0.5 | 0.5 | Cuánto relaja la base de noche (sol < −3°): baja la consigna en calor y la sube en frío. Si de noche te pasas de calor, súbela poco a poco (0,1 en 0,1). |
| Vacaciones calor (°C) | 17 | 17 | Base de calefacción con el modo Vacaciones activo (consigna reducida de ahorro). |
| Vacaciones frío (°C) | 30 | 30 | Base de refrigeración con el modo Vacaciones activo (consigna elevada de ahorro). |

### Límites de consigna

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Calor mín. (°C) | 18 | 20.5 | Consigna mínima en calefacción (modo normal). El target final nunca baja de aquí. |
| Calor máx. (°C) | 26 | 23.5 | Consigna máxima en calefacción (modo normal). El target final nunca sube de aquí. |
| Frío mín. (°C) | 22 | 25 | Consigna mínima en refrigeración (modo normal). |
| Frío máx. (°C) | 29 | 28 | Consigna máxima en refrigeración (modo normal). |
| Paso de cuantización (°C) | 0.5 | 0.1 | Paso de cuantización del target final (redondeo), ej. 0,1 °C. |
| Bias máx. calor (°C) *(av.)* | 0.8 | 1.5 | Tope duro al empuje total de todos los biases/frenos en calor, antes del target limitado. Si se queda corto, súbelo en pasos pequeños; si va agresivo, bájalo o revisa antes los biases. |
| Bias máx. frío (°C) *(av.)* | 0.8 | 1.5 | Tope duro al empuje total de todos los biases/frenos en frío (igual que el de calor). |
| Delta mín. aplicar (°C) | 0 | 0.2 | Cambio mínimo respecto a la última consigna antes de enviar una nueva al termostato (anti-jitter). 0 aplica siempre; con paso pequeño (0,1) prueba 0,2. |
| Vacaciones calor mín. (°C) | 15 | 15 | Consigna mínima de calefacción en vacaciones. |
| Vacaciones calor máx. (°C) | 19 | 19 | Consigna máxima de calefacción en vacaciones. |
| Vacaciones frío mín. (°C) | 28 | 28 | Consigna mínima de refrigeración en vacaciones. |
| Vacaciones frío máx. (°C) | 31 | 31 | Consigna máxima de refrigeración en vacaciones. |

### Bias exterior

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Umbral frío (°C) | 0 | 5 | Temp. exterior en o por debajo de la cual entra el bias de frío (compensación por frío). |
| Umbral calor (°C) | 30 | 30 | Temp. exterior en o por encima de la cual entra el bias de calor (compensación por calor). |
| Calor fuerte (°C) *(av.)* | 0.5 | 0.3 | Bias de calefacción cuando hace claramente frío (bajo el umbral). |
| Calor suave (°C) *(av.)* | 0.2 | 0.15 | Bias de calefacción en la banda suave justo por encima del umbral de frío. |
| Frío fuerte (°C) *(av.)* | 0.5 | 0.3 | Bias de refrigeración cuando hace claramente calor. |
| Frío suave (°C) *(av.)* | 0.2 | 0.15 | Bias de refrigeración en la banda suave cerca del umbral de calor. |
| Factor aislamiento *(av.)* | 1 | 0.6 | Multiplicador 0–1 del bias exterior: bájalo en viviendas bien aisladas. |

### Bias del bus

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Ganancia solar calor (°C) *(av.)* | -0.5 |  | Alivio de consigna cuando DC recibe del bus una intención de ganancia solar en calefacción (el sol calienta gratis). |
| Protección solar frío (°C) *(av.)* | 0.5 |  | Subida de consigna cuando DC recibe protección solar en refrigeración. |

### Bias VMC

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Bias calor V 1 *(av.)* | 0.1 | 0.05 | Compensación en calefacción con la VMC a V1 (la ventilación carga la estancia). |
| Bias calor V 2 *(av.)* | 0.2 | 0.1 | Compensación en calefacción con la VMC a V2. |
| Bias calor V 3 *(av.)* | 0.3 | 0.15 | Compensación en calefacción con la VMC a V3. |
| Bias frío V 1 *(av.)* | 0.1 | 0.05 | Compensación en refrigeración con la VMC a V1. |
| Bias frío V 2 *(av.)* | 0.2 | 0.1 | Compensación en refrigeración con la VMC a V2. |
| Bias frío V 3 *(av.)* | 0.3 | 0.15 | Compensación en refrigeración con la VMC a V3. |

### Tendencia y lead

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Lead de respaldo (h) *(av.)* | 1 | 1.5 | Anticipación de respaldo (horas) cuando faltan temperaturas para el modelo. |
| Desplaz. máx. tendencia (°C) *(av.)* | 0.25 | 0.2 | Máx. °C que la tendencia puede mover el target por ciclo (anti-pico). |
| Lead base (h) *(av.)* | 1 |  | Horizonte base de anticipación (horas). |
| Lead por °C (h) *(av.)* | 0.05 |  | Anticipación extra por °C de diferencia interior/exterior (inercia). |
| Lead por km/h (h) *(av.)* | 0.02 |  | Anticipación extra por km/h de viento (más pérdidas). |
| Lead mín. (h) *(av.)* | 0.5 | 1 | Tope inferior del lead calculado (horas). |
| Lead máx. (h) *(av.)* | 3 | 3 | Tope superior del lead calculado (horas). |
| Banda muerta (°C/h) *(av.)* | 0.1 | 0.12 | Tendencia por debajo de esto (°C/h) se trata como cero (ruido). |
| Alpha EMA tendencia *(av.)* | 0.3 | 0.25 | Suavizado de la EMA de tendencia (mayor = más reactivo). |

### Freno de tendencia

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Umbral freno 1 *(av.)* | 0.3 | 0.2 | Velocidad de tendencia (°C/h) para el paso 1 del freno (solo si la tendencia ya ayuda al modo). |
| Umbral freno 2 *(av.)* | 0.6 | 0.3 | Velocidad de tendencia (°C/h) para el paso 2 del freno. |
| Umbral freno 3 *(av.)* | 1 | 0.5 | Velocidad de tendencia (°C/h) para el paso 3 del freno. |
| Bias freno 1 *(av.)* | 0.1 | 0.1 | °C que resta el freno en el paso 1 para evitar sobrepasar. |
| Bias freno 2 *(av.)* | 0.2 | 0.2 | °C que resta el freno en el paso 2. |
| Bias freno 3 *(av.)* | 0.3 | 0.4 | °C que resta el freno en el paso 3. |

### Forecast

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Ganancia forecast *(av.)* | 0.1 | 0.08 | Cuánto relaja la consigna el forecast (°C por °C de ayuda prevista). Solo frena, nunca empuja. |
| Tope forecast (°C) *(av.)* | 0.5 | 0.8 | Máx. °C que puede aplicar el bias de forecast. |
| Ventana forecast (h) | 6 | 5 | Ventana de anticipación (horas) que se explora buscando el extremo que ayuda. |

### Lead adaptativo

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Alpha EMA *(av.)* | 0.2 | 0.2 | Suavizado EMA de la tasa/overshoot/retardo aprendidos. |
| Tasa de aprendizaje *(av.)* | 0.1 | 0.1 | Paso de aprendizaje hacia el lead objetivo en cada ciclo. |
| Overshoot objetivo (°C) *(av.)* | 0.1 | 0.1 | Overshoot tolerado (°C) antes de corregir el lead. |
| Suelo de tasa (°C/h) *(av.)* | 0.05 | 0.05 | Suelo de la tasa de calentamiento/enfriamiento aprendida (evita dividir por cero). |
| Peso del retardo *(av.)* | 1 | 1 | Peso del retardo térmico aprendido en el lead. |
| Duración ON mín. (h) *(av.)* | 0.25 | 0.25 | Duración ON mínima (h) para fiarse de una muestra de tasa. |
| ΔT mín. (°C) *(av.)* | 0.05 | 0.05 | Cambio de temperatura mínimo (°C) para fiarse de una muestra. |
| Ventana de asentamiento (h) *(av.)* | 3 | 3 | Ventana (h) vigilada tras apagar para aprender overshoot y retardo. |
| Lead adapt. mín. (h) *(av.)* | 0 |  | Tope inferior del lead aprendido (horas). |
| Lead adapt. máx. (h) *(av.)* | 4 |  | Tope superior del lead aprendido (horas). |

### Condensación

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Margen punto rocío (°C) | 2 |  | Riesgo de condensación cuando la temp. interior está a este margen del punto de rocío (seguridad de suelo refrescante). |

### Bias de fachadas

| Parámetro | Default | Preset Salón | Qué es |
|---|---|---|---|
| Ganancia fachada calor (°C) *(av.)* | 0.3 | 0.15 | Alivio máx. de consigna por fachadas soleadas abiertas en calefacción (ganancia solar gratis). |
| Ganancia fachada frío (°C) *(av.)* | 0.3 | 0.15 | Alivio máx. de consigna por fachadas soleadas en refrigeración. |

## DV · Dynamic Ventilation

Valores de fábrica del motor. (En tu instalación viva tienes algunos afinados: PM2.5 a 8/20 y ducha ΔHR a 4,5/3,5.)


### Umbrales de calidad de aire

| Parámetro | Default | Qué es |
|---|---|---|
| CO₂ → V2 (ppm) | 900 | Nivel de CO₂ (ppm) que sube la VMC a V2. Los umbrales deciden cuándo subir velocidad. |
| CO₂ → V3 (ppm) | 1300 | Nivel de CO₂ (ppm) que sube la VMC a V3. |
| PM2.5 → V2 (µg/m³) | 15 | Nivel de PM2.5 (µg/m³) que sube la VMC a V2. |
| PM2.5 → V3 (µg/m³) | 40 | Nivel de PM2.5 (µg/m³) que sube la VMC a V3. |
| Histéresis CO₂ (ppm) | 100 | Margen de bajada de CO₂ antes de bajar velocidad. Evita el «diente de sierra»; si oscila, súbela un poco. |
| Histéresis PM2.5 (µg/m³) | 5 | Margen de bajada de PM2.5 antes de bajar velocidad (anti diente de sierra). |

### Suavizado de sensores

| Parámetro | Default | Qué es |
|---|---|---|
| Suavizar CO₂ (EMA) | sí | Suaviza el CO₂ con una EMA antes de decidir (menos ruido). |
| Suavizar PM2.5 (EMA) | sí | Suaviza el PM2.5 con una EMA antes de decidir. |
| Alpha EMA CO₂ *(av.)* | 0.2 | Factor EMA del CO₂ (mayor = más reactivo, menos suavizado). |
| Alpha EMA PM2.5 *(av.)* | 0.2 | Factor EMA del PM2.5 (mayor = más reactivo). |

### Free-cooling

| Parámetro | Default | Qué es |
|---|---|---|
| Temp. ext. mínima (°C) | 5 | No hacer free-cooling por debajo de esta temp. exterior (demasiado frío). |
| ΔT activación (°C) | 2 | ΔT interior−exterior que inicia el free-cooling. |
| ΔT desactivación (°C) | 1 | ΔT que detiene el free-cooling (histéresis). |

### Exterior hostil

| Parámetro | Default | Qué es |
|---|---|---|
| Umbral AQI 1 | 50 | AQI exterior que limita la VMC a V2 (exterior empezando a ser malo). |
| Umbral AQI 2 | 100 | AQI exterior que limita la VMC a V1. |
| Umbral AQI 3 | 150 | AQI exterior que apaga la VMC (no meter aire muy malo). |

### Anticondensación

| Parámetro | Default | Qué es |
|---|---|---|
| ΔT seco V2 (°C) | 0.2 | Ventaja de rocío (dp_interior − dp_exterior, °C) para secar a V2. |
| ΔT seco V3 (°C) | 1 | Ventaja de rocío para secar a V3. |
| Margen punto rocío (°C) | 1.5 | Temp. interior a este margen del punto de rocío marca riesgo de condensación. |

### Failsafe y arranque

| Parámetro | Default | Qué es |
|---|---|---|
| Sensor obsoleto (s) *(av.)* | 120 | Un sensor vital más viejo que esto (s) cuenta como fallo. |
| Gracia de arranque (s) *(av.)* | 120 | Gracia tras arrancar antes de que pueda saltar el failsafe (s). |
| Ventana de fallos (s) *(av.)* | 7200 | Ventana (s) en la que se cuentan los fallos repetidos. |
| Límite de fallos *(av.)* | 3 | Fallos dentro de la ventana que arman un bloqueo. |
| Bloqueo (s) *(av.)* | 1800 | Cuánto dura el bloqueo del failsafe (s). |

### Refuerzo de ducha

| Parámetro | Default | Qué es |
|---|---|---|
| Δ HR activación (%) | 8 | Subida de HR del baño (Δ%) que dispara el refuerzo de ducha. Si detecta «falsas duchas», súbelo. |
| Δ HR desactivación (%) | 4 | Δ de HR por debajo del cual termina el refuerzo. Si corta demasiado pronto, bájalo. |
| Mantener (s) | 600 | Tiempo mínimo de mantenimiento del refuerzo (segundos). Si corta pronto, súbelo. |
| Velocidad de ducha | 3 | Velocidad objetivo mientras se detecta ducha (V2/V3). |

### Umbrales adaptativos

| Parámetro | Default | Qué es |
|---|---|---|
| Muestras mínimas *(av.)* | 100 | Lecturas necesarias antes de usar umbrales IAQ adaptativos. |

## DS · Dynamic Shutter

**Defaults de diseño** (no cosechados: no había suite YAML de persianas). Pistas de campo: posiciones parciales 25 % / 65 % usadas en tus botoneras.


### Posiciones de persiana

| Parámetro | Default | Qué es |
|---|---|---|
| Cierre por lluvia (%) | 0 | Posición de la persiana cuando llueve (protección). |
| Free-cool máx. (%) | 60 | Apertura máx. permitida durante el free-cooling. |
| Verano mín. (%) | 20 | Apertura mínima que se mantiene en verano. |
| Noche invierno (%) | 0 | Posición en noches de invierno (cerrar para aislar). |
| Meteo máx. (%) | 30 | Apertura máx. bajo una alerta meteo. |
| Protección solar máx. (%) | 30 | Apertura máx. cuando DC pide protección solar (refrigeración). |

### Deltas térmicos

| Parámetro | Default | Qué es |
|---|---|---|
| ΔT free-cool (°C) | 0.8 | ΔT interior−exterior que justifica abrir para free-cooling. |
| ΔT calor (°C) | 0.8 | ΔT por encima del cual la estancia cuenta como caliente (lógica de sombreo). |

### Protección de viento

| Parámetro | Default | Qué es |
|---|---|---|
| Límite de viento (km/h) | 40 | Velocidad de viento que fuerza el cierre protector. |
| Rango cap viento (km/h) *(av.)* | 20 | Rango por encima del límite en el que se limita progresivamente la apertura. |
| Histéresis cap viento (km/h) *(av.)* | 5 | Histéresis para soltar el cap de viento. |

### Slew rate

| Parámetro | Default | Qué es |
|---|---|---|
| Limitar slew rate | sí | Mover la persiana por pasos en vez de saltar (más suave, menos arranques de motor). |
| Paso slew (%) | 10 | Máx. % que cambia la posición por paso. |

### Geometría de ventana

| Parámetro | Default | Qué es |
|---|---|---|
| Altura ventana (cm) | 100 | Altura de la ventana para la geometría de penetración solar. |
| Voladizo (cm) | 0 | Profundidad del voladizo/alero sobre la ventana. |
