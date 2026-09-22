# Alkatrészalapú felismerés és pontozás (v2)

Az alap előírt színe, geometriája és a régi kézi maszkhidak nem szerepelnek a v2 feldolgozásban.
Egy jó minta hét, név szerint kijelölt poligonjából a rendszer geometriát és
színosztályokat tanul. Az új profil Lab-palettát tartalmaz a három alkatrészszínhez
és a háttérhez, régi v2 profiloknál továbbra is a HSV-tartományok működnek.
A recept az A–D ábra színelosztását követi, narancs helyett pirossal.

## Feldolgozás

1. A kijelölt munkaterületen külön piros, sárga és kék maszk készül. Lab-palettánál
   a háttér is versengő osztály: legközelebbi palettapont, kalibrált távolságlimit és
   a két legközelebbi osztály közötti különbség dönt. Kétértelmű pixel nem megbízható
   színbizonyíték. Új modellnél 3×3 zárás kezeli az apró kieséseket, majd 3×3 nyitás
   távolít el zajt. Nincs feltétel nélküli konvexburok-kiegészítés, alakjavítás vagy
   tűrésemelés a piros darabok kedvéért.
2. Külön színkontúrokból alkatrészjelöltek készülnek. A munkaterület széléhez érő
   foltok háttérnek számítanak. Jelentős plusz kontúr is hibának számít.
3. A geometriai illesztés színtől független, egyszer használatos párosítás:
   a név szerinti hét helyre legfeljebb egy-egy kontúr rendelhető. A kezdeti
   pozíció/terület alapú párosítás közeli kameraállást feltételez.
4. A középpontokból közös eltolás/forgatás/egyenletes skála illeszkedik.
   Ez nem enged elemenkénti külön forgatást: az egyedi hibák megmaradnak.
   Nincs perspektíva- vagy tükörtranszformáció, tetszőleges termékirány-felismerés.
5. A rendszer az elemek területét, alakját, középpontját, élszögeit és az elemek
   közötti eltolásvektorokat ellenőrzi. A színelosztás adja a felismert variánst;
   a gyártási megfelelőség ettől külön eredmény.

Azonos színű érintkező részek vagy teljesen azonos megjelenésű háttér/darab nem
választható szét biztosan pusztán ezzel a szegmentációval. Látható szín-, kontúr-
vagy hézaghatár kell. Ezt a korlátot az alapszín-függetlenség nem szünteti meg.
A kamera alatt a termék ne forduljon el nagy szögben a referenciához képest;
helyesen illesztett, külön kameraállásban készült új kalibráció szükséges.

## Élek kapcsolata

A körbejárási sorrendben rögzített poligonélek alapján minden elempárnál
referenciakapcsolatok készülnek. A jó mintán legfeljebb 6°-ra párhuzamosnak,
illetve 6°-ra merőlegesnek látszó élpárok bekerülnek a profilba. A megfigyelt
kontúrok élei ciklikus megfeleltetéssel kapcsolódnak a referenciaélekhez.

Az iránykülönbség modulo 180°, **nem modulo 90°**: párhuzamosnál 0°, merőlegesnél 90°
az ideális érték. Alapértelmezett tűrés 10°. Hiányzó vagy hibás élmegfeleltetés
nem kap automatikusan jó pontot. Az egyedi elem iránya és az elemek egymáshoz
viszonyított élei külön is ellenőrzöttek.

## Pontszám és döntés

A `quality_score` 0–100-as diagnosztikai érték:

| Összetevő | Súly |
|---|---:|
| Elemenkénti geometria: terület, alak, középpont, irány | 40% |
| Párhuzamos/merőleges élkapcsolatok | 25% |
| Elempárok relatív helyzete | 20% |
| Recept szerinti színmegfelelés | 15% |

Hibamértéknél a részpont `max(0, 1 - hiba / (2*tűrés))`, a színpont a belső
pixelek megfelelő színtartományba eső aránya. Az összesítés az egyes komponenseken
belüli átlag. A pontszám nem valószínűség és nem iparilag hitelesített minőségi index.

A PASS nem pusztán az összpontszám küszöbölése: pontosan hét elem, ismert és
szükség esetén a rendelésnek megfelelő variáns, minden elem és minden megadott
kapcsolat tűrésen belül kell legyen. Egy jó átlag nem rejthet el egy hibás elemet.

Induló tűrések: normalizált pozíció 0,06 (a termék hosszabb befoglaló méretéhez
viszonyítva), relatív területhiba 30%, OpenCV I1 alakeltérés 0,2, szöghiba 10°,
színmegfelelő pixelek aránya legalább 65%. Ezeket hibás és jó laboros mintákból
finomítani és külön tesztkészleten ellenőrizni kell; a rajz nem helyettesíti ezt.

## Időablak és rendelés

A v2 jelenlét az első, munkaterületen talált színes alkatrészjelölt alapján indul.
Ez nem jelenti a szerelés végét; a terméket készen kell a mérőhelyre tenni, vagy
később külső PLC/MES trigger szükséges. A régi `base_present` eredménymező
kompatibilitási okból tovább szerepel, a v2-ben ugyanazt jelenti, mint az `object_present`.

A három másodperces eredmény tárolja a variánsszavazatokat, a stabil felismert
variánst, az elvárt variánst és az átlagos pontszámot. Ha a termék a vizsgálat közben
megváltozik, nincs garantált fizikai azonosítás; az NFC/PLC-integráció továbbra is szükséges.

Az `OrderContext` a jövőbeli API-adapter határa. Most a JSON-fájlból ellenőrzi az
order_id, product_instance_id és expected_variant mezőket. A fájl nem adatbázis-szinkron:
nincs automatikus frissítés, rendelési sor kiválasztás, jogosultság vagy lejáratellenőrzés.
Később ezeket a digital_twin oldali szerződésben kell rögzíteni. A kameraállomásnak
nem kell közvetlen SQL-hozzáférés; a backend adhat ellenőrzött termék/recept azonosítót.

## Lab-paletta erőforrásigénye és reprodukálható hibák

Osztályonként legfeljebb 4096 kalibráló pixel és nyolc k-means középpont szerepel.
A k-means csak kalibrációkor fut. A kameraciklus palettapont-távolságokat számít a
munkaterületen, néhány ROI méretű munkatömbbel. Ez többlet CPU-költség a HSV-hez
képest; a cél-Pi-n a benchmarkot újra kell futtatni. Új csomag vagy neurális háló nem kell.

Az elutasított referencia nyers képe, sarkai és jelentése menthető és `--resume`
kapcsolóval újranyitható. A `report.json` szándékosan nem aktív profilséma;
nem kerülhető meg vele a referenciaellenőrzés. A régi küszöbök és az összes geometriai
feltétel megmaradt. A környezet változásával új háttérminták válhatnak szükségessé.
