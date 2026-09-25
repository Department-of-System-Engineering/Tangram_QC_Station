# Közvetlen kapcsolat a digitális iker API-jával

```text
Raspberry / qc_station ── HTTP API ── digital_twin ── meglévő közös adatbázis
```

Az állomás képet elemez és mérést küld. A digitális iker választ terméket a
nyomonkövetésből, kezeli a variánstérképet, tárolja a mérést és a hibákat,
valamint módosítja a termék és rendelés állapotát. Az állomáson nincs adatbázis,
adatbáziskapcsolat vagy külön QC-szerver. Minden rendszer központi adatforrása
továbbra is a digitális iker meglévő adatbázisa.

## Üzemmódok

- `--mode manual`: a kamera automatikusan felismeri az A–D variánst, pontozza
  a terméket. Beállított API mellett a mérés az ikerbe kerül, termék/rendelés
  hozzárendelése és állapotváltás nélkül.
- `--mode order`: az API-tól kapja az érkezési eseményt, termékazonosítót és
  elvárt variánst. Az észlelt variáns ettől független: eltéréskor FAIL.
  Érvényes központi azonosítás nélkül nem indít mérést.

A kamera legalább öt elem észlelésekor küld `product_present: true` jelzést a
`POST /qc/claim` kérésben. Az iker elsőként a meglévő `visual_qc / arrived`
érkezést használja. Ennek hiányában a soron következő nyitott rendelési darabot
választja: prioritás, rendelésdátum, tételpozíció és darabsorrend szerint.
A kamera variánsa nem választ másik rendelést. Gyártási előzmény nélkül is működik:
az iker a már létrehozott, várakozó termékpéldányhoz valódi QC-érkezést rögzít,
tálca és korábbi gyártási események nélkül. A közvetlen QC utáni rework vagy
INCONCLUSIVE darab új érkezéssel ismét vizsgálható. Több nyomon követett QC-érkezés
továbbra is hiba. Egy fizikai QC-területhez egyszerre egy nyitott feladat tartozhat.

`--claim-source tracking` elhagyja az új mezőt, és megköveteli a korábbi
nyomonkövetési érkezést. Az alapértelmezett új működéshez a digitális iker
`app/qc/api.py` fájlját is frissíteni kell, és az API-folyamatot újraindítani.
Nincs új adatbázistábla vagy állomásoldali adatbázis. Régi API extra-mező hibájánál
nem történik automatikus visszaváltás a más jelentésű nyomonkövetéses működésre.

A foglalás után az első észlelt alkatrész indítja a mintavételt. Megmaradt a
3 másodperces ablak, 15 minimális minta, 80%-os szavazás, jó zárókép és
biztonsági videó. Új ciklushoz legalább 0,7 másodperces üres munkaterület kell.

## Központi állapotváltás

| Rendeléses eredmény | Digitális iker művelete |
| --- | --- |
| PASS | termék `done`, raktári done esemény, tálca felszabadítása, darabszám frissítése |
| FAIL | termék `rework`, tálcahozzárendelés megmarad |
| INCONCLUSIVE | mérési hiba naplózása, változatlan termékállapot |

Az iker egy tranzakcióban végzi az eredménymentést és az állapotváltást.
Egy teljesült rendelés státusza továbbra is `completed`; a régi `completed`
termékek is késznek számítanak. Rework visszaútját a meglévő nyomonkövetés
választja `nextStationKey: assembly1` vagy `assembly2` értékkel. Minden új
vizsgálathoz új `arrived` esemény kell, INCONCLUSIVE utáni ismétléshez is.

A központi `qc_inspections` tábla tárolja a teljes mérést, átlagpontszámot,
azonosítókat, időket és kalibrációt; `qc_findings` a kategorizált eltéréseket.
Kategóriák: placement, orientation, alignment, shape, size, count, color,
variant, measurement. A mintasor átmeneti hibái PASS mellett is megjelenhetnek;
a részletes alkatrész-metrikák és élkapcsolatok a záróképből származnak.
`video_path` helyi fájlhivatkozás, a biztonsági videó nem kerül feltöltésre.

## API az iker meglévő portján

Normál végpontokon `X-API-Key` kell, az iker `INBOUND_API_KEY` értékével.

- `POST /qc/claim`, `{"station_id":"tangram-qc-01"}`: foglalás vagy `null`.
- `POST /qc/results`: teljes mérési JSON; `Idempotency-Key` = `inspection_id`.
  Siker: 200 és `{"inspection_id":"...","accepted":true,"duplicate":false}`.
- `GET /qc/results/{inspection_id}`: központi mérés, vagy 404, ha még nincs átvéve.
- `GET /qc/variants`: központi terméktípusok és elvárt variánsok.

Adminvégpontokhoz az iker külön `MAPPING_ADMIN_API_KEY` kulcsa kell:

- `PUT /qc/variants/{product_type_id}`, `{"variant":"A"}`: variánstérkép.
- `POST /qc/jobs/{inspection_id}/cancel`, `{"reason":"Operator removed tray"}`:
  elakadt foglalás auditált kezelői lezárása. Nem módosít termékstátuszt.
  Előtte állítsd le a klienst és ellenőrizd a függő küldéseket. Lezárt foglalás
  késői eredménye elutasításra kerül; új vizsgálathoz új érkezés kell.

## Hálózati hibák és újraindítás

A helyi `runtime/delivery/pending/<inspection_id>.json` csak küldési biztosíték,
nem terméknyilvántartás. Kiírása átnevezéssel atomikus. A fájl csak az adott
mérés pozitív visszaigazolása után kerül a `sent` mappába. Elveszett HTTP-válasznál
ugyanazt a fájlt küldi újra: az iker azonos azonosító/tartalom esetén nem hajt
végre újabb állapotváltást. Eltérő tartalommal újrahasznált azonosító hiba.

Hálózati hiba, 5xx, 408 vagy 429 esetén a folyamatos futás újrapróbál.
Más 4xx, hibás kontextus vagy hibás visszaigazolás esetén megáll és megtartja
a függő fájlt. Új rendelés foglalása csak a függő fájlok átvétele után lehetséges.
HTTP-kérés mintavétel közben nem fut. Egy megszakított `--once` küldés újraindítással
vagy külön `flush` paranccsal folytatható. A még be nem fejezett mérés hirtelen
áramkimaradáskor elveszhet; erre az iker soha nem kap PASS-t.

```bash
# Leállított kamerás program mellett:
python -m qc_station flush --endpoint http://twin-server:8000/qc/results --directory runtime/delivery
```

A pending fájlokat ne módosítsd/ne rendeld át más termékhez. A sent másolatok
és helyi videók archiválhatók. A régi helyi rendelési JSON kapcsolók csak
offline diagnosztikára valók; nem helyettesítik az API rendeléses foglalását.

Beállítás: [deployment.md](deployment.md).
