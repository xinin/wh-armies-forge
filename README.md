# Army Forge · Forja de Ejércitos

Constructor de listas de Warhammer 40,000 (11ª edición) con drag & drop, en español e inglés.
Es una web estática, sin dependencias ni paso de build.

```sh
./serve.sh          # http://localhost:8000
```

`serve.sh` arranca `server.py`, un servidor local en Python sin dependencias. Sirve la app y guarda cada ejército como un fichero JSON en `armies/<nombre>-<id>.json`. Si sirves la carpeta con otro servidor estático, las listas se guardan solo en el navegador.

## Documentación

- [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md): proceso paso a paso para cargar un ejército nuevo.
- [docs/RECURSOS.md](docs/RECURSOS.md): webs, fuentes de datos, recursos oficiales y herramientas, y qué se ha sacado de cada uno.

## Funcionalidades

- Catálogo de unidades con imagen, filtros por rol y búsqueda. Arrastra una unidad al ejército o pulsa **+**.
- **Líderes**: arrastra un personaje sobre una unidad y las unidades válidas se iluminan. También puedes usar el desplegable "Unir a…". Arrastrar un líder fuera de la unidad lo separa, y arrastrar una unidad al catálogo la borra.
- Tamaño de unidad, equipo (cambios de arma y armas especiales por cada 10 modelos), mejoras y Señor de la Guerra.
- Destacamentos con sus Puntos de Destacamento (DP) según el tamaño de batalla.
- Validación en vivo: límite de puntos, DP, límite de unidades (×2 para Battleline y Dedicated Transport), Héroes Épicos, número de mejoras, mejoras repetidas, una mejora por unidad combinada, líderes válidos y Señor de la Guerra.
- Home con tus ejércitos guardados (puntos, validez, destacamentos y miniaturas) y un formulario para crear listas nuevas.
- **Vista de ejército** (`#/list/<id>/view`): todas las unidades con su equipo, atributos, mejoras y habilidades; los destacamentos con su regla, mejoras (y quién las lleva) y estratagemas; la regla de ejército y las estratagemas generales. Se puede imprimir.
- Cada cambio se guarda automáticamente en `armies/*.json`. Desde la home puedes duplicar, exportar, importar o borrar listas, y desde el editor copiar la lista como texto.

## Aspecto oficial

La interfaz usa recursos oficiales de Games Workshop, extraídos de los PDF de datasheets, del Index y del MFM, más las fuentes de Wahapedia. Es un proyecto personal y no comercial.
- `js/icons.js`: iconos vectoriales calcados de los PDF (arma a distancia y cuerpo a cuerpo, flecha de perfiles, emblema de Astra Militarum, Strategic Ploy y Battle Tactic). Usan `currentColor`, así que se colorean desde CSS.
- `assets/brand/`: logo de Warhammer 40,000, águila, ilustraciones del Index, textura de cabecera de datasheet y fondo de pergamino.
- `assets/fonts/`: Conduit ITC, la fuente de los datasheets.

## Estructura

```
data/
  editions/11th.json                 reglas de reclutamiento (tamaños de batalla, límites)
  factions/index.json                facciones disponibles
  factions/astra-militarum/
    faction.json                     regla de ejército, destacamentos y mejoras
    units.json                       datasheets (perfiles, palabras clave, equipo, líderes)
    weapons.json                     perfiles de armas
    points.json                      ← PUNTOS: lo único que cambia con cada MFM
i18n/es.json, i18n/en.json           textos de la interfaz
js/                                  código de la app (no contiene datos de juego)
```

### Actualizar puntos (nuevo Munitorum Field Manual)

Edita solo `data/factions/<facción>/points.json`. Las listas guardadas guardan IDs, no puntos, así que se recalculan solas.
Cuando hayas comprobado una unidad, añade su id a `verified` y desaparecerá el aviso `*`.

### Añadir una unidad

1. Añade el datasheet en `units.json`. Los textos van como `{ "en": "...", "es": "..." }`.
2. Añade sus puntos en `points.json` → `units.<id>`.
3. Si usa armas nuevas, añádelas a `weapons.json`.

Campos útiles:
- `leader.canLead`: ids de las unidades que puede liderar.
- `bodyguard`: `{ "maxLeaders": 2, "maxWithKeyword": { "COMMAND SQUAD": 1 } }`.
- `wargear`: opciones de tipo `swap` (sustituir un arma), `pool` (hasta `max` armas cada `per` modelos) y `toggle`.
- Imagen: la URL de la foto va en `images.json` (no en `units.json`). Sin imagen se muestra el emblema de la facción.

### Importar datasheets desde PDF

`tools/import_datasheets.py` lee los datasheets en PDF (uno por unidad, formato de 10ª) y regenera `units.json`. Saca perfiles, armas, habilidades, opciones de equipo (las interactivas se generan solas), composición, líderes y transporte. No extrae fotos: las imágenes van siempre por URL.

```sh
/usr/bin/python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/import_datasheets.py <carpeta-pdfs> astra-militarum \
  --points PointsV1.1.pdf --skip "Infantry Squad,Platoon Command Squad"
```

El importador conserva lo editado a mano: nombres en español, `bodyguard` y `orders`. Las unidades sin PDF no se tocan. Con `--points`, las unidades nuevas sin entrada en `points.json` toman los puntos de ese MFM.

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

- **Facciones**: Astra Militarum (completa) y Adeptus Custodes (27 datasheets, reglas, estratagemas, emblema y fotos de la tienda, de la 11ª) y Tiránidos (50 datasheets, 10 destacamentos, emblema y 47 fotos). El objetivo es cargar todas las facciones siguiendo [docs/NUEVA-FACCION.md](docs/NUEVA-FACCION.md).

- Datasheets: 70 unidades oficiales. 59 vienen de los PDF de la carpeta compartida (formato de la 10ª, codex 2023) y 11 de Wahapedia (11ª): Commissar Graves (vehículo y a pie), Lord Marshal Dreir, Centaur RSV, Hippogriff AFV, Krieg Combat Engineers, Krieg Heavy Weapons Squad, Artillery Team, Cadian Recon Squad, Catachan Heavy Weapons Squad y Tempestus Aquilons. Los textos de reglas están en inglés. Las de Forge World y Warhammer Legends están excluidas (lista `excluded` en `units.json`) y el importador no las vuelve a meter.
- Imágenes: fotos de producto de la tienda de warhammer.com (URLs en `images.json`), sin ficheros locales.
- Reglas de reclutamiento, destacamentos y mejoras: 11ª edición (Wahapedia, pack de facción 11 / 2.8.1, octubre 2026).
- Puntos de unidades: solo **Cadian Shock Troops** está verificado con la 11ª. El resto son estimaciones (las unidades nuevas toman el MFM 1.1 de 2023) y hay que contrastarlas con el MFM actual.
- Los valores de Onslaught en `11th.json` no están confirmados.

Herramienta no oficial. Warhammer 40,000 es marca de Games Workshop.
