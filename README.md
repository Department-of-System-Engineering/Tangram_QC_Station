# Tangram QC Station

Kameraalapú, CPU-n futó minőségellenőrzés hét elemből álló tangramhoz.
A korábbi kísérleti programok a `legacy/` könyvtárban változatlanul szerepelnek;
az új belépési pont: `python -m qc_station`.

## Mit tud az új változat?

- Rögzített kameránál elég a színek mintavétele: a hét alakzatot előre megadott
  sablon alapján ellenőrzi. A teljes sarokkijelöléses tanítás opcionális.
- A–D variáns felismerése, rendelés szerinti elvárt variáns ellenőrzése,
  külön geometriai, relatív helyzeti, párhuzamossági/merőlegességi és színpontszám.
- Alapértelmezésben **3 másodperces vizsgálat**, legfeljebb 10 elemzett kép/s.
- Legalább 15 minta, legalább 80% elfogadott képkocka és elfogadott zárókép kell a PASS-hoz.
  Alapértelmezésben egy képen legalább **5 felismert elem** és egyértelmű A–D variáns
  szükséges; rendeléses módban annak a várt variánssal is egyeznie kell.
  Az alak- és szöghibák megmaradnak a mérésben és a pontszámban, de nem tiltják a PASS-t.
  A `--strict-quality` kapcsolóval a korábbi, mind a hét elem megfelelőségét megkövetelő
  ellenőrzés használható. Az üres képek is
  beleszámítanak a hibákba. Egy másodpercnél nagyobb mintavételi kiesés vagy kevés
  minta esetén az eredmény INCONCLUSIVE, nem PASS.
- Vizsgálatonként helyi MJPEG AVI biztonsági felvétel és JSON küldési fájl.
  A videó az elemzett képeket tartalmazza; névleges lejátszási sebessége a `--fps`.
  Terhelés miatti képkieséskor a videó időtartama rövidebb lehet a valós vizsgálatnál;
  a tényleges időt a JSON `duration_seconds` mezője adja meg.
- Egy eredmény termékbehelyezésenként; új ciklushoz legalább 0,7 s detektált elem
  nélküli idő kell. A v2 ciklus az első színes alkatrészjelölt felismerésekor indul,
  nem vár szereléskész jelre vagy mind a hét elem jelenlétére.
- Kézi, automatikus variánsfelismerés és nyomonkövetési érkezéshez kötött rendeléses mód.
- Közvetlen kommunikáció a digitális iker meglévő API-jával. Az iker menti a
  közös adatbázisba a mérést és a hibákat; PASS → `done`, FAIL → `rework`.
  Az állomás nem használ adatbázist vagy Dockert.

## Digitális iker kapcsolat

```bash
python -m qc_station run --mode manual --profile profiles/cica-v2.json
# QC_API_KEY = a digitális iker INBOUND_API_KEY kulcsa:
python -m qc_station run --mode order --profile profiles/cica-v2.json --twin-url http://twin-server:8000
```

[Üzemmódok, API és hibakategóriák](docs/integration.md) ·
[Natív Raspberry-telepítés és beállítás](docs/deployment.md).
Az INCONCLUSIVE mérési hibát jelent, nem módosít termékstátuszt.

Rendeléses módban a `WAITING_FOR_TRACKING` azt jelenti, hogy az iker nem adott
vizsgálati feladatot. A termék legutóbbi nyomonkövetési eseménye `visual_qc` / `arrived`
legyen, aktív rendeléshez és vizsgálható termékhez tartozzon. A terminál kiírja az
átvett rendelés-, termékazonosítót és a várt variánst. A `RESULT_ACKNOWLEDGED` a
központi eredménymentés visszaigazolása. PASS esetén az iker a kapcsolódó terméket
`done` állapotba állítja, és annak rendelési sorában frissíti a `completed_quantity`
értéket; az ismételt eredményküldés nem növeli újra a darabszámot.

