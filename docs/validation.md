# Elvégzett szoftveres ellenőrzés

Dátum: 2026-09-21. Környezet: Windows x64, Python 3.14.3,
OpenCV 4.14.0, NumPy 2.5.3; a projekt saját `.venv` környezete.

`python -m unittest discover -s tests -v`: **16 teszt sikeres**.

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

A CLI `--help` sikeresen lefutott. A tesztek nem nyitottak kamerát vagy GUI-t,
és nem küldtek adatot élő backendbe. Az interaktív kalibráció kezelhetősége,
a laborvilágítás alatti felismerés, a Raspberry Pi sebessége és a fogadó backend
integrációja **még nincs igazolva**. A laboros elfogadási terv a `review.md` fájlban található.
