# Tangram QC Station

Kameraalapú, CPU-n futó minőségellenőrzés hét elemből álló tangramhoz.
A korábbi kísérleti programok a `legacy/` könyvtárban változatlanul szerepelnek;
az új belépési pont: `python -m qc_station`.

## Mit tud az új változat?

- Az új (v2) kalibráció az alkatrészek színét, kontúrját és egymáshoz viszonyított
  helyzetét tanulja; az alap színét nem használja.
- A–D variáns felismerése, rendelés szerinti elvárt variáns ellenőrzése,
  külön geometriai, relatív helyzeti, párhuzamossági/merőlegességi és színpontszám.
- Alapértelmezésben **3 másodperces vizsgálat**, legfeljebb 10 elemzett kép/s.
- Legalább 15 minta, legalább 80% teljesen jó képkocka és jó zárókép kell a PASS-hoz.
  Egy teljesen jó képen mind a hét elemnek meg kell felelnie. Az üres képek is
  beleszámítanak a hibákba. Egy másodpercnél nagyobb mintavételi kiesés vagy kevés
  minta esetén az eredmény INCONCLUSIVE, nem PASS.
- Vizsgálatonként helyi MJPEG AVI biztonsági felvétel és SQLite-eredmény.
  A videó az elemzett képeket tartalmazza; névleges lejátszási sebessége a `--fps`.
  Terhelés miatti képkieséskor a videó időtartama rövidebb lehet a valós vizsgálatnál;
  a tényleges időt a JSON `duration_seconds` mezője adja meg.
- Egy eredmény termékbehelyezésenként; új ciklushoz legalább 0,7 s detektált elem
  nélküli idő kell. A v2 ciklus az első színes alkatrészjelölt felismerésekor indul,
  nem vár szereléskész jelre vagy mind a hét elem jelenlétére.
- Külön, képfeldolgozást nem blokkoló parancs a mentett eredmények HTTP-küldéséhez.

**Rögzített kamera és közel azonos termékirány** szükséges. A v2 kis elfordulást,
eltolást és egyenletes skálaváltozást közösen illeszt a hét elem alapján.
Tetszőleges forgatást, tükrözést és perspektívaváltozást nem kezel. A kalibrált
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

## Kalibráció – kódmódosítás nélkül

Az új alapértelmezett módban ismert, jó A/B/C/D termék kell. A képen lévő
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
# Rendelési bemenetből, most JSON-fájllal:
python -m qc_station run --profile profiles/cica-v2.json --once --order-context examples/order-context.json
```

`--expected-variant` nélkül bármelyik ismert, jól összeállított variáns megfelelhet.
Megadott elvárásnál a felismert variáns ettől függetlenül tárolódik, de eltéréskor FAIL.
A három másodperces ablakban a felismerésnek is legalább 80%-ban azonosnak kell lennie,
és a záróképnek egyeznie kell vele; megoszló variánsok esetén INCONCLUSIVE.
A rendelési JSON egy konkrét termék pillanatképe, ezért csak `--once` mellett használható;
új termékhez új bemenet kell. Adatbázis-lekérés ebben a változatban még nincs.

`Q` kilép az ablakos futásból. Kameraolvasási hiba/megszakítás során az aktív vizsgálat
INCONCLUSIVE eredményt kap, ha a háttértár írható; egy processzkilövés vagy áramkimaradás
közbeni aktív ciklus még elveszhet. A már SQLite-ba mentett eredmények megmaradnak.

`--seconds`, `--fps`, `--min-samples`, `--width`, `--height` állítják a futást.
Az alapérték 640×480, 10 FPS, 3 s, 15 minta. Alacsony FPS mellett a minimális
mintaszámot/időablakot is összehangoltan kell beállítani. `--no-video` kikapcsolja a
videómentést, de a három másodperces ellenőrzést nem. A teljes felvétel nincs RAM-ban:
a kód egy képkockát, munkamaszkokat és összesítő számlálókat tart.

Eredmények: `runtime/results.sqlite3`; videók: `runtime/videos/`.
Az alapértelmezett 500 videós határnál a program megáll, nem töröl korábbi bizonyítékot.
A határ `--max-videos` kapcsolóval módosítható. A SQLite-adatbázis archiválását és a
szabad tárhely felügyeletét az üzemeltetésben meg kell oldani; ezek nem korlátos méretűek.
A fejlesztői profilok és mérési adatok nincsenek Gitbe véve.

## Digital twin kapcsolat

A jelenleg vizsgált digital_twin **nem rendelkezik QC-eredményt fogadó végponttal**.
Az új küldő kész egy ilyen végponthoz, de a fogadóoldali bővítés még szükséges.
Nincs automatikus termékbefejezés vagy rendelésmódosítás.

```bash
# Csak az integrációs dokumentum szerinti fogadó megvalósítása után:
python -m qc_station flush --endpoint https://YOUR-HOST/qc/inspections
```

A `QC_API_KEY` környezeti változó opcionális `X-API-Key` fejlécet ad.
Hálózati hibánál a rekord helyben marad; a parancs újra futtatható.
A fogadónak az `inspection_id` alapján duplikációmentesnek kell lennie.
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
