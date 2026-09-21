# Tangram QC Station

Kameraalapú, CPU-n futó minőségellenőrzés hét elemből álló tangramhoz.
A korábbi kísérleti programok a `legacy/` könyvtárban változatlanul szerepelnek;
az új belépési pont: `python -m qc_station`.

## Mit tud az új változat?

- Jó mintadarabból tanulható alap-szín, elemenkénti szín, kontúr és helyzet.
- Alapértelmezésben **3 másodperces vizsgálat**, legfeljebb 10 elemzett kép/s.
- Legalább 15 minta, legalább 80% teljesen jó képkocka és jó zárókép kell a PASS-hoz.
  Egy teljesen jó képen mind a hét elemnek meg kell felelnie. Az üres képek is
  beleszámítanak a hibákba. Egy másodpercnél nagyobb mintavételi kiesés vagy kevés
  minta esetén az eredmény INCONCLUSIVE, nem PASS.
- Vizsgálatonként helyi MJPEG AVI biztonsági felvétel és SQLite-eredmény.
  A videó az elemzett képeket tartalmazza; névleges lejátszási sebessége a `--fps`.
  Terhelés miatti képkieséskor a videó időtartama rövidebb lehet a valós vizsgálatnál;
  a tényleges időt a JSON `duration_seconds` mezője adja meg.
- Egy eredmény termékbehelyezésenként; új ciklushoz legalább 0,7 s alap nélküli idő kell.
- Külön, képfeldolgozást nem blokkoló parancs a mentett eredmények HTTP-küldéséhez.

Ez az első megvalósítás **rögzített kamerát és közel azonos termékirányt** feltételez.
Eltolást és közel egyenletes méretváltozást normalizál; tetszőleges forgatást vagy
perspektívaváltozást nem korrigál. Az elemeket a rózsaszín alap maszkjának különálló
belső kontúrjaiból keresi, ahogy az eredeti program: az alapnak el kell választania
az elemeket, és a színük nem olvadhat bele az alap szűrésébe. Eltérő szerelési
kialakításnál más szegmentáció szükséges. Az elfogadási küszöbök induló értékek,
valós jó/hibás mintákkal beállítandók; egyetlen jó kép nem bizonyítja a pontosságot.

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

1. Rögzítsd a kamerát, tedd a jó terméket a teljesen látható munkaterületre.
2. Indítsd: `python -m qc_station calibrate --camera 0 --output profiles/cica.json`.
3. SPACE-szel fagyaszd a képet. Jelölj ki kis, egyenletes **rózsaszín alapfelületet**, ENTER.
4. A HSV csúszkákkal állítsd a maszkot úgy, hogy pontosan hét különálló alkatrész
   kapjon zöld kontúrt. A kék kontúrnak a teljes alapot kell körülfognia.
5. `S` menti a profilt; `Q` megszakítja. A hét számozott elem alakja, helyzete és
   belső színe automatikusan bekerül a profilba. A színszűrés a vörös Hue-átfordulást is kezeli.
6. Indíts ellenőrzést és próbálj ki jó, hiányos, rossz színű, elfordított és elcsúszott mintákat.

Mentett fotó is használható: `python -m qc_station calibrate --image jo_termek.png`.
Másik összeállításhoz ments külön profilt. Az elemek neve és a toleranciák a profil
JSON-jában szerkeszthetők. A mentés felülírja az azonos nevű profilt; az eredmények
tartalomfüggő kalibrációazonosítót tárolnak. A profilokat archiváld a mérési eredményekkel.
Az új LED-világítás felszerelése után új színkalibráció szükséges.

## Futtatás

```bash
python -m qc_station run --profile profiles/cica.json --camera 0 --debug
# Kijelző nélküli Pi:
python -m qc_station run --profile profiles/cica.json --camera 0 --headless
# Egy konkrét, már azonosított termék vizsgálata:
python -m qc_station run --profile profiles/cica.json --once --product-instance-id 123
```

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
python scripts/benchmark.py --image jo_termek.png --profile profiles/cica.json
```

A benchmark a cél-Pi-n futtatandó, reprezentatív fotóval. Csak a képelemzést méri;
a kamera, videókódolás és megjelenítés idejét nem. A 10 FPS-es induló célhoz az
elemzés + videóírás + kijelzés teljes költsége maradjon 100 ms alatt, és hosszabb
üzem alatt is ellenőrizd a mintaszámot, RAM-ot, hőmérsékletet és a CPU-terhelést.
A 8 GB RAM önmagában nem garantál valós idejű működést. Pi-n és laborvideón még
nem történt mérés. A szintetikus tesztek szoftverhibákat keresnek, nem mérik a valódi
selejtészlelési arányt.

Az eredeti forrás részletes értékelése: [docs/review.md](docs/review.md).