Az ablakban **D** menti a nyers képet, maszkot, felismert kontúrjelölteket,
profilt és kiértékelést a `runtime/diagnostics/` könyvtárba. Ez például a 8/7
darabszám okának vizsgálatához használható; nem indít és nem fogad el mérést.
Ha egy kép feldolgozása kb. 700 ms, a 3 másodperc kevés 15 mintához:
használj például `--seconds 15` értéket. Ez csak a mintaszámhoz ad több időt,
a geometriai és variánshibákat nem teszi elfogadhatóvá.

**A v2 profilok a termék síkbeli elfordulását a teljes 360°-os tartományban kezelik**,
a korábban mentett, csak színmintás profilok is. Az eltolást és egyenletes
skálaváltozást a felismert elemek közös illesztése kompenzálja. Az egyes darabok
egymáshoz képesti helyzetét és szögét továbbra is ellenőrzi. Tükrözést és
perspektívaváltozást nem kompenzál. Mind a hét elem legyen teljesen a munkaterületen. A kalibrált
munkaterület és feldolgozási felbontás maradjon ugyanaz. A kalibrált piros/sárga/kék
elemeknek optikailag elkülöníthetőknek kell lenniük: egymáshoz érő azonos színű
elemeket, illetve a háttérrel teljesen összeolvadó darabot nem lehet megbízhatóan
külön kontúrként kinyerni. A munkaterület széléhez érő színfoltokat háttérnek tekinti.
A régi, alapmaszkos profilok kompatibilitási módban tovább futnak, variánsfelismerés nélkül.
Az elfogadási küszöbök induló értékek, valós jó/hibás mintákkal validálandók.

## Telepítés

Python 3.11 vagy újabb, OpenCV és NumPy. Desktop Python kell az ablakos kalibrációhoz.

