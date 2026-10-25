# Cargar una facción nueva

Proceso para añadir un ejército nuevo (por ejemplo Adeptus Custodes) con datos de la 11ª edición. Se ha probado de principio a fin con Adeptus Custodes: 27 datasheets oficiales, 13 destacamentos con sus estratagemas, emblema y 26 fotos de la tienda.

Tiempo aproximado: 10–15 minutos, la mayor parte esperando a las descargas y revisando.

## 0. Preparación (solo la primera vez)

```sh
/usr/bin/python3 -m venv .venv
.venv/bin/pip install -r tools/requirements.txt
```

Necesitas tres datos de la facción:

| Dato | Dónde | Ejemplo (Custodes) |
|---|---|---|
| Identificador de Wahapedia | URL de la facción en Wahapedia | `adeptus-custodes` (de `wahapedia.ru/wh40k11ed/factions/adeptus-custodes/`) |
| Página de la tienda (en inglés) | warhammer.com → Warhammer 40,000 → facción | `https://www.warhammer.com/en-GB/shop/warhammer-40000/armies-of-the-imperium/adeptus-custodes` |
| Carpeta del Drive (opcional, para el emblema) | Carpeta compartida → facción | `Imperium/Adeptus Custodes` |

El identificador de Wahapedia es también el `id` de la facción en la app y el nombre de su carpeta en `data/factions/`.

## 1. Crear la facción

```sh
python3 tools/bootstrap_faction.py adeptus-custodes --color "#b8923a"
```

Crea `data/factions/adeptus-custodes/` con:
- `faction.json`: regla de ejército, destacamentos (coste en DP, regla resumida) y mejoras con sus requisitos;
- `units.json`, `weapons.json`, `points.json` (con los puntos de las mejoras) e `images.json`.

Además la añade a `data/factions/index.json`. `--color` es el color de la facción en las tarjetas de la home.

**Revisa `faction.json`:**
- **`requires` de cada mejora**: palabras clave que debe tener la unidad, deducidas del texto «X model only». Si sale `[]`, cualquier personaje (no Héroe Épico) puede llevarla. Corrige los casos dudosos. Ejemplo: `[["INFANTRY", "OFFICER"]]` exige las dos palabras clave; `[["A"], ["B"]]` significa A **o** B.
- **`type: "upgrade"`**: se marca solo en las mejoras etiquetadas como UPGRADE. Pueden llevarlas unidades que no son personajes y no cuentan para el límite de mejoras.
- **Nombres en español**: pon `name.es` en la facción y en los destacamentos que quieras traducir.
- **Mecánicas propias de la facción**: la regla de ejército solo se muestra como texto. Las órdenes de Astra Militarum (`armyRule.orders`) son un caso especial escrito a mano; otras facciones no lo necesitan.

## 2. Importar los datasheets

Primero mira la clasificación:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes --list
```

Recorre todos los datasheets enlazados desde la página de la facción y clasifica cada uno según su propia página: **CORE** (oficiales), **LEGENDS** o **FW** (Forge World), mirando el logo del datasheet. Tarda medio segundo por página. Después importa todas las oficiales:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes --all
```

Por cada unidad guarda:
- perfiles, armas (con sus perfiles y reglas) y equipo por defecto;
- habilidades (CORE, de facción, propias y de equipo), regla de dañado y órdenes;
- opciones de equipo: como texto, y además como selectores cuando el patrón es reconocible;
- composición, a quién lidera y límite de líderes;
- **puntos de la 11ª**, que se marcan como verificados. Si el datasheet tiene el sobrecoste de la 3.ª copia, va a `points.json` → `unitsExtraCopies`.

Las unidades de Legends y Forge World se apuntan en `units.json` → `excluded` y nunca se importan.

**Revisa la salida.** Cada línea muestra el rol, los perfiles, las armas, las opciones de equipo (convertidas a selector / total), a quién lidera y los puntos.
- **`lead=None` en un personaje**: el nombre de la unidad a la que lidera no coincide con el nuestro. Añade el alias en `by_name.update({...})` dentro de `import_wahapedia_datasheets.py` y vuelve a ejecutar.
- **`skip X: could not parse`**: la página tiene un formato distinto. Ábrela en Wahapedia y ajusta el parser o crea esa unidad a mano.
- **Rol incorrecto**: se calcula a partir de las palabras clave, en este orden: FORTIFICATION, CHARACTER, BATTLELINE, AIRCRAFT, TITANIC, TRANSPORT, VEHICLE, MOUNTED y, si no, infantry.

