# Elvégzett szoftveres ellenőrzés

## Közvetlen digitálisiker-API, 2026-09-24

- Állomás: **51 sikeres teszt**, adatbázis nélkül. Valódi helyi HTTP-kapcsolaton
  elveszett válasz utáni újraküldés, hibás visszaigazolás, hibás rendelési kontextus,
  egymást követő termékek, variánstévesztés és kézi felismerés ellenőrizve.
- A helyi digitális ikerben **15 sikeres QC API-teszt**, elkülönített PostgreSQL-en:
  tranzakciós done/rework váltás, duplikáció, stale érkezés elutasítása, rollback,
  jogosultságok, központi variánstérkép, valódi közös kapcsolatpool és migráció.
- A meglévő digitálisiker-API betöltése és QC/production végpontjainak regisztrációja
  sikeres; a meglévő dashboard szerződésének **7 tesztje sikeres**.
- Az állomásnak nincs SQLite/PostgreSQL/SQLAlchemy függősége, adatbáziskapcsolata,
  külön szervere vagy Docker-konfigurációja. Függő és visszaigazolt JSON-küldési
  fájlokat, illetve a meglévő biztonsági videót tárolja.

Környezet: Windows x64, Python 3.14.3, OpenCV 4.14.0, NumPy 2.5.3.
Éles központi adatbázisba nem történt írás; a tesztadatbázis csak a backend
ellenőrzésére szolgált. A Pi/kamera/PLC fizikai végpontok közötti laborpróba,
sebességmérés és optikai kalibráció továbbra is helyszíni ellenőrzést igényel.

## Korábbi kontúr- és kalibrációs ellenőrzés

Az alábbi 2026-09-22-i feljegyzés történeti: az akkori SQLite-tárolást azóta
felváltotta a küldési JSON-fájl és a digitális iker központi mentése.

Dátum: 2026-09-22. Környezet: Windows x64, Python 3.14.3,
OpenCV 4.14.0, NumPy 2.5.3; a projekt saját `.venv` környezete.

`python -m unittest discover -s tests -v`: **42 teszt sikeres**.

A kontúrjavítás négy regressziós tesztje: kis háttérfoltok kizárása valódi plusz elem
elutasításával együtt; kis saroklevágású háromszög élillesztése; mély bemetszés és
téves csúcsszám elutasítása; nem mérhető szög null értéke és `edge_geometry` hibája.
A felhasználó második maszk-képernyőképén a kis fül kontúrja 1044 pixel területű,
az egyszerű közelítés négyszögnek veszi. A hosszú élekből illesztett háromszög területe
ehhez képest +2,18%; a nyers kontúr alak/terület adatai nem változnak. A teljes eredeti
kalibráció nem reprodukálható a nyers frame.png és selection.json nélkül.

A Lab-palettás javítás négy további tesztje: halvány piros darab és hasonló rózsaszín
háttér elkülönítése (ugyanazon mintán a régi HSV elutasít); darab eltávolításának
elutasítása; kétértelmű palettaegyezés kizárása; palettavalidáció; nyers kép és sarkok
veszteségmentes diagnosztikai mentése/visszaolvasása, elutasított jelentés nem aktív profil.

A felhasználó 2026-09-22-i képernyőképén közelítően újrakijelölt sarkokkal is történt
diagnosztika: a Lab-modell után a fej és a középső háromszög elemenkénti hibái eltűntek.
A teljes kép továbbra is elutasított (plusz kontúrok és élkapcsolatok); feliratokkal és
zöld kijelöléssel szennyezett képernyőkép, ezért nem szolgál elfogadási bizonyítékként.
A kép nem került a tesztkészletbe; a nyers kameraképes validáció továbbra is szükséges.

- Referenciaminta elfogadása; eltolt/kicsinyített minta elfogadása.
- Hiányzó és plusz elem, rossz szín, módosított alak/helyzet elutasítása.
- Üres és levágott alap elutasítása; érvénytelen kalibráció elutasítása.
- Vörös HSV-tartomány 179/0 átfordulása.
- Három másodperces ciklus, egyetlen eredmény, eltávolítás utáni újraélesítés.
- Üres képkockák, rövid villogás, rossz zárókép, elégtelen mintaszám és mintavételi szünet.
- Helyi eredmény újranyitás utáni megmaradása; szimulált HTTP-hiba utáni újraküldés,
  változatlan idempotenciaazonosító és siker utáni kézbesítési jelölés.
- Teljes kameraciklus szimulált bemenettel és órával, de valódi SQLite- és MJPEG AVI-írással;
  az AVI visszaolvasása és képkockaszámának ellenőrzése.
- Kameraolvasási hiba és KeyboardInterrupt esetén INCONCLUSIVE mentés és erőforrás-felszabadítás.
- Két mesterséges alapvonalszakadással reprodukált 5/7 detektálás; rövid összekötésekkel
  7/7 kalibráció és sikeres vizsgálat, majd hiányzó elem és üres kép elutasítása.
- Állítható automatikus réslezárás kalibrációban és mérésben; kézi összekötés mindkét
  végpontjának színellenőrzése; hibás konfiguráció és eltérő képméret elutasítása.
- V2: A–D felismerés négy különböző háttéren; tanítás mind a négy mintavariánsból.
- V2: rendeléstől független felismert variáns, elvárt variánstól eltérés elutasítása,
  nem ismert színkombináció elutasítása.
- V2: hiányzó/plusz elem, összeérő azonos színű részek, üres kép, egyedi eltolás és
  egyedi forgatás; kis közös forgatás/eltolás/skálaváltozás elfogadása.
- V2: párhuzamos és merőleges szögek megkülönböztetése, szögpontszám romlása,
  érvénytelen profil és eltérő képméret elutasítása.
- V2: keveredő variánsok időablaka nem PASS; validált rendelési JSON és teljes
  szimulált kameraciklus, SQLite-ba mentett order_id/termékazonosító/elvárt és felismert
  variánssal; A rendelés alatt B termék FAIL eredménnyel.

A CLI `--help` sikeresen lefutott. A tesztek nem nyitottak kamerát vagy GUI-t,
és nem küldtek adatot élő backendbe. Az interaktív kalibráció kezelhetősége,
a laborvilágítás alatti felismerés, a Raspberry Pi sebessége és a fogadó backend
integrációja **még nincs igazolva**. A laboros elfogadási terv a `review.md` fájlban található.
Az új résjavítást szintetikus képeken teszteltük; a felhasználó képernyőképeinek
vizuális értékelése nem helyettesíti a nyers kameraképen végzett helyszíni próbát.
Ugyanez vonatkozik az új v2 variánsfelismerésre. A kézi sarokkijelöléses kalibráció
GUI-ja nincs automatizáltan végigkattintva, de a profilalkotás és mentés előtti
automatikus referenciaellenőrzés magja tesztelt.