```bash
python -m venv .venv
# Linux / Raspberry Pi:
source .venv/bin/activate
# Windows PowerShell alternatíva:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Raspberry Pi-n elsődleges cél a 64 bites rendszer és egy OpenCV/V4L2 által elérhető
USB-kamera. Az adott ARM/Python kombinációhoz elérhető OpenCV-csomagot telepítsd;
ha nincs pip wheel, használható a rendszer `python3-opencv` és `python3-numpy`
csomagja, `python3 -m venv --system-site-packages .venv` környezettel. CSI/Picamera2
kameraadapter ebben a változatban még nincs. A konkrét Pi-modell és kamera nincs
megadva, ezért a kompatibilitás és a sebesség helyszíni ellenőrzést igényel.

## Beállítás csak színmintavétellel

A jelenlegi 640×480-as kameranézethez beépített macskasablon készült a
2026-09-25-i kép alapján. Nem kell alakzatsarkokat kijelölni vagy egy jó terméket
elfogadtatni a színbeállítás mentéséhez.

```bash
python -m qc_station sample-colors --camera 0 --output profiles/cica-v2.json
python -m qc_station run --mode manual --profile profiles/cica-v2.json
```

1. SPACE: kép rögzítése.
2. Sorban piros, sárga, kék, majd háttér: jelölj ki kis, egynemű téglalapokat.
   ENTER rögzít egy mintát, további téglalapokkal bővíthető; ESC lép tovább.
3. A háttérből a kék lap világos és sötét részeit, valamint az alapot is mintázd.
   A kék alkatrész és a kék háttér külön mintacsoportba tartozik.
4. A végén a zöld vonalak a fix sablont mutatják, nem a mért kontúrokat.
   `S` menti a színeket akkor is, ha az aktuális kép FAIL. Ez nem fogadja el a terméket.
   A sablon referenciairányt mutat; az élőkép terméke lehet elfordítva.

Futáskor továbbra is ellenőrzi az alakot, relatív területet, egymáshoz képesti helyzetet,
szögeket, élkapcsolatokat, darabszámot és variánst. Először a teljes terméket illeszti
a referenciairányhoz, majd ezen a közös koordinátarendszeren belül pontoz.
Az illesztés nem használ színcímkéket, ezért a rossz variánst nem igazítja a várt színekhez.
Másik recept a `--layout` JSON-paraméterrel adható meg. Nyers mentett
képen is mintázhatsz: `sample-colors --image .../frame.png`.

A sablon az illesztés után szolgál a háttérfoltok térbeli szűrésére, nem vágja formára a kontúrokat.
A vizsgálati helyektől távoli tárgyak nem részei a darabszámellenőrzésnek.
Alkatrészhez hozzáolvadt háttér vagy fel nem ismert elem továbbra is hibát okozhat.

A Lab-színmodell által széttördelt felületeket a mentett HSV-színtartomány
összefüggő foltjaival egészíti ki, ha a folt legalább 20%-át a Lab-modell is az
adott színhez sorolja. Munkaterület széléhez kapcsolódó folttal nem bővít.
Ez mért színpixeleket használ, nem sablonból pótolja az alakzatot; a geometriai
ellenőrzések változatlanul érvényesek. A háttér által körülvett, de attól különálló
alkatrészeket is külön összefüggő komponensként vizsgálja.

## Opcionális teljes alakzatkalibráció

A `calibrate` sarokkijelöléses módhoz ismert, jó A/B/C/D termék kell. A képen lévő
narancssárgát pirosnak vesszük; a kép alatti prezentációs feliratok nem részei a receptnek.
A bal/jobb fül az álló referenciarajz szerinti bal/jobb, akkor is, ha a kamera más
szögből látja a terméket.

| Elem | A | B | C | D |
|---|---|---|---|---|
| Bal fül | kék | sárga | kék | sárga |
| Jobb fül | sárga | kék | kék | sárga |
| Fej (négyzet) | piros | piros | piros | piros |
| Nyak (paralelogramma) | sárga | kék | sárga | sárga |
| Középső háromszög | piros | piros | piros | piros |
| Nagy testháromszög | kék | kék | kék | sárga |
| Talp | kék | kék | kék | kék |

```bash
# A --variant a kalibráló mintadarab TÉNYLEGES variánsa legyen!
python -m qc_station calibrate --camera 0 --variant A --output profiles/cica-v2.json
# Nyers kamerafotóval:
python -m qc_station calibrate --image jo_termek.png --variant A --output profiles/cica-v2.json
```

1. SPACE: képfagyasztás. Jelöld ki a teljes terméket körülvevő munkaterületet,
   a szélén háttérráhagyással; ENTER.
2. A program sorban kéri a bal fület, jobb fület, fejet, nyakat, középső háromszöget,
   nagy testháromszöget és talpat. Mindig a színes elem sarkaira kattints körbejárási
   sorrendben, ne az alapra. Háromszög: 3 pont, fej/nyak: 4 pont; ENTER továbblép.
3. U: utolsó pont vagy elem visszavonása. Q: megszakítás. A 7. elem után S: ellenőrzés és mentés.
4. Mentés előtt a program automatikusan kiértékeli a jó képet; csak akkor ment,
   ha a színalapú szegmentáció és a geometriai/szögvizsgálat is elfogadja.
   A kézi körberajzolás a tanítást segíti, nem helyettesíti a méréskori felismerést.
5. Egy profil tartalmazza mind a négy receptet. Ellenőrizd a többi variáns valódi
   példányain is, különösen az eltérő méretű/színű darabokon és csillogás mellett.

Az új LED után újrakalibrálás szükséges. A v1 profil nem alakítható automatikusan
v2-vé, mert nincsenek benne szemantikusan megnevezett elemek és közös színosztályok.
Részletes pontozás és korlátok: [docs/variants.md](docs/variants.md).

### Halvány piros elemek és hasonló színű háttér

Az újonnan készített v2 profil már Lab színtérben tanul kis színpalettát a kijelölt
elemek belsejéből **és a munkaterület háttérpixeleiből**. Nem követel meg rózsaszín
alapot, és nem használja annak geometriáját; a háttérszínek kizáró mintaként segítenek
elkerülni, hogy a halvány piros és a rózsaszín egy kontúrrá olvadjon. Az azonosan
valószínű színosztályba kerülő pixel ismeretlen marad. Régebbi v2 profilok továbbra is
HSV-t használnak, tehát a javításhoz újrakalibrálás kell.

A zöld poligonok a saját sarokkijelöléseid, nem a mért kontúrok. Sikertelen `S` mentés
után külön ablakban jelenik meg az automatikus maszk és a tényleges detektálás.
A program a profil mellett, egy egyedi `calibration_diagnostics/.../` könyvtárba menti:

- `frame.png`: eredeti, feliratok és kijelölések nélküli kamerakép;
- `selection.json`: a sarokkijelölések, munkaterület és variáns;
- `detected.png`, `mask.png`: a tényleges automatikus detektálás;
- `report.json`: mért hibák és az elutasított profil adatai (nem futtatható profil).

A terminál kiírja a pontos könyvtárat. Hibaelemzéshez ezt a teljes könyvtárat érdemes
megőrizni/átadni, nem képernyőképet használni bemenetként. Nem kell újrakattintani:

```bash
python -m qc_station calibrate --resume profiles/calibration_diagnostics/ID/selection.json --output profiles/cica-v2.json
```

A `--resume` a mentett nyers képet használja, nem élő kamerát; `U`-val javíthatók a
kijelölések, `S` újra ellenőriz és csak siker esetén ment aktív profilt. A háttér vagy
világítás jelentős változásakor új kameraképből taníts; a Lab-paletta sem tud optikailag
megkülönböztethetetlen felületeket biztonságosan szétválasztani.

### Apró háttérfoltok és a fül plusz kontúrcsúcsa

Az új kalibráció a legkisebb kijelölt darab területének 25%-át menti jelöltméret-küszöbként
(legalább 30 pixel). Ennél kisebb foltok nem számítanak teljes alkatrésznek. Ez nem a
hét legnagyobb kontúr vak kiválasztása: nagyobb plusz elemek továbbra is hibát okoznak.
Kis szennyeződések külön vizsgálatára ez a darabszámellenőrzés nem alkalmas.
A megjelenített detektálási maszk már csak a méret- és szélvizsgálaton átment jelölteket mutatja.

A lekerekített/levágott kis sarok miatt létrejövő plusz kontúrcsúcsot a hosszabb mért
élszakaszokra illesztett egyenesek kezelik. A nyers kontúr területét és alakját továbbra
is ellenőrzi a rendszer. Ha az élek nem párosíthatók, `edge_geometry` hiba és
`angle_degrees: null` szerepel; ez nem egy mért 90 fokos elfordulás.
Korábban készült profilnál a jelöltméret-küszöb még a régi érték: a mentett kijelölés
`--resume` betöltésével és `S` mentéssel újratanítható, újrakattintás nélkül.

### Hiányos színmaszk egy egyébként egyenes él mentén

A 2026-09-24-i testkontúr hibájára az élillesztés kapott egy korlátozott második
lépést. Ha a szigorú illesztés nem sikerül, a megmaradt kontúrpontokból méri az
egyeneseket. Minden oldalon legalább 9/12 hosszirányú szakaszban kell mért
támasznak lennie. A nagy vagy mély hiányt nem tölti ki automatikusan; a jelölt
poligon területe legfeljebb 12%-kal térhet el a nyers kontúrétól. Az elvárt
referenciaszögeket nem használja az illesztéshez, ezért az elfordulás mérhető marad.

A pontsúlyozás egyenletes kontúrhosszon történik: a recés rész sok töréspontja
nem kap több súlyt, mint egy hosszú tiszta él. A nyers maszk, terület- és alakmérés
nem változik, a párhuzamossági/merőlegességi vizsgálat továbbra is működik.
A tűrésen belüli fizikai kis csorbulás és színmaszk-kiesés ebből a maszkból nem
különböztethető meg biztosan; az illesztés nem bizonyítja a felület épségét.
A mentett kalibrációs kijelölés az új kóddal `--resume` segítségével újraellenőrizhető.

### Régi alapmaszkos kalibráció (csak `--legacy-base` módban)

Az alábbi korábbi módszer v1 profilt készít, nincs A–D variánsfelismerése.

1. Rögzítsd a kamerát, tedd a jó terméket a teljesen látható munkaterületre.
2. Indítsd: `python -m qc_station calibrate --legacy-base --camera 0 --output profiles/cica.json`.
3. SPACE-szel fagyaszd a képet. Jelölj ki kis, egyenletes **rózsaszín alapfelületet**, ENTER.
4. A HSV csúszkákkal állítsd a maszkot úgy, hogy pontosan hét különálló alkatrész
   kapjon zöld kontúrt. A kék kontúrnak a teljes alapot kell körülfognia.
5. `S` menti a profilt; `Q` megszakítja. A hét számozott elem alakja, helyzete és
   belső színe automatikusan bekerül a profilba. A színszűrés a vörös Hue-átfordulást is kezeli.
6. Indíts ellenőrzést és próbálj ki jó, hiányos, rossz színű, elfordított és elcsúszott mintákat.

### Ha csak 5/7 vagy 6/7 elem látszik a régi, alapmaszkos kalibrációban

A színmaszk vékony alapvonalainak szakadása miatt két belső terület összeolvadhat,
vagy egy elem belseje összenyílhat a háttérrel. Ez nem feltétlenül kamera-felbontási
probléma. Az elvárt darabszám marad hét.

- Először a `Gap closing` csúszkát emeld fokozatosan: 1-es állás = 3×3,
  2-es = 5×5, 3-as = 7×7 képpontos réslezárás, legfeljebb 15×15.
  A legkisebb megfelelő értéket válaszd, mert túl nagy érték eltorzíthatja a kontúrokat.
- Ha marad szakadás, a színes `Calibration` ablakban kattints a meglévő rózsaszín
  vonal két végére. Legfeljebb 40 képpontos szakasz köthető össze, legfeljebb 20 helyen.
  Csak tényleges alapvonal rövid hiányát javítsd; ne rajzolj új alkatrészt vagy teljes élt.
- `U`: utolsó pont/összekötés visszavonása; `R`: összes kézi összekötés törlése.
  A cián vonal a beállított összekötés, a fekete-fehér maszk mutatja, hogy éppen aktív-e.
- `S` csak a hét külön kontúr megtalálása után ment. A javítási beállítások a profilba
  kerülnek, és ellenőrzéskor is érvényesülnek. Régi profilok továbbra is használhatók.

A kézi összekötés csak akkor aktív, ha a nyers színmaszkban mindkét végén, két pixel
környezeten belül látszik az alap. Ez nem állítja vissza a kitakart információt:
segített szegmentáció, amelyet hibás termékekkel is ellenőrizni kell.
**A kézi összekötések rögzített képpozíciókhoz kötöttek: csak rögzített kamera és
ugyanoda illesztett termék mellett használd őket.** Eltérő felbontásnál a program hibával
megáll; helyzetváltozásnál újrakalibrálás szükséges. A csak automatikus réslezárásnak
nincs ilyen képpozícióhoz kötése.

Az XDG/Wayland Qt-figyelmeztetés önmagában nem magyarázza a darabszámot, ha az ablakok
és a kijelölés működnek; az elemszámot a képfeldolgozás maszkja határozza meg.

Mentett fotó is használható: `python -m qc_station calibrate --legacy-base --image jo_termek.png`.
Másik összeállításhoz ments külön profilt. Az elemek neve és a toleranciák a profil
JSON-jában szerkeszthetők. A mentés felülírja az azonos nevű profilt; az eredmények
tartalomfüggő kalibrációazonosítót tárolnak. A profilokat archiváld a mérési eredményekkel.
Az új LED-világítás felszerelése után új színkalibráció szükséges.

## Futtatás

```bash
python -m qc_station run --profile profiles/cica-v2.json --camera 0 --debug
# Kijelző nélküli Pi:
python -m qc_station run --profile profiles/cica-v2.json --camera 0 --headless
# Egy konkrét, már azonosított termék vizsgálata:
python -m qc_station run --profile profiles/cica-v2.json --once --product-instance-id 123 --expected-variant B
# Régi, offline tesztbemenetből (nem a digitális iker rendeléses üzemmódja):
python -m qc_station run --profile profiles/cica-v2.json --once --order-context examples/order-context.json
```

`--expected-variant` nélkül bármelyik ismert, jól összeállított variáns megfelelhet.
Megadott elvárásnál a felismert variáns ettől függetlenül tárolódik, de eltéréskor FAIL.
A három másodperces ablakban a felismerésnek is legalább 80%-ban azonosnak kell lennie,
és a záróképnek egyeznie kell vele; megoszló variánsok esetén INCONCLUSIVE.
A rendelési JSON egy konkrét termék pillanatképe, ezért csak `--once` mellett használható;
új termékhez új bemenet kell. Élő rendeléses működéshez használd a `--mode order`
és `--twin-url` kapcsolókat; a rendelést a digitális iker API-ja adja.

`Q` kilép az ablakos futásból. Kameraolvasási hiba/megszakítás során az aktív vizsgálat
INCONCLUSIVE eredményt kap, ha a háttértár írható; egy processzkilövés vagy áramkimaradás
közbeni aktív ciklus még elveszhet. A már atomikusan kiírt JSON-eredmények megmaradnak.

`--seconds`, `--fps`, `--min-samples`, `--width`, `--height` állítják a futást.
Az alapérték 640×480, 10 FPS, 3 s, 15 minta. Alacsony FPS mellett a minimális
mintaszámot/időablakot is összehangoltan kell beállítani. `--no-video` kikapcsolja a
videómentést, de a három másodperces ellenőrzést nem. A teljes felvétel nincs RAM-ban:
a kód egy képkockát, munkamaszkokat és összesítő számlálókat tart.

Függő küldések: `runtime/delivery/pending/`; visszaigazolt másolatok:
`runtime/delivery/sent/`; videók: `runtime/videos/`.
Az alapértelmezett 500 videós határnál a program megáll, nem töröl korábbi bizonyítékot.
A határ `--max-videos` kapcsolóval módosítható. A visszaigazolt JSON-másolatok és
videók archiválását és a szabad tárhely felügyeletét az üzemeltetés kezeli.
A fejlesztői profilok és mérési adatok nincsenek Gitbe véve.

## Digital twin kapcsolat

A helyi `digital_twin` projekt meglévő API-ja QC-végpontokkal bővült. Az
állomásnak csak az API címe és kulcsa kell. A mérést, hibajegyzéket és a termék
`done/rework` állapotát az iker kezeli ugyanabban a közös adatbázisban.

```bash
# A kamerás program leállítása után függő fájlok kézi újraküldése:
python -m qc_station flush --endpoint https://YOUR-HOST/qc/results
```

A `QC_API_KEY` kötelező a hálózati működéshez. Az iker `INBOUND_API_KEY`
értékét kell beállítani, és `X-API-Key` fejlécben kerül elküldésre.
Hálózati hibánál a küldési JSON megmarad; ugyanazzal az azonosítóval újraküldhető.
Csak az adott mérés pozitív visszaigazolása után kerül a `sent` mappába.
Részletes szerződés és a jelenlegi backend korlátai: [docs/integration.md](docs/integration.md).

## Ellenőrzés és teljesítmény

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py --image jo_termek.png --profile profiles/cica-v2.json
```

A benchmark a cél-Pi-n futtatandó, reprezentatív fotóval. Csak a képelemzést méri;
a kamera, videókódolás és megjelenítés idejét nem. A 10 FPS-es induló célhoz az
elemzés + videóírás + kijelzés teljes költsége maradjon 100 ms alatt, és hosszabb
üzem alatt is ellenőrizd a mintaszámot, RAM-ot, hőmérsékletet és a CPU-terhelést.
A 8 GB RAM önmagában nem garantál valós idejű működést. Pi-n és laborvideón még
nem történt mérés. A szintetikus tesztek szoftverhibákat keresnek, nem mérik a valódi
selejtészlelési arányt.

Az eredeti forrás részletes értékelése: [docs/review.md](docs/review.md).
