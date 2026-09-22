# Kapcsolat a digital_twin rendszerrel

Vizsgált backend commit: `f9dc4b065a765a71ce06efa3fd249bd5a30488d8`.
Források:
- [API](https://github.com/Department-of-System-Engineering/digital_twin/blob/f9dc4b065a765a71ce06efa3fd249bd5a30488d8/app/dashboard/api.py)
- [Sémák](https://github.com/Department-of-System-Engineering/digital_twin/blob/f9dc4b065a765a71ce06efa3fd249bd5a30488d8/app/dashboard/schemas.py)
- [Üzleti logika](https://github.com/Department-of-System-Engineering/digital_twin/blob/f9dc4b065a765a71ce06efa3fd249bd5a30488d8/app/dashboard/service.py)

## Ami már létezik

`POST /products/{product_instance_id}/events` kérése:

```json
{"state":"arrived","processStepId":1,"assetId":1,"time":"2026-09-21T12:00:00"}
```

A state csak `arrived`, `departed`, `done`. Aktív tálcahozzárendelés kell;
lezárt vagy törölt termékhez 409 választ ad. A `done` lezárja a terméket,
felszabadítja a tálcát és módosítja a rendelés teljesülését. Emiatt egy QC PASS
eredményt nem szabad automatikusan `done` eseménnyé alakítani üzleti döntés nélkül.
A sémának nincs minősítési, hibajegyzék- vagy kalibrációmezője, és a végpontban
nincs inspection_id alapú idempotencia.

A SilverFrog adatgyűjtő a DC mérési végpontjait olvassa. Ez nem bizonyítja, hogy
a QC station közvetlenül küldhet adatot arra az interfészre; DC-beírási szerződés
nincs igazolva. A `/asset_predict` pedig karbantartási predikcióhoz tartozik.

## Javasolt, MÉG NEM létező fogadó szerződés

`POST /qc/inspections`, JSON, `X-API-Key`, `Idempotency-Key: <inspection_id>`.
A station bármely konfigurált HTTP(S) URL-re tud küldeni; az útvonal javaslat.
A `flush` külön folyamatként/parancsként fut, nincs hálózati hívás a kameraciklusban.

```json
{
  "schema_version": 1,
  "inspection_id": "64c559d4-09c2-4b87-a24a-4114f64029d9",
  "station_id": "tangram-qc-01",
  "product_instance_id": 123,
  "completed_at": "2026-09-21T12:00:03+00:00",
  "calibration_id": "content-hash",
  "profile_name": "cica",
  "video_path": "runtime/videos/64c559d4-09c2-4b87-a24a-4114f64029d9.avi",
  "result": {
    "status": "PASS",
    "samples": 31,
    "passing_samples": 29,
    "pass_fraction": 0.93548,
    "duration_seconds": 3.05,
    "sampling_gap": false,
    "failure_counts": {},
    "last_frame": {
      "base_present": true,
      "passed": true,
      "found_count": 7,
      "parts": [],
      "reasons": []
    }
  }
}
```

A fenti `parts` lista csak a példa rövidítése; rendes vizsgálatnál hét elemenkénti
metrika/hibajegyzék van benne. Kamera- és megszakítási hibáknál a result rövidített:
`status: INCONCLUSIVE`, `reason`, `samples`. Ezeket is kezelni kell.
A `video_path` helyi hivatkozás, **nem letöltési URL**; a küldő nem tölti fel a videót.

Fogadóoldali követelmények:

1. Külön QC-tábla, egyedi inspection_id, séma- és állomásellenőrzés.
2. Azonos ID és azonos tartalom újraküldésére sikeres válasz új sor nélkül;
   eltérő tartalomnál konfliktus. A hálózat a mentés után, a válasz előtt is megszakadhat.
3. Csak tartós tranzakció után adjon 2xx választ; a küldő ekkor jelöli kézbesítettnek.
4. UTC-idő explicit kezelése: a meglévő backendben több helyen naiv datetime szerepel,
   ezért az időzónát a QC-bővítésben következetesen konvertálni kell.
5. Éles termékhez ellenőrzött product_instance_id és tálcakapcsolat. Az offline
   station null értéket is megenged; ilyen eredmény ne zárhasson le terméket.
6. PASS/FAIL/INCONCLUSIVE külön tárolása; utóbbi újramérést igényel.

A station `--product-instance-id` kapcsolója csak `--once` módban használható.
Így ugyanazt az azonosítót nem használja észrevétlenül több termékre. Folyamatos
üzemben NFC/PLC/MES indítás és azonosítóátadás lesz a következő integrációs lépés.
Az egyszerű optikai jelenlét önmagában nem termékazonosító, és tárgycsere felismerésére
sem megbízható, ha nincs közöttük üres állapot.

A flush egyszerre legfeljebb 100 rekordot küld, kérésenként 5 s timeouttal; az első
hibánál megáll. 4xx esetén javítás szükséges, 5xx/hálózati hiba után ismétlés.
Nincs háttérben automatikus retry-daemon. A receiver idempotenciája kötelező akkor is,
ha több küldő fut vagy egy küldés után a helyi kézbesítési jelölés előtt áll le a gép.
Az API-kulcsot környezeti változóban add meg; éles hálózaton HTTPS használandó.

A digital_twin repository ebben a munkában nem módosult, és éles backendhez
nem történt küldés. Az end-to-end integráció a fogadó elkészültéig nincs igazolva.

## Rendelés szerinti variáns (v2 képfeldolgozás)

A station most fogad `--expected-variant A|B|C|D` beállítást, illetve
`--once --order-context <JSON>` bemenetet. Utóbbi formátuma:

```json
{"order_id": 12, "product_instance_id": 123, "expected_variant": "A"}
```

A validált `OrderContext` adatstruktúra a jövőbeli adatbázis/API-adapter csatlakozási
pontja; tényleges lekérdezés még nincs implementálva. A fájl egyszer, kameranyitás
előtt kerül beolvasásra. Nem tekinthető élő rendelési állapotnak, és egy fájl újbóli
futtatása nem akadályozza meg ugyanazon termék ismételt vizsgálatát. A korrelációt
és az újramérés szabályát a fogadó/vezérlő oldalon kell meghatározni.

A kimeneti esemény új, opcionális mezői: `order_id`, `expected_variant`.
A teljes időablak `result` objektumába `detected_variant`, `expected_variant`,
`variant_votes`, `mean_quality_score` kerül. A `last_frame` tartalmazza a geometriai,
relatív helyzeti, élkapcsolati és színpontokat, továbbá az egyes élkapcsolatok
szöghibáját. V1 profilnál nincs variánsfelismerés; v1-hez rendelési variáns megadása
hibával leállítja a programot.

A pontszám nem valószínűség. Ismert, de a rendeléstől eltérő variáns esetén a valóban
felismert variáns megmarad az eredményben, a minősítés FAIL. Keveredő variánsokat
adó időablak INCONCLUSIVE lehet. Ezek a mezők a javasolt QC-fogadó szerződéséhez
tartoznak; a régi termékesemény-végpont nem használható helyettük.
