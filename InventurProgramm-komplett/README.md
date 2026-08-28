# Inventurprogramm

FastAPI-Webapp zur Verwaltung und Ausleihe von Geräten über QR-Codes.

## Aktueller Funktionsumfang

- gemeinsame Anmeldung für Benutzer und Administratoren
- Argon2-Passwort-Hashes und CSRF-Schutz
- Benutzerverwaltung mit Rollen, Kontosperre, Passwortänderung und Löschfunktion
- Geräte anlegen, bearbeiten, deaktivieren und archivieren
- Ausleihe nur durch angemeldete Benutzer
- Rückgabe durch den Ausleiher oder einen Administrator
- QR-Code für jedes Gerät
- Ausleihverlauf und Anzeige überfälliger Geräte
- SQLite-Datenbank mit automatischen Migrationen

### Felder für IT-Geräte

- Handys, PC, Laptops, Notebooks und Tablets
- Betriebssystem
- letztes Update
- Setup abgeschlossen/offen

### Felder für sonstige Geräte

- Kamera, Messgeräte und Werkzeug
- Seriennummer
- letzte technische Prüfung

Anschaffungsdatum, Standort, Zustand und freie technische Daten stehen für
alle Gerätetypen zur Verfügung.

## Erster Start unter Windows

```powershell
cd C:\Pfad\zum\Inventurprogramm
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Danach `.env` öffnen und mindestens diese Werte ändern:

```env
ADMIN_PASSWORD=EIN-SICHERES-STARTPASSWORT
SESSION_SECRET=EIN-LANGER-ZUFAELLIGER-WERT
```

Einen geeigneten Sitzungswert erzeugst du beispielsweise mit:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Entwicklungsstart:

```powershell
fastapi dev app/main.py
```

Aufrufen:

```text
http://127.0.0.1:8000/login
```

## Vorhandene Datenbank weiterverwenden

Die vorhandene `inventory.db` in das Projektverzeichnis kopieren. Vorher eine
Sicherung erstellen. Beim nächsten Start werden fehlende Spalten automatisch
ergänzt; vorhandene Geräte, Benutzer und Ausleihen bleiben erhalten.

## Serverbetrieb

FastAPI hinter IIS oder einem anderen HTTPS-Reverse-Proxy nur lokal starten:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app `
    --host 127.0.0.1 `
    --port 8000 `
    --proxy-headers `
    --forwarded-allow-ips=127.0.0.1
```

In der Server-`.env` beispielsweise:

```env
PUBLIC_BASE_URL=https://inventur.eure-domain.de
FORCE_HTTPS=false
SESSION_COOKIE_SECURE=true
```

IIS übernimmt dabei HTTPS. Port 8000 darf nicht für andere Netzwerkgeräte
freigegeben werden.

## Firmenlogo

Falls ein Firmenlogo verwendet werden soll, diese Datei anlegen:

```text
app/static/images/logo.jpg
```

Ohne diese Datei funktioniert die Webapp weiterhin; lediglich das Bild fehlt.
