# Recursos y referencias

Fuentes de datos, webs y recursos usados para construir Forja de Ejércitos, y qué se ha sacado de cada uno.

> Proyecto personal y no comercial (trabajo de universidad). Warhammer 40,000, sus logos, ilustraciones, fotos de producto y textos de reglas son propiedad de Games Workshop.

## Webs de referencia

| Recurso | URL | Para qué lo usamos |
|---|---|---|
| Wahapedia: reglas básicas (11ª) | https://wahapedia.ru/wh40k11ed/the-rules/core-rules/ | Reglas de reclutamiento (tamaños de batalla, puntos de destacamento, límites de unidades y mejoras, líderes) y **estratagemas generales (Core)** |
| Wahapedia: página de facción (11ª) | `https://wahapedia.ru/wh40k11ed/factions/<facción>/`<br>p. ej. [astra-militarum](https://wahapedia.ru/wh40k11ed/factions/astra-militarum/) | Regla de ejército, destacamentos (coste en DP, regla, mejoras, estratagemas) e índice de datasheets con su clasificación (oficial, Legends o Forge World) |
| Wahapedia: datasheet (11ª) | `https://wahapedia.ru/wh40k11ed/factions/<facción>/<Datasheet>`<br>p. ej. [Lord-Marshal-Dreir](https://wahapedia.ru/wh40k11ed/factions/astra-militarum/Lord-Marshal-Dreir) | Perfiles, armas, habilidades, equipo, líderes y **puntos de la 11ª**, incluido el sobrecoste a partir de la 3.ª copia |
| Munitorum Field Manual (MFM) | https://mfm.warhammer-community.com/en | Fuente oficial de puntos; cambia con cada ajuste de balance. Sirve para verificar `points.json` a mano |
| Tienda de Warhammer | `https://www.warhammer.com/en-GB/shop/warhammer-40000/<grupo>/<facción>`<br>p. ej. [Astra Militarum (es-ES)](https://www.warhammer.com/es-ES/shop/warhammer-40000/armies-of-the-imperium/astra-militarum) | Fotos de producto de cada unidad (`images.json`) |
| New Recruit | https://www.newrecruit.eu/ | Referencia funcional de constructor de listas (muy completo, pero con mala experiencia de uso) |
| Warhammer Community | https://www.warhammer-community.com/ | Novedades, reglas y FAQ oficiales |

### Notas sobre cada web

- **Wahapedia** sirve las páginas a peticiones directas. Los importadores esperan 0,5 s entre páginas para no saturarla. Su HTML puede cambiar; si un importador deja de reconocer algo, revisa las clases CSS (`dsOuterFrame`, `dsWeaponRow`, `str11Wrap`, `EnhancementsPts`…).
- **La tienda de Warhammer** tiene protección anti-bots: a `curl` responde `202` sin contenido y a Chrome headless le muestra una página de *Human Verification*. Hay que abrirla en una ventana de Chrome visible (`tools/store_images.py` lo hace solo). Las **imágenes** sí se pueden enlazar directamente:
  `https://www.warhammer.com/app/resources/catalog/product/920x950/<código>_<Nombre>.jpg?fm=webp&w=480&h=495`
  (con `w=480` ocupan unos 30 KB).
- **El MFM** se publica como web/PDF; no hay importador automático. Los puntos de la 11ª que trae Wahapedia en cada datasheet suelen coincidir con el MFM vigente.

## Carpeta compartida de Google Drive (PDF oficiales)

https://drive.google.com/drive/folders/11h099eTJtxY0yShZ8wcGNpngwmo8b0f3

Es pública ("cualquiera con el enlace"), así que se puede listar y descargar sin iniciar sesión (`tools/download_drive_folder.py`). Estructura:

```
Imperium/ · Chaos/ · Xenos/ · Titans/        facciones, una carpeta cada una
  Astra Militarum/
    Characters/ Infantry/ Vehicles/ Leman Russ's/ Baneblades/
    Imperial Armor/                           Forge World: no se usa
    index.pdf                                 Index de la 10ª (2023): regla de ejército, destacamento, ilustraciones
    ADSE.pdf                                  resumen de regla de ejército y destacamento
PointsV1.1.pdf                                MFM v1.1 (2023), desfasado
Core Rules/                                   vacía
pdf_mod_w40k.py / .txt                        script del autor de la carpeta (no usado)
```

Cada datasheet es un PDF de 2 páginas con formato de la **10ª edición (codex 2023)**:
- Página 1: atributos, armas, habilidades y palabras clave. Lleva fotos de las miniaturas (no se usan: la app usa las de la tienda) y el emblema de facción en vector, en la barra inferior, aprox. en `bbox 290,300,362,357`.
- Página 2: opciones de equipo, composición, a quién lidera, transporte y trasfondo.

## Qué hemos sacado de cada fuente

| Dato o recurso | Fuente | Dónde está en el proyecto |
|---|---|---|
| Reglas de reclutamiento de la 11ª | Wahapedia (core rules) | `data/editions/11th.json` |
| Estratagemas generales | Wahapedia (core rules) | `data/editions/11th-stratagems.json` |
| Regla de ejército y destacamentos (resumen) | Wahapedia (facción) | `data/factions/<f>/faction.json` |
| Texto completo de reglas de destacamento y mejoras | Wahapedia (facción) | `data/factions/<f>/rules.json` |
| Estratagemas de destacamento | Wahapedia (facción) | `data/factions/<f>/stratagems.json` |
| Datasheets de todas las facciones (11ª) | Wahapedia (datasheets) | `data/factions/<f>/units.json` |
| Puntos (y sobrecoste por copias) | Wahapedia (11ª, verificados) | `data/factions/<f>/points.json` |
| Fotos de unidades | Tienda de Warhammer | `data/factions/<f>/images.json` (URLs) |
| Iconos (arma a distancia, cuerpo a cuerpo, flecha de perfil, Strategic Ploy, Battle Tactic, emblema AM) | Vectores de los PDF (datasheet e Index) | `js/icons.js` |
| Emblema de cada facción (opcional) | Vectores del PDF de la facción | `data/factions/<f>/emblem.svg` |
| Logo de Warhammer 40,000 | Portada del MFM v1.1 | `assets/brand/wh40k-logo.webp` |
| Águila, ilustraciones (Cadia, guardia), banner de batalla | Index de Astra Militarum | `assets/brand/` |
| Textura de cabecera de datasheet y pergamino | Fondos de los PDF de datasheet | `assets/brand/datasheet-header.webp`, `parchment.webp` |
| Fuente Conduit ITC (tipografía de los datasheets) | Wahapedia (`/wh40k10ed/fonts/`) | `assets/fonts/` |

## Herramientas (`tools/`)

Dependencias: `tools/requirements.txt`. Usa **CPython** (`/usr/bin/python3`), porque Pillow no compila con PyPy:

```sh
/usr/bin/python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
```

| Script | Qué hace | Fuente |
|---|---|---|
| `bootstrap_faction.py` | Crea la carpeta de una facción nueva: regla de ejército, destacamentos, mejoras y ficheros vacíos. La registra en `index.json` | Wahapedia (facción) |
| `import_wahapedia_datasheets.py` | Importa datasheets de la 11ª (`--all` para todos los oficiales; Legends y FW van a `excluded`) con sus puntos | Wahapedia (datasheets) |
| `wargear.py` | Motor de equipo: modelos por tipo y tamaño, equipo por defecto con cantidades y opciones de equipo como selectores | (usado por el importador) |
| `audit_units.py` | Compara cada unidad importada con su datasheet y avisa de armas, habilidades u opciones mal leídas | Caché de Wahapedia |
| `translations.py` | Lista los textos de juego sin traducir (`pending`) y guarda las traducciones (`apply`) en los `i18n.es.json` | Datos importados |
| `wahapedia_fetch.py` | Descarga con caché local (`.cache/wahapedia/`) para los importadores | Wahapedia |
| `import_wahapedia_rules.py` | Textos completos de reglas y mejoras, estratagemas de destacamento y Core | Wahapedia |
| `store_images.py` | Abre la tienda en Chrome, recoge los productos y asigna fotos a las unidades | warhammer.com |
| `download_drive_folder.py` | Descarga una carpeta pública de Drive | Google Drive |
| `import_datasheets.py` | **Obsoleto**: importaba datasheets desde los PDF (formato 10ª). Ya no se usa para los datos; sus utilidades (`role_of`, `slug`) las usan los demás scripts | PDF de Drive |
| `pdf_vector_icon.py` | Convierte dibujos vectoriales de un PDF en SVG (iconos y emblemas) | PDF de Drive |

`server.py` (en la raíz) es el servidor local: sirve la app, guarda los ejércitos en `armies/*.json` y las URLs de imágenes en `images.json`.

## Estado y salvedades de los datos

- **Edición**: todo es de la 11ª, sacado de Wahapedia: reglas de reclutamiento, destacamentos, mejoras, estratagemas y los datasheets de todas las facciones. Los PDF de Drive solo se usan para los iconos, el emblema y las ilustraciones.
- **Puntos**: los de la 11ª de cada datasheet de Wahapedia, todos verificados. Conviene contrastarlos con el MFM vigente cuando salga uno nuevo. Los costes de equipo («per Lascannon: 5») se cobran por cada pieza que lleve la unidad, también la de serie: es la lectura literal de Wahapedia y conviene confirmarla con el MFM.
- **Onslaught**: sus valores en `11th.json` están sin confirmar.
- **Excluido**: Forge World, Warhammer Legends y Boarding Actions.
- **Idioma**: la interfaz y todo el contenido de juego están en español e inglés. Los textos se importan en inglés y la traducción al español es propia, no oficial, con la terminología de GW. Las palabras clave en mayúsculas se dejan en inglés.
