# Brand assets

Emblemas transparentes (sin texto) y assets de marca de Dynamic Home.

| Archivo | Uso |
|---|---|
| `icon.png` (256×256) | Icono de la integración para `home-assistant/brands` |
| `icon@2x.png` (512×512) | Versión @2x del icono |
| `logo.png` | Logo con texto (opcional para brands) |
| `dynamic_home.png` | Emblema Home (transparente, 512) |
| `dynamic_climate.png` | Emblema Climate (transparente, 512) |
| `dynamic_ventilation.png` | Emblema Ventilation (transparente, 512) |
| `dynamic_shutter.png` | Emblema Shutter (transparente, 512) |

## Publicar el icono en Home Assistant / HACS

El icono que muestra HA/HACS sale del repo oficial
[`home-assistant/brands`](https://github.com/home-assistant/brands), no de aquí.
Para publicarlo, abre un PR allí con:

```
custom_integrations/dynamic_home/icon.png      (= docs/brand/icon.png)
custom_integrations/dynamic_home/icon@2x.png   (= docs/brand/icon@2x.png)
custom_integrations/dynamic_home/logo.png      (opcional, = docs/brand/logo.png)
```
