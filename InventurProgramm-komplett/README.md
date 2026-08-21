# Inventurprogramm

Eine mobile Webapp für ausleihbare Office-Geräte. Jedes Gerät erhält einen QR-Code. Nach dem Scan wird das Gerät automatisch erkannt; der Benutzer trägt nur seinen Namen ein.

## Funktionen

- Admin-Anmeldung und Geräteübersicht
- Geräte anlegen und bearbeiten
- Attribute: Gerätename, Typ, Betriebssystem, letztes Update, Setup, Standort und Zustand
- QR-Code pro Gerät
- Ausleihe und Rückgabe per Smartphone
- Sperre bei aktiver Ausleihe, offenem Setup, Service oder Defekt
- vollständiger Ausleihverlauf für den Admin
- kein Benutzername auf der öffentlichen Scan-Seite
- SQLite ohne ORM; SQL steht direkt in `app/database.py` und den Routen

## Start auf macOS

Im VS-Code-Terminal im Projektordner:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
fastapi dev app/main.py
```

Öffne anschließend `http://127.0.0.1:8000/admin/`.

Die Demo-Zugangsdaten stehen in deiner lokalen `.env`. Ändere `ADMIN_PASSWORD` und `SESSION_SECRET`, bevor die App öffentlich erreichbar ist.

## HTTPS und QR-Codes

Lokal ist HTTP korrekt. Für die öffentliche Version setzt du in `.env`:

```env
PUBLIC_BASE_URL=https://inventur.deine-domain.de
FORCE_HTTPS=true
SEED_DEMO_DATA=false
```

`PUBLIC_BASE_URL` wird in die QR-Codes geschrieben. Deshalb muss dort die endgültige HTTPS-Adresse stehen. In Produktion sollte HTTPS an einem Reverse Proxy oder Hosting-Dienst beendet werden; dieser leitet an FastAPI weiter.

## Datenbank verschieben

Standardmäßig liegt `inventory.db` im Projektordner. Mit `DATABASE_PATH` kannst du sie später verschieben:

```env
DATABASE_PATH=/Users/deinname/Daten/inventory.db
```

## Wichtige Dateien

- `app/database.py`: Verbindung, Tabellen und Beispieldaten
- `app/routes/admin.py`: Adminbereich und QR-Codes
- `app/routes/devices.py`: öffentliche Ausleihe und Rückgabe
- `app/templates/`: HTML-Oberfläche
- `app/static/styles.css`: responsives Design
- `app/main.py`: startet die Webapp

## Produktion

Für einen echten Firmeneinsatz fehlen je nach Anforderungen noch Benutzerkonten/SSO, Rollen, Backups, Protokollierung und Datenschutzregeln. Die vorhandene Version ist ein vollständiger, lauffähiger MVP.

