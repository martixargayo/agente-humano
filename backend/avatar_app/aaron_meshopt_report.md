# Informe técnico del avatar `aaron_meshopt.glb`

## Resumen de formato y dependencias
- Extensiones requeridas: `EXT_meshopt_compression`, `KHR_mesh_quantization`, `KHR_texture_basisu`. Extensión opcional usada: `KHR_materials_specular`.
- Sin animaciones embebidas; requiere animación externa (esqueleto o morph targets).
- Un único *scene* con 121 nodos y 12 mallas (todas con *skins*), 12 *skins* con 109 *joints* cada una (esqueleto completo compatible con animación CC5).

## Mallas y objetivos de morph (blendshapes)
| Malla | Objetivos total | Nombres de objetivos |
| --- | --- | --- |
| Brows | 1 191 | 397 |
| CC_Base_Body | 2 130 | 355 |
| CC_Base_Eye | 36 | 9 |
| CC_Base_EyeOcclusion | 774 | 387 |
| CC_Base_TearLine | 784 | 392 |
| CC_Base_Teeth | 8 | 4 |
| CC_Base_Tongue | 33 | 33 |
| Classic_Slick_Back (pelo) | 794 | 397 |
| Eyelash_Low | 397 | 397 |
| Eyelash_Up | 397 | 397 |
| RS_Regular_Fit_Shirt | 36 | 36 |
| Stubble (barba) | 397 | 397 |

- Total de nombres de morph distintos: 530.
- Distribución por tipo (detectada por prefijos): ~128 de boca, 46 de TearLine, 40 de ojo, 20 de lengua, 16 *visemes* (V_*), 15 cuello, 14 mandíbula, 12 nariz, 12 dientes, además de ~117 controles de ropa (prefijo `C`/ajustes de camisa) y variaciones de cejas/pestañas/pelo.
- *Visemes* disponibles: `V_Affricate`, `V_Dental_Lip`, `V_Explosive`, `V_Lip_Open`, `V_None`, `V_Open`, `V_Tight`, `V_Tight_O`, `V_Tongue_Curl_D`, `V_Tongue_Curl_U`, `V_Tongue_Lower`, `V_Tongue_Narrow`, `V_Tongue_Out`, `V_Tongue_Raise`, `V_Tongue_up`, `V_Wide`.

## Materiales y transparencia
- 22 materiales en total; 12 usan `alphaMode: BLEND` y todos son *double-sided*.
- Materiales translúcidos: `Brows_Hair_Transparency`, `Brows_Color_Transparency`, `Brows_Base_Transparency`, `Std_Eyelash`, `Std_Eye_R`, `Std_Cornea_R`, `Std_Eye_L`, `Std_Eye_Occlusion_R`, `Hair_Transparency`, `Hair_Clap_Transparency`, `Eyelash_Low_Transparency`, `Beard_Transparency`.
- Posibles artefactos de pelo/barba/cejas con “baja opacidad”: el modo `BLEND` y doble cara requieren orden de renderizado correcto y activar *alpha to coverage* o *depth sorting* en el motor para evitar que se vean demasiado transparentes.

## Posibilidades de animación
- **Labios y habla**: 16 visemes + 128 morphs de boca/labios y 20 de lengua permiten *lip-sync* fino (combinando visemas con ajustes de lengua y mandíbula). No hay animación pregrabada, por lo que el motor debe aplicar los valores de morphs por clave temporal.
- **Microexpresiones y espera**: hay abundantes morphs de cejas, ojos, párpados y tearline (más de 700 combinados) que sirven para parpadeo aleatorio, miradas y micro-tensiones durante estados de reposo.
- **Estados emocionales**: los morphs de boca (sonrisa, comisuras), cejas (subir/bajar/lateral) y nariz/cheeks permiten construir *blend trees* para felicidad/enfado/sorpresa. Se pueden modular durante el habla sumando valores a los visemes.
- **Cuerpo y ropa**: morphs de cuello (15), postura de mandíbula/cuello/cabeza (p. ej. `Neck_*`, `Head_*`) y ~117 ajustes de camisa/cuellos/puños/hemline permiten deformaciones secundarias al animar cuerpo o respiración.
- **Rig esquelético**: 12 *skins* sobre el mismo conjunto de 109 *joints* facilitan usar un solo *AnimationClip* para todo el avatar (cuerpo, ropa, pelo, barba), con opción de combinar animación esquelética (poses corporales) y morphs faciales.

## Recomendaciones de uso
- **Carga**: habilitar soporte de `EXT_meshopt_compression` y texturas BasisU; desactivar *frustum culling* parcial hasta verificar que las mallas con alpha no se recorten.
- **Lip-sync realista**: mapear fonemas → visemes (`V_*`) y añadir microvariaciones de `Mouth_*`, `Tongue_*`, `Jaw_*` para enfatizar consonantes/vocales. Mezclar con *easing* suave para evitar popping.
- **Idle “vivo”**: programar un *state machine* que, en reposo, module levemente `Eye_Blink_*`, `Eye_Look_*`, `Brow_*` y `Mouth_Slight*` con ruido Perlin o curvas lentas.
- **Emociones al hablar**: aplicar capas aditivas de morphs (ej. `Mouth_Smile_*` + `Brow_Down_*` para enfado controlado) sobre el valor base del viseme actual; limitar suma al 0–1 y restaurar al final de cada frase.
- **Transparencias de pelo/barba**: ordenar render de mallas alpha después de las opacas, usar *alpha to coverage* si el motor lo soporta, y probar con *dithered transparency* para evitar halos.

