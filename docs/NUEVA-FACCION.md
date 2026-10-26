# Cargar una facción nueva

Proceso para añadir un ejército nuevo (por ejemplo Adeptus Custodes) con datos de la 11ª edición. Se ha probado de principio a fin con Adeptus Custodes: 27 datasheets oficiales, 13 destacamentos con sus estratagemas, emblema y 26 fotos de la tienda.

Tiempo aproximado: 10–15 minutos, la mayor parte esperando a las descargas y revisando, más la traducción al español (paso 6).

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

Además la añade a `data/factions/index.json`. `--color` es el color de la facción en las tarjetas de la home. Con `--force` se regenera solo `faction.json` (y los puntos de las mejoras) de una facción existente; las unidades, sus puntos y las imágenes no se tocan.

### Capítulos de Marines Espaciales

Los capítulos con datasheets propios (Lobos Espaciales, Ángeles Oscuros, Ángeles Sangrientos…) no tienen página propia en Wahapedia: están dentro de `space-marines`. Se cargan como una facción aparte:

```sh
python3 tools/bootstrap_faction.py space-wolves --source space-marines --chapter "Space Wolves" --color "#5b7a99"
```

- `--chapter` es el nombre tal cual aparece en el filtro de capítulos de la página. Wahapedia marca cada fila con una máscara (`data-f="CH:<hex>"`) y el script toma el bit de ese capítulo.
- Solo entran los destacamentos y mejoras genéricos y los del capítulo; los de otros capítulos se descartan.
- La primera regla de ejército (Combat Doctrines) va a `armyRule`. Las demás (Librarius, Curse of the Wulfen…) van a `extraRules` y se ven en el editor y en la pestaña «Regla de ejército».
- Guarda en `faction.json` → `wahapedia` (`faction`, `chapter`, `chapterBit`). Los demás importadores lo leen de ahí, así que el resto de pasos se ejecutan igual, con el id de la facción (`space-wolves`).
- Los datasheets de otros capítulos se reconocen por sus palabras clave de facción y no se importan. En los datasheets genéricos, las filas solo para otros capítulos (puntos, a quién lidera) se quitan antes de leer la página (`only_chapter`).
- Las unidades de otras facciones que permite una regla (los aliados de Deathwatch Support) no entran.

**Revisa `faction.json`:**
- **`requires` de cada mejora**: palabras clave que debe tener la unidad, deducidas del texto «X model only». Si sale `[]`, cualquier personaje (no Héroe Épico) puede llevarla. Corrige los casos dudosos. Ejemplo: `[["INFANTRY", "OFFICER"]]` exige las dos palabras clave; `[["A"], ["B"]]` significa A **o** B (en el texto, «A/B unit only»). También entiende nombres de datasheet en minúsculas («Kroot War Shaper model only») y las exclusiones «(excluding KROOT SHAPER models)», que van a `excludes`. Una palabra en plural («STEALTH BATTLESUITS») encaja con la palabra clave en singular.
- **Letras que parecen latinas**: Wahapedia a veces mezcla letras cirílicas («Kauyоn» con una о cirílica). Los importadores las convierten a latinas; si un destacamento sale con `warning: no section`, mira si es esto.
- **`type: "upgrade"`**: se marca solo en las mejoras etiquetadas como UPGRADE. Pueden llevarlas unidades que no son personajes y no cuentan para el límite de mejoras.
- **`tags`**: etiquetas del destacamento, sacadas de la marca «UNIQUE: …» de Wahapedia sobre su título. Un ejército solo puede llevar un destacamento de cada etiqueta (los seis de Custodes son SHIELD HOST); el panel bloquea los demás y la validación avisa.
- **`grantsLead`**: una mejora con «SUPPORT: OPHYDIAN DESTROYERS, …» (o «LEADER: …») deja al portador unirse también a esas unidades.
- **`unitAbilities`**: si un destacamento lista habilidades con puntos bajo un título propio en vez de «Enhancements» (Pantheon of Woe: «Necrodermal Binding Abilities»), no son mejoras: cada datasheet nombrado las recibe solo y cuesta más (`points.json` → `unitAbilities`). Comprueba en la regla del destacamento que sea así.
- **Requisitos con «o»** («OVERLORD or CATACOMB COMMAND BARGE model only») salen como alternativas. Las exclusiones solo cuentan justo detrás de «only»; un «(excluding TITANIC units)» más adelante habla de las unidades afectadas, no del portador.
- **Nombres en español**: no hace falta tocarlos aquí; todos los textos se traducen en el paso 6.
- **Mecánicas propias de la facción**: la regla de ejército solo se muestra como texto. Las órdenes de Astra Militarum (`armyRule.orders`) son un caso especial escrito a mano; otras facciones no lo necesitan.

