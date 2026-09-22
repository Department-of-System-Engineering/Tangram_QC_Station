# Az eredeti QC megoldás áttekintése

Ez a dokumentum az eredeti program és az első, alapmaszkos változat értékelése.
A 2026-09-22-én bevezetett, alap színétől független v2 megoldás és annak korlátai
a [variants.md](variants.md) dokumentumban szerepelnek.

Forrás: [Hullo0215/QC_Station_Tangram](https://github.com/Hullo0215/QC_Station_Tangram),
helyi forrásverzió: `cdd6a16a95c614b4d47b499be5b49c26c0285896`.
Az öt Python-fájl végigolvasva; az új projekt eredetileg üres Git-munkakönyvtár volt,
eltérő originnel. A korábbi programok referenciaként a `legacy/` könyvtárba kerültek.

## Hibák és következményeik

| Súly | Hely | Megállapítás | Következmény / új megoldás |
|---|---|---|---|
| Kritikus | `qs_station_fix_vs1.py`, `pozició ellenőrzés qs.py`: `m_avg >= QUALITY_THRESHOLD` | 0,4 feletti összpontszám elég; nem szükséges mind a hét elem. Három tökéletes elem is 3/7 ≈ 0,43. | Hiányos termék OK lehet. Most teljes képkockánként hét megfelelő elem kell. |
| Kritikus | Ugyanott: `if found > 0: score_history.append(...)` | Nulla találat nem kerül az átlagba. | Régi jó eredmény fennmarad. Most minden vizsgálati minta számít. |
| Magas | Ugyanott: `abs(angle1-angle2) % 90` | A merőleges és párhuzamos élek egyaránt maximális pontot kaphatnak. | Nem helyes párhuzamossági vizsgálat. Az új referencia-illesztés kontúrátfedést, alakot és helyzetet mér. |
| Magas | Ugyanott: legközelebbi alapél | Egy alkatrészhez egy közeli él alapján rendelt pontszám nem bizonyítja a teljes alak/helyzet megfelelőségét. | Teljes referencia-kontúrhoz hasonlítás szükséges. |
| Magas | `qs station.py`: EXPECTED_PARTS | Két hiányzó vessző miatt a fájl szintaktikailag hibás. | A fájl nem indítható; az új modul önálló, a legacy csak referencia. |
| Magas | `qs station.py`: belső párosítás | Ugyanaz a kontúr több elvárt elemhez felhasználható; a megadott min_area nincs ellenőrizve. | Téves darabszám. Az új párosítás egyszer használ egy detektálást. |
| Magas | `qs test.py`: results | A státuszfelirat lehet OK, de a visszaadott results.status FAIL marad; found_count sem frissül. | Külső integráció ellentmondó adatot kapna. Most egy strukturált eredmény az igazságforrás. |
| Közepes | Fix pixelterület-intervallumok | Felbontás, távolság és skálázás függvényei, részben átfedik egymást. | Alap-befoglalóhoz normalizált geometria és jó mintából tanult referencia. |
| Közepes | `calibration.py`, `qs test.py` | 2× szélesség és magasság négyszeres pixelszámot jelent, új kamerarészlet nélkül. | Felesleges Pi-terhelés. Új rendszer csak lefelé méretez, korlátozza a feldolgozási sebességet. |
| Közepes | `calibration.py` | Megmutatja a kontúrterületeket, de nem ment profilokat és nem tanul elemenkénti színeket. | Interaktív HSV és automatikusan mentett geometriai/színprofil. |
| Közepes | Három másodperces várakozás + 10 elemű deque | Nem ment felvételt, és nem feltétlenül a teljes három másodpercről dönt. | Monoton idővel mért ablak, minden minta összesítése és biztonsági videó. |
| Közepes | Globális állapot, imshow az elemzőben | Nehéz fej nélküli futtatás, tesztelés és több ciklus biztonságos elkülönítése. | Tiszta elemzőfüggvény, külön állapotgép, opcionális GUI. |

## Tervezési döntések és határok

Maradt a könnyű OpenCV/NumPy megoldás; nincs neurális háló vagy GPU-követelmény.
Az új geometria referenciaalapú: azonos kameraállásnál kontúrátfedés, relatív terület,
pozíció és Hu-momentumokon alapuló alakeltérés együtt dönt. A szín a kontúr belsejének
erodált maszkjából számított HSV-tartomány és megfelelési arány.
Az alap felismerése továbbra is színalapú; a legnagyobb megfelelő kontúr kiválasztása
kontrollált munkaterületet igényel. Azonos színű zavaró tárgyak, egymáshoz érő elemek,
tartós csillogás és takarás továbbra is hibaforrások. A több képkocka időben változó
zavaron segíthet, tartósan elveszett információt nem állít helyre.

A pozícióalapú egyszer használatos párosítás szándékosan egyszerű. Szorosan egymás
mellett lévő, azonos alakú elemeknél és jelentős elmozdulásnál laboros validáció kell;
nem általános, tetszőleges elrendezésű objektumfelismerő. A profil hét elemet vár,
de nem ellenőrzi, hogy a kalibráló valóban hibátlan terméket választott-e.

Pi-n a valós időt főleg CPU, kameraillesztő, expozíció, felbontás és videóírás
határozza meg. A mostani 10 FPS célérték, nem mért hardvergarancia. A képtárolás
képkockánként történik; a feldolgozó RAM-igénye nem nő a videó hosszával.
Az SQLite-adatbázis viszont hosszú távon nő: archiválási/megőrzési szabály kell.

## Laboros elfogadási vizsgálat

1. Rögzített kamera, teljes termék a képben, stabil expozíció/fehéregyensúly,
   az új LED-del újrakalibrált profil. A kamera beállításait a kamera saját eszközével
   kell rögzíteni; a program nem garantál illesztőfüggetlen expozícióvezérlést.
2. Külön tesztkészlet: jó termékek, minden egyes elem hiánya, cserélt színek,
   rossz alakok, elfordulás, eltolás, plusz elem, kéz/takarás, üres vagy levágott alap.
3. A küszöböket tanító mintán állítani, a téves elfogadás és elutasítás arányát
   ettől független mintákon mérni, mindkét világítással.
4. Pi-n legalább 30 perc futás, videóírással; elemzési p95, ciklusidő, mintaszám,
   CPU/RAM, hőmérséklet és tárhely figyelése. Egyeztesd a gyártási taktusidővel.
5. Kamera kihúzása, programleállítás, háttértárhiba és hálózati kiesés próbája.
   Egyiket se lehessen hibátlan termékként értelmezni.
6. A fogadó QC API elkészülte után duplikált POST és elveszett válasz próbája,
   termék/NFC-azonosítóval és üzemileg jóváhagyott továbbengedési logikával.

Nem áll rendelkezésre valódi laborfelvétel, csatlakoztatott célkamera vagy Pi-mérés;
ezért az üzemi pontosság és az end-to-end teljesítmény jelenleg nincs validálva.
