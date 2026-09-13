# Inglés 3° de Secundaria — Libro Interactivo

Versión interactiva del libro de texto oficial **Libro Abierto** del Ministerio de Educación de la República Dominicana (MINERD) — Lenguas Extranjeras, Inglés 3° de Secundaria.

Cada página del libro se muestra tal como en el original (imágenes, diseño, iconos), con zonas de audio invisibles sobre todo el texto en inglés: al hacer clic se reproduce una grabación de voz neuronal (pre-generada, funciona sin conexión a internet). El texto en español (indicadores de logro, notas del Ministerio, etc.) no tiene audio.

## Cómo usarlo

Abre `index.html` con doble clic en cualquier navegador — no requiere instalación ni servidor.

- **Ver zonas de audio**: resalta en color todo el texto que tiene pronunciación, para mostrarlo en clase.
- Clic sobre cualquier frase en inglés para escucharla.
- Navegación por número de página o por unidad.

## Estructura

```
index.html       — visor
css/              — estilos
js/               — lógica del visor
data/pages.js     — texto e información de cada página
pages/            — cada página del libro, renderizada como imagen
audio/            — pronunciación pre-grabada (voz neuronal)
tools/build.py    — script para regenerar todo a partir del PDF original
```

## Créditos

Contenido educativo: Ministerio de Educación de la República Dominicana (MINERD), colección *Libro Abierto*, Serie 2 — [libroabierto.minerd.gob.do](https://libroabierto.minerd.gob.do). Uso educativo, sin fines de lucro.

Visor interactivo construido para el **Centro Educativo Salomé Ureña**.
