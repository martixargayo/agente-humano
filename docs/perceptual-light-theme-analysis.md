# Análisis perceptual y arquitectónico para adaptación a fondo claro (sin cambios de código)

## 1) Análisis del sistema visual actual

### 1.1 Rol perceptual del fondo negro
El fondo negro absoluto no es un “color de interfaz”; es un componente activo del motor perceptual del avatar.

- **Funciona como sumidero de luminancia**: todo valor luminoso emitido por partículas claras tiene contraste máximo local y global.
- **Elimina información competidora**: al no haber textura, gradiente ni color de fondo, el sistema visual humano asigna prioridad a los puntos de la cara.
- **Amplifica la lectura de profundidad por superposición**: cuando múltiples partículas con alpha se apilan, el resultado parece “salir” del negro por acumulación de energía visual.
- **Favorece la segmentación figura-fondo**: la máscara facial es inmediatamente separable sin necesidad de borde explícito.

En términos de percepción, el negro establece una condición de **alto rango dinámico útil** para partículas luminosas semitransparentes.

### 1.2 Por qué las partículas claras funcionan bien sobre negro
Las partículas claras en este esquema se benefician de una asimetría perceptual:

- **Un punto claro sobre fondo oscuro se interpreta como señal** (objeto) y no como suciedad de superficie.
- **La suma aditiva perceptual de translucencias claras** incrementa la sensación de masa, especialmente en nariz, pómulos, arco supraorbital y labio superior.
- **El borde facial emerge por gradiente de densidad**, no por contorno dibujado: el negro “absorbe” las regiones de baja ocupación y deja visibles solo las de suficiente acumulación.

### 1.3 Cómo alpha + densidad generan volumen sin sombras reales
El volumen se construye por tres mecanismos combinados:

1. **Densidad espacial de vértices/partículas**: zonas anatómicamente convexas tienden a proyectar más puntos visibles por perspectiva.
2. **Acumulación de alpha por solape**: múltiples capas translúcidas elevan opacidad aparente local.
3. **Modulación por textura de densidad**: introduce variación microestructural que evita lectura plana tipo “spray uniforme”.

Sin sombras PBR, el cerebro reconstruye forma 3D usando **gradientes estadísticos de ocupación** y **contraste relativo intra-cara**.

### 1.4 Qué información se perdería al abandonar negro sin adaptación
Si el fondo deja de ser negro sin rediseño perceptual, se degradan:

- **Separación figura-fondo** en zonas de baja densidad (mandíbula, sienes, periferia de mejillas).
- **Jerarquía de planos** entre regiones centrales (nariz/boca/ojos) y regiones difusas.
- **Lectura de “emergencia desde el vacío”**: el efecto pasa de volumétrico a gráfico/ruidoso.
- **Cohesión global de la nube**: las partículas dejan de percibirse como cuerpo continuo y pasan a “grano flotante”.

---

## 2) Análisis de fallo: inversión literal

Escenario ingenuo:
- fondo = blanco
- partículas = negro
- mismo alpha
- misma density
- misma iluminación

### 2.1 Por qué colapsa el volumen
El colapso proviene de una no simetría psicofísica:

- En oscuro→claro, la acumulación aumenta energía visible.
- En claro→oscuro, la acumulación oscura sobre blanco se percibe más rápido como **ensuciamiento tonal** que como masa 3D.

El sistema deja de “emitir forma” y empieza a “restar luz”. La resta no conserva la misma lectura volumétrica con el mismo alpha.

### 2.2 Por qué aparece ruido visual
Con fondo blanco, los puntos oscuros de baja opacidad en periferia se leen como:

- grano de impresión,
- artefacto de compresión,
- textura accidental.

Es decir, el observador ya no interpreta cada punto como parte de una superficie facial coherente, sino como perturbación distribuida.

### 2.3 Por qué las zonas densas se vuelven manchas
Sin remapeo, la acumulación en nariz/cuencas/labios oscurece demasiado rápido y produce **bloques de tinta**.

- Se pierde gradiente interno.
- Se aplana el relieve.
- Se reduce la continuidad entre semitonos que antes modelaban volumen.

### 2.4 De “cara” a “suciedad”
Cuando la señal deja de ser jerárquica (rasgos centrales legibles + periferia sugerida) y pasa a ser distribución homogénea de puntos oscuros, el sistema perceptual clasifica el patrón como **ruido superficial**, no como objeto 3D antropomórfico.

---

## 3) Principio clave: inversión perceptual, no cromática

### 3.1 Definición
**Invertir perceptualmente** significa conservar la misma experiencia visual (legibilidad, volumen, jerarquía, foco), aunque cambien polaridad tonal y fondo.

No implica reemplazo 1:1 de colores.

### 3.2 Parámetros no simétricos entre modo oscuro y claro
No son simétricos:

- respuesta al contraste global,
- tolerancia al grano periférico,
- velocidad de saturación perceptual por solape,
- umbral de “mancha” en regiones de alta densidad.

### 3.3 Comportamiento de alpha oscuro sobre claro vs alpha claro sobre oscuro
- **Alpha claro sobre oscuro**: acumula brillo de forma legible, con transición suave hacia el fondo.
- **Alpha oscuro sobre claro**: acumula “tinta” de forma más abrupta; el fondo claro hace más visibles irregularidades y discontinuidades.

Por eso, mantener alpha idéntico no conserva semántica visual.

---

## 4) Estrategia conceptual para fondo claro (sin código)

### A) Fondo