## 2. Importar los datasheets

Primero mira la clasificación:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes --list
```

Recorre todos los datasheets enlazados desde la página de la facción y clasifica cada uno según su propia página: **CORE** (oficiales), **LEGENDS** o **FW** (Forge World), mirando el logo del datasheet. Las páginas se guardan en una caché local (`.cache/wahapedia/`, fuera de git), así que solo se descargan la primera vez. Usa `--refresh` para volver a bajarlas, por ejemplo tras una errata. Después importa todas las oficiales:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes --all
```

Por cada unidad guarda:
- perfiles, armas (con sus perfiles y reglas), habilidades (CORE, de facción, propias y de equipo), regla de dañado y órdenes;
- composición, a quién lidera (sección LEADER) o a quién apoya (sección SUPPORT, `leader.support`) y límite de líderes. En la 11ª una unidad puede llevar sus líderes y además una unidad de apoyo;
- **puntos de la 11ª**, que se marcan como verificados. Si el datasheet tiene sobrecoste por copias ("YOUR 3RD+ UNIT COSTS", a veces desde la 2.ª), va a `points.json` → `unitsExtraCopies` (`{from, sizes}`);
- **costes de equipo** ("WARGEAR OPTIONS · per Lascannon · 5"): van a `points.json` → `wargearCosts` y la app los suma por cada pieza que lleve la unidad, también la que trae de serie;
- **palabras clave por modelo** ("KEYWORDS – ALL MODELS: … | TEMPESTOR PRIME: CHARACTER; OFFICER"): la unidad recibe todas;
- **equipo común de la facción** (los drones T'au de la sección «Drones» de la página de la facción): su regla y su arma se copian en cada unidad que puede llevarlos;
- **armas que da un equipo o una habilidad** ("MV15 Gun Drone: The bearer is equipped with 1 twin pulse blaster", "… is equipped with the support turret weapon"): van a `gearWeapons` / `abilityWeapons` y salen en la tabla de armas;
- **notas que limitan combinaciones** ("cannot have duplicates of these pieces of wargear", "No model can be equipped with both …"): van a `uniqueGear` / `exclusiveGear` y la validación de la lista avisa si no se cumplen;
- **equipo con cantidades** (`tools/wargear.py`):
  - cuántos modelos de cada tipo tiene la unidad en cada tamaño ("1 Tempestor + 4-9 Tempestus Scions");
  - el equipo por defecto contado ("Every Heavy Weapons Gunner is equipped with: lascannon…" → 3× lascannon). Lo que no es un arma (vox, estandarte, medi-pack) se guarda como equipo, y su habilidad de equipo solo se muestra si la unidad lo lleva;
  - las opciones de equipo convertidas en selectores. Entiende estos patrones:
    - sustituir el arma de un modelo ("This model's…", "The Sergeant's…", "One Trooper can replace…");
    - "Any number of <modelos> can each…": cada modelo elige, hasta el número de esos modelos;
    - "For every 10 models, up to 2…" y "Up to N…";
    - "All models in this unit can each…": todos a la vez;
    - "If this unit contains 10 models, …": solo con ese tamaño;
    - añadidos ("can be equipped with");
    - paquetes de varias armas ("autopistol and trench club → flamer and close combat weapon");
    - notas al pie con límite por arma ("no more than once… twice with 20 models");
    - alternativas excluyentes ("You can select one of the following options");
    - opciones que dependen de otra ("If this model is equipped with a neo-volkite pistol, it can be equipped with a storm shield"): van a `needs` y solo se aplican si se cumple la condición; con "is not equipped with" van a `needsNot`;
    - "For every 3 models in this unit, this unit can have 1 Plasmacyte";
    - "1 model's gauss scalpel or tesla caster can be replaced": se sustituye la de serie (la opción que cambia todas aplica después);
  - **unidades con acompañantes** ("3-6 Hunting Wolf / 3-6 Wolf Guard Headtaker", con puntos para 3, 6, 6 y 12 modelos): los tamaños son los modelos principales y los acompañantes una opción con su coste por modelo (`companion_split`). El número de modelos de la unidad cuenta solo los principales.

Con `--all`, una facción se reemplaza entera: las unidades que ya no son datasheets de la facción se eliminan de `units.json` y `points.json`. Las de Legends y Forge World se apuntan en `units.json` → `excluded` y nunca se importan. Los identificadores son el nombre del datasheet en minúsculas con guiones (`cadian-heavy-weapons-squad`). No se usan alias: si GW renombra una unidad, actualiza su clave en `images.json` (las listas guardadas que la usaran la pierden al abrirse).

**Revisa la salida.** Al final aparecen líneas `CHECK <unidad>` con lo que no se ha podido interpretar: opciones de equipo que no encajan en ningún patrón y unidades a las que lidera que no existen en la facción. Las unidades de Legends y Forge World excluidas no se avisan.
- **Exclusiones por página**: una página de Legends puede tener el mismo id que una unidad oficial (Venerable Dreadnought). Por eso la exclusión se comprueba por la página del datasheet, no por el id.
- **Líderes marcados como Legends**: Wahapedia a veces marca como Legends un objetivo de liderazgo que es oficial. Se conservan todos; la marca solo silencia el aviso si el objetivo no existe en la facción.
- **Rol incorrecto**: se calcula a partir de las palabras clave, en este orden: FORTIFICATION, TITANIC, CHARACTER, BATTLELINE, AIRCRAFT, TRANSPORT, MONSTER, VEHICLE, MOUNTED y, si no, infantry. TITANIC va antes que CHARACTER para que los Caballeros Imperiales, que son personajes titánicos, salgan en «Titánicos»; las mejoras y el Señor de la Guerra dependen de las palabras clave, no del rol.
- **Datasheets que no se pueden reclutar** (p. ej. Sir Hekhtur, que solo se usa cuando muere el Canis Rex): salen sin puntos. Añade su id a `excluded.ids` y quítalos de `units`.

Para añadir o actualizar unidades sueltas más adelante:

```sh
.venv/bin/python tools/import_wahapedia_datasheets.py adeptus-custodes Blade-Champion Trajann-Valoris
```

### 2b. Auditar (obligatorio)

```sh
.venv/bin/python tools/audit_units.py adeptus-custodes
```

Compara cada unidad importada con su datasheet de la caché y termina con «N errors, M warnings». Comprueba:

| Comprobación | Qué detecta |
|---|---|
| `weapons` | Perfiles de arma de la tabla que no se han importado |
| `abilities` | Bloques de habilidad (también de equipo) que no se han importado |
| `composition` | Tipos de modelo que no cuadran con el tamaño de la unidad |
| `loadout` | Equipo por defecto que no se reconoce como arma: nombre escrito distinto o equipo sin habilidad |
| `reachable` | Armas del datasheet que no están en el equipo por defecto ni en ninguna opción, es decir, opciones o equipo mal leídos |
| `options` | Opciones de equipo que no se han convertido en selector, o que dan un «equipo» que no es un arma ni tiene regla (opción mal leída) |
| `costs` | Costes de equipo de algo que la unidad no puede llevar |
| `replaces` | Opciones que sustituyen algo que la unidad nunca lleva |
| `data` | Sin perfiles, palabras clave o puntos, o líderes hacia unidades inexistentes |

Hay que dejarlo en **0 errores**. Los errores son fallos de lectura y casi siempre se corrigen en el parser, no en los datos: así el arreglo sirve para todas las facciones. Casos que han aparecido y ya están resueltos:
- nombres con «and» o comas ("monstrous bonesword and lash whip");
- variantes de escritura ("Militarum multi-laser" / "multi-laser", "battlecannon" / "battle cannon");
- listas de equipo sin punto final o partidas por un salto de línea;
- "1 of the following";
- guiones no separables ("hot‑shot");
- llamadas a nota pegadas al texto ("following*:");
- "equipped with: nothing";
- notas entre corchetes dentro de una opción ("1 medi-pack [that model's hot-shot lasgun cannot be replaced]"), que se leían como un objeto de equipo;
- plurales con un calificativo delante ("2 additional heavy stubbers" / "heavy stubber");
- erratas de una letra en nombres largos ("tri-bade" / "tri-blade") y "have their X can be replaced with";
- "up to two of the following, and can take duplicates" / "but cannot take duplicates" (varias elecciones por modelo) y "up to 2 seeker missiles" (cantidad);
- "If this unit contains 10 models:" seguido de opciones completas, "2 models can each…" y "1 model in this unit equipped with…";
- un tamaño que es el modelo más su complemento ("1 model | 85, 2 models | 105" con "can be equipped with 1 Tidewall defence platform");
- la lista de equipo que nombra las armas distinto que la tabla de perfiles (Krootox Rampagers, el «Chronomancer's stave» que es el Aeonstave a distancia y cuerpo a cuerpo);
- armas que solo da una habilidad ("select up to two different C'tan Powers weapons … this model is equipped with those weapons": Tesseract Vault);
- personajes SUPPORT sin unidades a las que unirse (la auditoría avisa con `data: the datasheet has Leader/Support targets`).

La auditoría no ve los nombres de equipo raros que sí se ven en la app: revisa también la lista de comprobación del paso 7 en los dos idiomas.

Si aparece un patrón nuevo, añádelo en `tools/wargear.py` (opciones y equipo) o en `tools/import_wahapedia_datasheets.py` (lectura de la página), reimporta y vuelve a auditar **todas** las facciones (`tools/audit_units.py` sin argumentos). Después comprueba que el cambio no altera las facciones anteriores:

```sh
for f in $(ls data/factions | grep -v index); do .venv/bin/python tools/import_wahapedia_datasheets.py $f --all --check; done
```

`--check` reimporta con el código actual sin escribir nada y lista lo que cambiaría (`CHANGE unidad.campo: antes → después`). En las facciones que ya estaban bien debe decir `no changes`; si no, el patrón nuevo ha roto algo o hay un cambio a mano en `units.json` que una reimportación perdería.

La auditoría también comprueba que `data/factions/index.json` tenga bien el número de unidades y de destacamentos de cada facción, que es lo que enseña el selector de **Nueva lista** sin cargar la facción. Los importadores los mantienen solos.

## 3. Reglas completas y estratagemas

```sh
python3 tools/import_wahapedia_rules.py adeptus-custodes
```

Genera:
- `rules.json`: texto completo de la regla de cada destacamento y de cada mejora;
- `stratagems.json`: estratagemas por destacamento;
- `data/editions/11th-stratagems.json`: las Core, comunes a todas las facciones.

Los textos completos se ven en la **vista de ejército** y en el desplegable de cada destacamento del editor; los resúmenes de `faction.json` solo se usan si falta el texto completo. Los bloques «Errata/FAQ» de Wahapedia se descartan, porque el texto principal ya viene corregido. Comprueba que cada destacamento muestre `enhancements` y `stratagems`. Si alguno sale a 0, su nombre en Wahapedia no coincide con el de `faction.json`.

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

**Revisa el resultado.** El emparejamiento es por palabras del nombre, en singular, y prefiere el producto cuyo nombre tiene menos palabras de más; una caja que encaja con un nombre más concreto se reserva para esa unidad (la de «Lokhust Heavy Destroyer» no es la de los Lokhust Destroyers). Con Astra Militarum acertó 52 de 53.
- **Unidades sin imagen**: suelen ser variantes que comparten caja (los 7 Leman Russ, Comandantes, unidades de Ogretes…) o unidades que solo se venden dentro de cajas conjuntas (Combat Patrol, Royal Court, Kill Team). Añádelas a mano en `images.json` copiando la URL del kit, o desde la app: ficha de la unidad → **Imagen de la tienda (URL)**.
- **Coincidencias dudosas**: comprueba sobre todo las unidades con nombres genéricos (p. ej. "Heavy Weapons Squad").
- Con `--products <facción>-products.json` puedes repetir el emparejamiento sin volver a abrir la tienda (por ejemplo, tras importar unidades nuevas).
- Usa la tienda en **inglés** (`en-GB`): con nombres en español se emparejan muchas menos.
- Para un capítulo, usa su propia sección (`…/shop/warhammer-40000/space-marines/space-wolves`). La de Marines genéricos sirve después para las unidades comunes que falten.
- Algunas unidades se venden en la sección de **otra facción** (p. ej. los Skitarii de los Caballeros Imperiales están en Adeptus Mechanicus). Vuelve a ejecutar el script con la URL de esa sección: solo rellena las unidades que aún no tienen imagen.

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

## 6. Traducir al español

Los textos de juego se importan en inglés. La app los traduce con diccionarios:

- `data/factions/<facción>/i18n.es.json`: textos de la facción (nombres, habilidades, opciones de equipo, reglas, mejoras y estratagemas).
- `data/editions/11th.i18n.es.json`: estratagemas Core, textos que comparten dos o más facciones y el glosario `terms` de reglas con valor («Rapid Fire 2» → «Fuego Rápido 2»).

```sh
python3 tools/translations.py pending                 # .cache/translations/<facción>.tsv: textos sin traducir, numerados
# escribe .cache/translations/<facción>.es.txt con una línea por texto: "<número><TAB><traducción>" (saltos de línea como \n)
python3 tools/translations.py apply .cache/translations/<facción>.tsv .cache/translations/<facción>.es.txt
python3 tools/translations.py pending                 # debe quedar en 0
```

- Usa la terminología de GW en español (acobardamiento, alcance de combate, Despliegue Rápido, No Hay Dolor…) y la misma traducción para el mismo término en toda la facción.
- Las palabras clave en mayúsculas (INFANTRY, OFFICER…) se quedan en inglés, igual que los nombres propios.
- Las habilidades de armas entre corchetes se traducen como en el glosario: `[IMPACTOS LETALES]`, `[IGNORA COBERTURA]`.
- Si aparece una palabra clave de arma o una habilidad básica nueva, añádela a `terms` en `11th.i18n.es.json`, no a la lista de textos.
- Los nombres de destacamento que ya tengan `name.es` en `faction.json` deben traducirse igual cuando aparecen como origen de una estratagema.

La traducción no es oficial. Un texto sin traducir se muestra en inglés, así que tras cada reimportación basta con repetir `pending` y traducir lo nuevo.

## 7. Comprobar en la app

Primero la comprobación automática (necesita Google Chrome; tarda unos 45 s por idioma con 7 facciones):

```sh
python3 tools/check_app.py                 # todas las facciones, en español e inglés
python3 tools/check_app.py necrons         # solo una
```

Crea en una carpeta temporal una lista de prueba por facción (todas las unidades y destacamentos, cada opción de equipo con su primera elección y cada líder o apoyo unido a la primera unidad que puede), arranca el servidor con esa carpeta (tus listas no se tocan) y recorre en Chrome headless la home, el selector de facción, el editor, todas las fichas y todas las pestañas de la vista de ejército. Falla si hay errores de JavaScript, si falta alguna lista, unidad, ficha o facción, si sale «undefined» o «NaN», o si hay frases en el otro idioma. Con `--keep` deja la carpeta con las listas y el texto de cada vista.

Después, a mano:

```sh
./serve.sh
```

- [ ] La facción aparece en **Nueva lista** y se puede crear una lista.
- [ ] El catálogo muestra todas las unidades, con foto y puntos sin `*`.
- [ ] Un personaje se puede unir a las unidades que indica su datasheet, y **Líderes n/m** respeta el límite.
- [ ] Al elegir un destacamento, sus mejoras aparecen solo en los personajes que cumplen el requisito.
- [ ] En la **vista de ejército** se ven la regla del destacamento, las mejoras, las estratagemas y las Core.
- [ ] Una tercera copia de una unidad con sobrecoste sale marcada como «3.ª+ copia» con el precio más alto.
- [ ] En una unidad con opciones por modelo (p. ej. una escuadra de armas pesadas), cada modelo puede elegir arma y la tabla muestra las cantidades.
- [ ] Con **ES** no queda texto de juego en inglés (salvo palabras clave en mayúsculas y nombres propios), y con **EN** todo sale en inglés.
- [ ] La consola del navegador no muestra errores.

## Mantenimiento

| Cuando… | Haz… |
|---|---|
| Sale un MFM nuevo | Reimporta la facción con `--all --refresh` (los puntos vienen en cada datasheet) y audita, o edita `points.json` a mano |
| GW publica erratas de reglas o estratagemas | `import_wahapedia_rules.py <facción>` y `import_wahapedia_datasheets.py <facción> --all --refresh`, y después `audit_units.py` |
| Sale una unidad nueva | `import_wahapedia_datasheets.py <facción> <Datasheet>` y `store_images.py … --products <lista guardada>`, o la URL a mano |
| Has reimportado algo | `translations.py pending`, traduce lo que salga y `apply`; después `check_app.py` |
| Has cambiado el importador o `wargear.py` | `import_wahapedia_datasheets.py <facción> --all --check` en todas las facciones: debe dar `no changes` |
| Has cambiado el código de la app | `check_app.py` |
| Quieres excluir una unidad | Añade su id a `units.json` → `excluded.ids` y bórrala de `units`, `points.json` e `images.json` |

## Problemas conocidos

- **Pillow no se instala**: estás usando PyPy. Crea el entorno con `/usr/bin/python3`.
- **`202` o "Human Verification" en la tienda**: es la protección anti-bots. Usa `store_images.py`, que abre una ventana visible, y no Chrome headless.
- **Wahapedia cambia su HTML**: los importadores dependen de sus clases CSS (ver [RECURSOS.md](RECURSOS.md)). Si fallan tras un cambio, hay que ajustar las expresiones regulares.
- **Listas guardadas tras reimportar**: al abrir una lista, la app quita las unidades que ya no existen y las elecciones de equipo que han dejado de ser válidas, y guarda el resultado.
- **Traducciones**: los textos de reglas se importan en inglés y se traducen con `translations.py` (paso 6). Si Wahapedia cambia un texto, su traducción deja de encajar y vuelve a salir en `pending`.
