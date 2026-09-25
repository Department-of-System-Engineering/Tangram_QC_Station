# Natív telepítés Raspberryre

Az állomás önálló Python-program, OpenCV és NumPy függőségekkel. Nincs saját
adatbázisa, adatbázis-jelszava, webszervere vagy Docker-szolgáltatása.

## Telepítés és színmintavétel

64 bites Raspberry OS és OpenCV/V4L2 által elérhető kamera esetén:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m qc_station sample-colors --camera 0 --output profiles/cica-v2.json
```

Ha az adott Pi/Python verzióhoz nincs OpenCV wheel, a rendszer `python3-opencv`
és `python3-numpy` csomagja használható `--system-site-packages` virtuális
környezettel. A színmintavétel ablakos munkamenetet igényel. SPACE után adj
piros/sárga/kék és háttérmintákat; nem kell alakzatsarkokat kijelölni. A fix
sablon a 2026-09-25-i, 640×480-as kameranézethez tartozik. Más kameraállásnál
másik fix sablon vagy az opcionális teljes `calibrate` mód használható.

## Kapcsolat a meglévő digitális ikerrel

Előbb a digitális iker frissített API-ját kell telepíteni. A normál `db-init`
most a saját közös adatbázisában létrehozza a QC-táblákat is. Ez kizárólag
szerveroldali feladat, nem a Raspberry telepítésének része. A backend leírása
a `digital_twin/docs/qc_station.md` fájlban van. Nincs külön QC-port/szolgáltatás.

A központi API `GET /qc/variants` végpontja listázza a valódi terméktípusokat.
Az adminisztrátor a `PUT /qc/variants/{product_type_id}` végponton, például
`{"variant":"A"}` törzzsel állítja be az A–D megfeleltetést. Ehhez az iker
`MAPPING_ADMIN_API_KEY` kulcsa kell; ezt ne add oda az állomásnak.

Az állomás normál API-kulcsa az iker `INBOUND_API_KEY` értéke:

```bash
export QC_API_KEY='A_DIGITALIS_IKER_API_KULCSA'
export QC_TWIN_URL='http://twin-server:8000'
# Kézi mód: felismerés és mérésküldés, rendelésmódosítás nélkül.
python -m qc_station run --mode manual --profile profiles/cica-v2.json
# Rendeléses mód: a QC-hez beérkezett termék alapján.
python -m qc_station run --mode order --profile profiles/cica-v2.json --headless
```

A projekt gyökerében lévő `.env` fájlból automatikusan beolvassa a `QC_API_KEY`
és `QC_TWIN_URL` értékét. A `.env.example` másolható kiindulási mintának.
A már exportált változók elsőbbséget élveznek; a `--twin-url` ezeket is felülírja.
A kulcs a fájlban is `QC_API_KEY` néven szerepeljen, az értéke az iker
`INBOUND_API_KEY` értéke. Nem kell `source .env` parancsot futtatni.
Hálózat nélküli helyi próbához ne állítsd be a `QC_TWIN_URL` változót, és
használj `--mode manual` módot. Ilyenkor csak a helyi JSON és videó készül el.
Ugyanazzal a runtime könyvtárral egyszerre egy kamerás program vagy küldő futhat.

Windows PowerShell alatt a beállítás például:

```powershell
$env:QC_API_KEY='A_DIGITALIS_IKER_API_KULCSA'
$env:QC_TWIN_URL='http://twin-server:8000'
```

## Átállás és ellenőrzés

A korábbi `results.sqlite3` fájlt az új verzió nem nyitja meg, nem módosítja
és nem használja. Ha maradt benne korábbi adat, archiváld; nem kerül automatikusan
új rendeléshez hozzárendelve elküldésre. Az új küldések a `runtime/delivery/`
könyvtárba kerülnek. Az állomás függőségei csak a `requirements.txt` fájlból kellenek.

```bash
python -m unittest discover -s tests -v
python scripts/benchmark.py --image jo_termek.png --profile profiles/cica-v2.json
```

A tesztekhez sem kell adatbázis vagy digitálisiker-szerver: helyi teszt-HTTP
végpontot használnak. A sebességet és a felismerést viszont az adott Pi-n,
kamerával, jó és hibás darabokkal is ellenőrizni kell. A szoftvertesztek nem
helyettesítik az optikai kalibráció és a laborban elérhető képfrekvencia mérését.

Helyszíni próba: A–D jó darabok, hibás variáns és elfordított/hiányzó elem,
hálózatmegszakítás, visszatérő rework termék, kamera-megszakítás. A PLC/Node-RED
az eredmény központi átvételéig tartsa a tálcát a kamera alatt.