#### A.1 Por qué no usar blanco puro
El blanco puro (#FFFFFF) comprime margen de contraste para semitonos oscuros finos y magnifica cualquier ruido de borde.

#### A.2 Qué blancos funcionan mejor
Conviene un **off-white técnico** (ligeramente gris o cálido/frío controlado) para:

- bajar agresividad de contraste extremo,
- permitir más escalas intermedias de partículas,
- preservar lectura editorial/científica limpia.

#### A.3 Temperatura y luminancia recomendadas
- Luminancia alta, pero no máxima.
- Temperatura neutra o levemente fría para sostener estética tecnológica sin “amarilleo papel”.

### B) Color base de partículas

#### B.1 Por qué no negro puro
Negro puro sobre fondo claro acelera la percepción de manchas y recorta microgradientes.

#### B.2 Rango tonal funcional
Usar oscuros profundos no absolutos (carbón/grafito) permite conservar detalle tonal en acumulación.

#### B.3 Efecto del matiz en volumen
Un matiz sutil (frío o neutro) ayuda a separar “señal estructural” de “suciedad acromática”, mejorando percepción de forma.

### C) Alpha y densidad

#### C.1 Por qué density debe reinterpretarse
La misma curva de ocupación no produce la misma lectura al cambiar polaridad. La densidad actual está calibrada para emisión sobre negro.

#### C.2 Problemas sin remapeo
- periferia ruidosa,
- centro sobreoscurecido,
- pérdida de continuidad entre planos.

#### C.3 Tipo de remapeo conceptual necesario
No cambiar arquitectura, sino **recalibrar respuesta perceptual**:

- comprimir contribución en altas densidades (evitar tinta sólida),
- limpiar contribución en bajas densidades periféricas (reducir grano),
- reservar rango medio para modelar volumen facial.

### D) Iluminación

#### D.1 Por qué cambia el comportamiento en fondo claro
En modo claro, la luz deja de competir contra negro y pasa a competir contra un fondo ya luminoso; el contraste útil de highlights/sombreado relativo disminuye.

#### D.2 Ajustes mínimos aceptables
- Rebalancear intensidades relativas para recuperar separación de planos.
- Ajustar sesgo tonal de contribución lumínica para no contaminar el fondo.

#### D.3 Qué no tocar
- No introducir sombras reales/PBR.
- No alterar lógica geométrica de partículas.
- No modificar pipeline de animación, rig o lipsync.

---

## 5) Conservación del sistema existente

### 5.1 NeckEditor y MouthEditor
Deben permanecer intactos porque operan sobre parámetros geométrico-cinemáticos (transformaciones, pesos, offsets), no sobre percepción cromática.

### 5.2 Rig por pesos (aHeadWeight)
Sigue siendo válido: su función es mezclar influencia de movimiento en la nube según región anatómica. Es independiente de polaridad visual.

### 5.3 Lógica de animación
Micro-movimiento, respiración y lipsync procedural describen dinámica temporal de la forma. El esquema claro/oscuro solo afecta cómo se **ve** esa forma, no cómo se **genera**.

### 5.4 Partes geométricas vs perceptuales
- **Geométricas**: topología GLB, distribución de vértices, pesos de rig, animación procedural.
- **Perceptuales**: fondo, rango tonal de partículas, respuesta de alpha/densidad, contraste efectivo de iluminación.

---

## 6) Arquitectura de soporte multi-tema (conceptual)

Objetivo: soportar modo oscuro y modo claro **sin duplicar shaders, geometría ni lógica**.

### 6.1 Modelo conceptual
Definir un **perfil perceptual de render** como estado de alto nivel:

- preset_dark
- preset_light

Cada preset modifica solo parámetros de apariencia (fondo, rango tonal, curvas perceptuales de alpha/density, balance de luz).

### 6.2 Principios de arquitectura
- Un único shader con parámetros temáticos.
- Una única fuente geométrica (GLB/vértices).
- Una única lógica de animación/rig/lipsync.
- Cambio de tema = conmutación de preset, no bifurcación de pipeline.

### 6.3 Beneficios
- Coherencia funcional entre modos.
- Menor riesgo de regresión.
- Mantenimiento centralizado del motor visual.

---

## 7) Criterios de validación visual

### 7.1 Zonas anatómicas críticas que deben conservar lectura
- puente y punta de nariz,
- cuencas oculares y arco de cejas,
- contorno y volumen de labios,
- transición pómulo-mejilla,
- recorte mandibular en periferia.

### 7.2 Contraste aceptable
- Contraste suficiente para segmentar cara/fondo sin contorno duro artificial.
- Sin clipping tonal en zonas densas.
- Sin desaparición de semitonos en zonas medias.

### 7.3 Detección de pérdida de volumen
Indicadores de fallo:

- regiones centrales convertidas en masa plana,
- periferia convertida en grano suelto,
- pérdida de gradiente continuo entre planos faciales.

### 7.4 Pruebas visuales conceptuales
- Comparativa lado a lado oscuro vs claro, misma pose y frame.
- Secuencias con giro suave de cabeza para verificar continuidad volumétrica.
- Pruebas de expresiones (boca/cejas) para confirmar que el tema no rompe legibilidad dinámica.
- Revisión en distintos niveles de escala (zoom) para detectar ruido o manchado emergente.

---

## Conclusión técnica
La migración correcta a fondo claro requiere una **recalibración perceptual integral** del mismo motor, no una inversión cromática literal. El sistema geométrico y de animación debe permanecer intacto; la adaptación vive en la capa de presentación perceptual (fondo, rango tonal, alpha/density e iluminación relativa). Con este enfoque, se preserva la identidad visual del avatar y su legibilidad tridimensional en ambos temas.