Para añadir o actualizar unidades sueltas más adelante:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes Blade-Champion Trajann-Valoris
```

## 3. Reglas completas y estratagemas

```sh
python3 tools/import_wahapedia_rules.py adeptus-custodes
```

Genera:
- `rules.json`: texto completo de la regla de cada destacamento y de cada mejora;
- `stratagems.json`: estratagemas por destacamento;
- `data/editions/11th-stratagems.json`: las Core, comunes a todas las facciones.

Todo se ve en la **vista de ejército**. Comprueba que cada destacamento muestre `enhancements` y `stratagems`. Si alguno sale a 0, su nombre en Wahapedia no coincide con el de `faction.json`.

## 4. Fotos de la tienda

```sh
.venv/bin/python tools/store_images.py adeptus-custodes \
  https://www.warhammer.com/en-GB/shop/warhammer-40000/armies-of-the-imperium/adeptus-custodes
```

1. Se abre una ventana de Chrome con un perfil temporal.
2. Si aparece la verificación humana (captcha), resuélvela en esa ventana.
3. Cuando veas los productos, pulsa **Enter** en la terminal.
4. El script pulsa "Show more" hasta cargar todo y guarda la lista en `adeptus-custodes-products.json`, que puedes reutilizar con `--products`.
5. Empareja productos y unidades por nombre y escribe en `images.json` los que coinciden.

**Revisa el resultado.** El emparejamiento es por palabras del nombre: con Astra Militarum acertó 52 de 53.
- **Unidades sin imagen**: suelen ser variantes que comparten caja (los 7 Leman Russ, Comandantes, unidades de Ogretes…). Añádelas a mano en `images.json` copiando la URL del kit, o desde la app: ficha de la unidad → **Imagen de la tienda (URL)**.
- **Coincidencias dudosas**: comprueba sobre todo las unidades con nombres genéricos (p. ej. "Heavy Weapons Squad").
- Con `--products <facción>-products.json` puedes repetir el emparejamiento sin volver a abrir la tienda (por ejemplo, tras importar unidades nuevas).
- Usa la tienda en **inglés** (`en-GB`): con nombres en español se emparejan muchas menos.

## 5. Emblema de la facción (opcional)

Sin emblema propio, la app usa el de Astra Militarum. Para sacar el oficial de cualquier datasheet en PDF de la facción:

```sh
# descargar la carpeta de la facción (o un solo PDF desde el navegador)
python3 tools/download_drive_folder.py <id-de-la-carpeta-de-drive> pdfs/adeptus-custodes

# trazar el emblema de la barra de palabras clave (misma posición en todos los datasheets)
.venv/bin/python tools/pdf_vector_icon.py "pdfs/adeptus-custodes/Characters/BLADE CHAMPION.pdf" 0 \
  data/factions/adeptus-custodes/emblem.svg --bbox 290,295,362,357 --mono
```

El id de la carpeta es la última parte del enlace de Drive. Si el resultado no es el emblema, usa `--list` para ver los dibujos de la página con sus coordenadas y elige por `--ids`.

La app usa el emblema en la cabecera, los títulos, las fichas, los placeholders de unidades sin foto y la tarjeta de la home.

## 6. Comprobar en la app

```sh
./serve.sh
```

- [ ] La facción aparece en **Nueva lista** y se puede crear una lista.
- [ ] El catálogo muestra todas las unidades, con foto y puntos sin `*`.
- [ ] Un personaje se puede unir a las unidades que indica su datasheet, y **Líderes n/m** respeta el límite.
- [ ] Al elegir un destacamento, sus mejoras aparecen solo en los personajes que cumplen el requisito.
- [ ] En la **vista de ejército** se ven la regla del destacamento, las mejoras, las estratagemas y las Core.
- [ ] Una tercera copia de una unidad con sobrecoste sale marcada como «3.ª+ copia» con el precio más alto.
- [ ] La consola del navegador no muestra errores.

## Mantenimiento

| Cuando… | Haz… |
|---|---|
| Sale un MFM nuevo | Edita `points.json` o reimporta los datasheets afectados (`import_wahapedia_datasheets.py <facción> <Datasheet>…`) |
| GW publica erratas de reglas o estratagemas | `import_wahapedia_rules.py <facción>` |
| Sale una unidad nueva | `import_wahapedia_datasheets.py <facción> <Datasheet>` y `store_images.py … --products <lista guardada>`, o la URL a mano |
| Quieres excluir una unidad | Añade su id a `units.json` → `excluded.ids` y bórrala de `units`, `points.json` e `images.json` |

## Problemas conocidos

- **Pillow no se instala**: estás usando PyPy. Crea el entorno con `/usr/bin/python3`.
- **`202` o "Human Verification" en la tienda**: es la protección anti-bots. Usa `store_images.py`, que abre una ventana visible, y no Chrome headless.
- **Wahapedia cambia su HTML**: los importadores dependen de sus clases CSS (ver [RECURSOS.md](RECURSOS.md)). Si fallan tras un cambio, hay que ajustar las expresiones regulares.
- **Opciones de equipo complejas** (paquetes de varias armas, equipo que no es arma): se ven como texto en la ficha, pero no tienen selector.
- **Traducciones**: los textos de reglas se importan en inglés.
