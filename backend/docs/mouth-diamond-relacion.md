# Análisis: relación entre `useDiamondFade` y el “hueco” de la boca

## Resumen corto
Sí hay una relación directa y fuerte. El diamante no “suaviza” la zona: **la recorta con `discard`** en el shader de la malla superficial cuando la boca entra en modo abierto (`mouthPointsVisibleLatched`). Ese `discard` elimina justo la superficie que antes veía el “labio alargado” (textura estirada), por eso aparece fondo blanco con solo algunas partículas/puntos. La prueba clave está en el fragment shader.

## Cadena técnica exacta (de código a síntoma visual)

1. Al hablar, `mouthOpenVisual` sube y activa un latch para mostrar puntos de boca (`mouthPointsVisibleLatched`).
2. Ese latch se pasa al shader de la malla como `uMouthHoleActive`.
3. Si además `useDiamondFade` está activo, el shader calcula si cada fragmento cae dentro del rombo (`diamondField <= 1`).
4. Si se cumplen ambas condiciones (`uMouthHoleActive` y dentro del rombo), el fragmento se **descarta** (`discard`).
5. Resultado visual: desaparece la malla en el centro de la boca (ya no hay “labio alargado” por textura), y lo que queda es el sistema de puntos de boca + fondo.

Referencias principales:
- Latch de boca abierta y uniform `uMouthHoleActive`.【F:backend/avatar_app/app.js†L3410-L3415】【F:backend/avatar_app/app.js†L3504-L3504】
- Activación y parámetros del diamante en uniforms (`uUseDiamondFade`, `uFadeDiamond*`).【F:backend/avatar_app/app.js†L2211-L2217】【F:backend/avatar_app/app.js†L3498-L3503】
- Recorte real del rombo mediante `discard` en fragment shader.【F:backend/avatar_app/app.js†L1766-L1772】

## Por qué antes se veía “labio alargado” y con rombo no

Sin rombo, la malla de superficie se mantiene (aunque con alpha reducido por `mouthFade`) y sigue muestreando la textura del rostro/labio, lo que puede percibirse como ese “labio estirado”. Con rombo, esa malla **ya no se dibuja en esa zona** porque se descarta, así que no hay superficie a la que aplicar textura.

- Atenuación de alpha de malla en apertura (`outAlpha` cae hacia `meshAlphaMin`, pero no obliga a desaparecer por completo).【F:backend/avatar_app/app.js†L1761-L1765】【F:backend/avatar_app/app.js†L1824-L1825】
- Recorte duro del diamante con `discard` (sí elimina completamente).【F:backend/avatar_app/app.js†L1769-L1772】

## Por qué quedan “algunas bolitas dispersas”

Porque el sistema de boca abierta dibuja una nube de puntos separada (`mouthPoints`) con su propia máscara (rim/inner), alpha y clipping. No es una malla continua.

- Construcción de puntos de boca con máscara de borde + inner gain (`mouthRimMaskFromWeight`).【F:backend/avatar_app/app.js†L1205-L1209】【F:backend/avatar_app/app.js†L1247-L1253】
- Render como `THREE.Points`, no como malla continua.【F:backend/avatar_app/app.js†L2278-L2282】
- Fragment shader de puntos con alpha y discard por clip circular/alpha mínima.【F:backend/avatar_app/app.js†L1457-L1466】

Además, por defecto se descartan puntos “de atrás” (`pointsCullBack = true`), así que en el hueco central puede haber menos cobertura de la que intuitivamente esperarías.

- Default de `pointsCullBack` activado.【F:backend/avatar_app/app.js†L1144-L1145】
- Uniform de cull back aplicado en shader de puntos.【F:backend/avatar_app/app.js†L2269-L2270】【F:backend/avatar_app/app.js†L1465-L1465】

## Por qué al hacer el diamante más pequeño vuelve a verse el “labio alargado”

Porque el área descartada (`diamondInside`) se reduce. Entonces parte de la malla superficial deja de ser recortada y vuelve a verse la textura base estirada en esa zona.

Esto concuerda con la forma en que se calcula el rombo: `|x|/rx + |y|/ry <= 1`; bajar `rx`/`ry` hace el rombo más chico y elimina menos fragmentos.【F:backend/avatar_app/app.js†L1766-L1768】

## Prueba numérica reproducible

Se añadió un script para muestrear la región de boca con las mismas fórmulas de máscara de boca y diamante, comparando tamaño default vs uno menor.

- Script: `scripts/analyze_mouth_diamond.py`.
- Resultado típico:
  - `default (rx=0.11, ry=0.07)`: recorta ~15.3% del área de boca y ~100% de la zona más interna (`w > 0.70`).
  - `smaller (rx=0.06, ry=0.035)`: recorta ~4.2% del área y ~81% de la zona interna.

Conclusión: reducir el rombo deja más superficie central sin recorte, por eso vuelve la percepción del “labio alargado”.

## Hipótesis cerrada

La relación que buscabas es esta:
- El rombo **no compite** con la malla de labio: la **anula** localmente por `discard`.
- Lo que ves después (bolitas + fondo) es el sistema de `mouthPoints`, que no rellena como malla continua y además culla parte de puntos traseros.
- Al reducir rombo, la anulación cubre menos y reaparece la malla/texture stretch.