## Sistema propuesto para hablar y expresarse de forma ultra realista

### Capas y entradas
- **Entrada de audio o texto**: fonemas temporizados (voz sintetizada o audio real con *forced alignment*) + marcadores de intensidad (volumen, energía) y prosodia (pitch/ritmo).
- **Contexto emocional**: estado discreto (feliz, neutral, enfadado, triste, sorprendido) + escala continua de valencia/arousal (−1 a 1) para modular amplitud y velocidad de morphs.
- **Estado corporal**: pose esquelética base (idle/locomoción) que aporta sutiles movimientos de cabeza/cuello; respiración opcional ligada a ciclo de animación.

### Pipeline de animación facial
1. **Generador de visemas**
   - Mapea fonemas a los 16 `V_*` del avatar.
   - Ajusta el *timing* con *lookahead* para anticipar consonantes o cierres de mandíbula.
   - Usa curvas de entrada/salida (ease-in/out) de 60–120 ms para evitar pasos bruscos entre visemas rápidos.

2. **Coarticulación y lengua**
   - Aplica *coarticulation blending* mezclando el viseme actual con el anterior/siguiente (ratio 0.2–0.4) para vocales largas.
   - Añade targets de lengua (`V_Tongue_*` + `Tongue_*`) sincronizados: protrusión para /th/, elevación para /l/ y estrechamiento para /s/.
   - Varía la amplitud según energía de audio: mayor apertura mandibular en sílabas acentuadas.

3. **Capa de expresividad emocional**
   - Define plantillas por emoción: p. ej., **feliz** (`Mouth_Smile_*`, `Cheek_Raise_*`, `Brow_Inner_Up`), **enfadado** (`Brow_Down_*`, `Nose_Sneer_*`, cierre mandibular), **triste** (comisuras caídas, párpados semi-cerrados).
   - Aplica las plantillas como curva lenta (300–700 ms) sobre la señal de visemas, escalada por la valencia/arousal.
   - Añade micro-asimetría (10–20 %) alternando lado izquierdo/derecho para evitar simetría perfecta.

4. **Microexpresiones y living idle**
   - Ejecuta un *scheduler* que lanza eventos pseudoaleatorios: parpadeo (`Eye_Blink_*`), micro-movimientos de ojos (`Eye_Look_*`), *saccades*, tensión leve de cejas (`Brow_*`), respiración ligera con `Neck_*`/`Head_*`.
   - En modo espera: amplitudes bajas (0.05–0.12) y periodos de 3–6 s con ruido Perlin para suavidad.
   - Durante habla: sincroniza parpadeos con pausas y caídas de energía, y agrega acentos faciales al inicio de frases.

5. **Resolver y clamping**
   - Suma capas (visema + coarticulación + emoción + microexpresión) y hace *clamp* 0–1 por target.
   - Prioriza cierres (p. ej., labio cerrado) sobre aperturas de emoción para evitar penetraciones.
   - Aplica *low-pass* (filtro exponencial) a todos los canales a 60–90 Hz para suprimir jitter.

### Esqueleto y movimientos secundarios
- **Cabeza/cuello**: usa `Head_*` y `Neck_*` (15 targets) como *additive layer* para acompañar la prosodia (cabeceo leve en sílabas fuertes, negación/afirmación sutil).
- **Respiración**: modula escala torácica o ligeros offsets de cuello/clavículas sincronizados a un LFO; incrementa frecuencia bajo arousal alto.
- **Ropa/pelo/barba**: si el motor permite físicas, activa *cloth/hair simulation*; si no, usa morphs de camisa (`C*`) y huesos del pelo para añadir *secondary motion* que reaccione al movimiento de cabeza.

### Lógica de estados
- **Idle vivo**: máquina de estados con “Quiet”, “Alert”, “Thinking”; cada uno ajusta tasa de parpadeo, amplitud de ojos/cejas y respiración. Transiciones suaves de 0.5–1 s.
- **Habla con emoción**: estado “Speech” con subestados por emoción; la emoción se interpola gradualmente desde el estado previo. Se fuerza coherencia: no mezclar plantillas incompatibles (p. ej., sonrisa amplia + ceño extremo sin atenuar).
- **Eventos externos**: gatillar *emphasis hits* (subir cejas + ligera apertura mandibular) en palabras clave o picos de energía.

### Herramientas y datos recomendados
- **Driver de audio → visema**: Silero VAD + Montreal Forced Aligner o servicio TTS que devuelva marcas de tiempo de fonemas.
- **Runtime**: sistema de *blend trees* con capas aditivas y pesos por emoción; *pose caches* para visemas recurrentes (p, b, m, f, v) para reducir CPU.
- **Edición**: exponer *profiles* por emoción y por idioma para ajustar amplitud/duración de visemas según fonética (español vs. inglés).

### Validación y viabilidad
- El número y variedad de morphs (530 nombres, con 128 de boca y 20 de lengua) permiten cubrir visemas complejos, coarticulación y expresividad simultánea sin necesidad de capturas faciales externas.
- El rig de 109 joints más morphs de ropa/pelo habilita movimientos secundarios y acompañamiento corporal que refuerza la naturalidad durante el habla.
- Requisito clave: motor debe soportar **morph blending** en múltiples capas, resolución a 60 fps y buen manejo de transparencias para pelo/barba; de cumplirse, el pipeline anterior es viable en tiempo real.

