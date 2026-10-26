# Army Forge · Forja de Ejércitos

Constructor de listas de Warhammer 40,000 (11ª edición) con drag & drop, en español e inglés.
Es una web estática, sin dependencias ni paso de build.

```sh
./serve.sh          # http://localhost:8000
```

`serve.sh` arranca `server.py`, un servidor local en Python sin dependencias. Sirve la app y guarda cada ejército como un fichero JSON en `armies/<nombre>-<id>.json`. Si sirves la carpeta con otro servidor estático, las listas se guardan solo en el navegador.

La app carga cada facción solo cuando la necesita: la home, las de tus listas guardadas; el editor, la de su lista. El navegador reutiliza los ficheros que no han cambiado.

## Comprobaciones

```sh
.venv/bin/python tools/audit_units.py          # datasheets importados contra Wahapedia
python3 tools/check_app.py                     # cada vista de la app en Chrome headless, en español e inglés
```

Deben terminar con `0 errors` y `0 failures`. Ver [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md).

## Documentación

- [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md): proceso paso a paso para cargar un ejército nuevo.
- [docs/RECURSOS.md](docs/RECURSOS.md): webs, fuentes de datos, recursos oficiales y herramientas, y qué se ha sacado de cada uno.

## Funcionalidades

- Catálogo de unidades con imagen, filtros por rol y búsqueda. Arrastra una unidad al ejército o pulsa **+**.
- **Líderes y apoyo**: arrastra un personaje sobre una unidad y las unidades válidas se iluminan. También puedes usar el desplegable "Unir a…". Arrastrar un líder fuera de la unidad lo separa, y arrastrar una unidad al catálogo la borra. Los datasheets «SUPPORT» de la 11ª (Crypteks, Tenientes, Apotecarios…) ocupan su propio hueco: una unidad puede llevar su líder y además un apoyo.
- Tamaño de unidad, equipo (cambios de arma y armas especiales por cada 10 modelos), mejoras y Señor de la Guerra. Las opciones que dependen de otra («si lleva una pistola neovolkita…») salen desactivadas, con el motivo, mientras no se cumple la condición.
- Tamaño de batalla con un deslizador: Incursión (1000), Fuerza de Asalto (2000) o Embestida (3000). El límite de puntos es el del tamaño elegido.
- Destacamentos con sus Puntos de Destacamento (DP) según el tamaño de batalla. Si un destacamento da una habilidad a ciertos datasheets a cambio de puntos (las Ataduras Necrodérmicas de los C'tan en «Pantheon of Woe»), se aplica sola y se suma al coste de la unidad.
- Validación en vivo: límite de puntos, DP, límite de unidades (×2 para Battleline y Dedicated Transport), Héroes Épicos, número de mejoras, mejoras repetidas, una mejora por unidad combinada, líderes y apoyos válidos, un solo destacamento por etiqueta (SHIELD HOST, DYNASTY…) y Señor de la Guerra.
- Home con tus ejércitos guardados (puntos, validez, destacamentos y miniaturas) y un formulario para crear listas nuevas.
- **Vista de ejército** (`#/list/<id>/view`): todas las unidades con su equipo, atributos, mejoras y habilidades; los destacamentos con su regla, mejoras (y quién las lleva) y estratagemas; la regla de ejército y las estratagemas generales. Se puede imprimir.
- **Español e inglés**: el botón ES/EN cambia la interfaz y todo el contenido de juego (datasheets, armas, habilidades, equipo, reglas, mejoras y estratagemas). Las palabras clave en mayúsculas se quedan en inglés.
- Cada cambio se guarda automáticamente en `armies/*.json`. Desde la home puedes crear, importar, duplicar, exportar o borrar listas.

## Aspecto oficial

La interfaz usa recursos oficiales de Games Workshop, extraídos de los PDF de datasheets, del Index y del MFM, más las fuentes de Wahapedia. Es un proyecto personal y no comercial.
- `js/icons.js`: iconos vectoriales calcados de los PDF (arma a distancia y cuerpo a cuerpo, flecha de perfiles, emblema de Astra Militarum, Strategic Ploy y Battle Tactic). Usan `currentColor`, así que se colorean desde CSS.
- `assets/brand/`: logo de Warhammer 40,000, águila, ilustraciones del Index, textura de cabecera de datasheet y fondo de pergamino.
- `assets/fonts/`: Conduit ITC, la fuente de los datasheets.

## Estructura

```
data/
  editions/11th.json                 reglas de reclutamiento (tamaños de batalla, límites)
  factions/index.json                facciones disponibles (un capítulo lleva "parent": su facción base)
  factions/astra-militarum/
    faction.json                     regla de ejército, destacamentos y mejoras
    units.json                       datasheets (perfiles, palabras clave, equipo, líderes)
    weapons.json                     perfiles de armas
    points.json                      ← PUNTOS: lo único que cambia con cada MFM
    i18n.es.json                     traducción al español de los textos de la facción
  editions/11th.i18n.es.json         estratagemas Core, textos compartidos y glosario de reglas en español
i18n/es.json, i18n/en.json           textos de la interfaz
js/                                  código de la app (no contiene datos de juego)
```

### Actualizar puntos (nuevo Munitorum Field Manual)

Edita solo `data/factions/<facción>/points.json`. Las listas guardadas guardan IDs, no puntos, así que se recalculan solas.
Cuando hayas comprobado una unidad, añade su id a `verified` y desaparecerá el aviso `*`.

### Añadir una unidad

Las unidades se importan de Wahapedia, no se escriben a mano:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py astra-militarum Lord-Marshal-Dreir
.venv/bin/python tools/audit_units.py astra-militarum
```

Campos de cada unidad en `units.json` (los genera el importador):
- `weapons`: armas del datasheet con sus perfiles; `wargearAbilities`: habilidades ligadas a equipo.
- `sizes[].loadout`: equipo por defecto con cantidades para cada tamaño (`{"lascannon": 3, "gear:vox-caster": 1}`).
- `wargear`: opciones de equipo (`swap`, `pool`, `toggle`) con lo que sustituyen (`replaces`), lo que da cada elección (`packages`) y su máximo por tamaño (`maxBySize`). Descrito en `tools/wargear.py`.
- `leader.canLead`: ids de las unidades que puede liderar; `bodyguard`: límite de líderes (`{ "maxLeaders": 2, "maxWithKeyword": { "COMMAND SQUAD": 1 } }`).
- Imagen: la URL de la foto va en `images.json`, no en `units.json`. Sin imagen se muestra el emblema de la facción.

### Importar datasheets desde PDF (obsoleto)

`tools/import_datasheets.py` importaba los datasheets en PDF de la 10ª. Ya no se usa: todos los datasheets salen de Wahapedia (11ª). Se mantiene porque otros scripts usan sus utilidades.

### Datasheets de la 11ª desde Wahapedia

`tools/import_wahapedia_datasheets.py` añade o actualiza datasheets concretos a partir de sus páginas de Wahapedia (11ª edición): perfiles, armas, habilidades, equipo, a quién lidera y **puntos de la 11ª**, que se marcan como verificados.

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py astra-militarum Lord-Marshal-Dreir Centaur-RSV
```

En la 11ª algunas unidades cuestan más a partir de la tercera copia. Ese precio se guarda en `points.json` → `unitsExtraCopies`, y la app lo aplica sola: la unidad aparece marcada como «3.ª+ copia».

### Reglas y estratagemas (Wahapedia, 11ª)

`tools/import_wahapedia_rules.py` descarga de Wahapedia el texto completo de las reglas de destacamento y de las mejoras, las estratagemas de cada destacamento y las estratagemas generales (Core). No toca `faction.json`.

```sh
python3 tools/import_wahapedia_rules.py astra-militarum
```

Genera `data/factions/<facción>/rules.json`, `data/factions/<facción>/stratagems.json` y `data/editions/11th-stratagems.json`. Vuelve a ejecutarlo cuando GW publique erratas.

### Imágenes de unidades

Las fotos van siempre por URL, sin ficheros locales. Cada unidad busca su foto en este orden:
1. la que hayas subido tú en este navegador;
2. la URL de la tienda guardada en `data/factions/<facción>/images.json`;
3. el emblema de la facción.

Para rellenar `images.json`, usa `tools/store_images.py` (ver [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md)) o pega la URL en la ficha de la unidad (en warhammer.com: clic derecho sobre la foto → «Copiar dirección de imagen»).

### Añadir una facción

Sigue [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md): crear la facción desde Wahapedia, importar datasheets, reglas y estratagemas, sacar las fotos de la tienda y el emblema, y comprobarlo todo en la app.

## Estado de los datos

- **Facciones**: Astra Militarum (completa), Adeptus Custodes (27 datasheets, reglas, estratagemas, emblema y fotos de la tienda, de la 11ª), Tiránidos (50 datasheets, 10 destacamentos, emblema y 47 fotos), Caballeros Imperiales (18 datasheets, 8 destacamentos, emblema y 17 fotos) Imperio T'au (39 datasheets, 7 destacamentos, drones, emblema y 38 fotos), Necrones (51 datasheets, 12 destacamentos, emblema y 41 fotos) y Marines Espaciales: la base (67 datasheets genéricos, 16 destacamentos) y 11 capítulos que añaden lo suyo (Lobos Espaciales, Templarios Negros, Ángeles Sangrientos, Ángeles Oscuros, Deathwatch, Ultramarines, Puños Imperiales, Manos de Hierro, Guardia del Cuervo, Salamandras y Cicatrices Blancas). El objetivo es cargar todas las facciones siguiendo [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md).

- Datasheets: 416 unidades oficiales de la 11ª sacadas de Wahapedia (70 de Astra Militarum, 27 de Custodes, 50 de Tiránidos, 18 de Caballeros Imperiales, 39 del Imperio T'au, 51 de Necrones y 161 de Marines Espaciales: 67 genéricos y 94 de capítulos), auditadas con `tools/audit_units.py` (0 errores). Todos los textos de juego están en inglés y en español (traducción propia, no oficial; ver `tools/translations.py`). Las de Forge World y Warhammer Legends están excluidas (lista `excluded` en `units.json`) y el importador no las vuelve a meter.
- Imágenes: fotos de producto de la tienda de warhammer.com (URLs en `images.json`), sin ficheros locales.
- Reglas de reclutamiento, destacamentos y mejoras: 11ª edición (Wahapedia, pack de facción 11 / 2.8.1, octubre 2026).
- Puntos de unidades: los de la 11ª de cada datasheet de Wahapedia, todos verificados (sin `*`), incluido el sobrecoste por copias y los costes de equipo («per Lascannon: 5»), que se cobran por cada pieza que lleva la unidad.
- Los valores de Onslaught en `11th.json` no están confirmados.

Herramienta no oficial. Warhammer 40,000 es marca de Games Workshop.
