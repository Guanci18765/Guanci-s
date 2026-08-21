## Installation und Start

Das Inventurprogramm funktioniert unter macOS und Windows. Die virtuelle Python-Umgebung `.venv` wird auf jedem Computer neu erstellt und darf nicht in Git gespeichert werden.

### Voraussetzungen

- Python 3.12 oder neuer
- Git
- Visual Studio Code
- Zugriff auf das Git-Repository

## Installation unter macOS

Repository herunterladen:

```bash
git clone git@github.com:DEIN-USERNAME/DEIN-REPOSITORY.git
cd DEIN-REPOSITORY
```

Virtuelle Umgebung erstellen:

```bash
python3 -m venv .venv
```

Virtuelle Umgebung aktivieren:

```bash
source .venv/bin/activate
```

Abhängigkeiten installieren:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Umgebungsdatei erstellen:

```bash
cp .env.example .env
```

Anwendung starten:

```bash
fastapi dev app/main.py
```

Der Adminbereich ist anschließend erreichbar unter:

```text
http://127.0.0.1:8000/admin/
```

Virtuelle Umgebung beenden:

```bash
deactivate
```

## Installation unter Windows

PowerShell öffnen und das Repository herunterladen:

```powershell
git clone git@github.com:DEIN-USERNAME/DEIN-REPOSITORY.git
cd DEIN-REPOSITORY
```

Virtuelle Umgebung erstellen:

```powershell
py -m venv .venv
```

Falls `py` nicht gefunden wird:

```powershell
python -m venv .venv
```

Virtuelle Umgebung aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Falls PowerShell die Ausführung blockiert:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Danach erneut aktivieren:

```powershell
.\.venv\Scripts\Activate.ps1
```

Abhängigkeiten installieren:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Umgebungsdatei erstellen:

```powershell
Copy-Item .env.example .env
```

Anwendung starten:

```powershell
fastapi dev app/main.py
```

Der Adminbereich ist anschließend erreichbar unter:

```text
http://127.0.0.1:8000/admin/
```

Virtuelle Umgebung beenden:

```powershell
deactivate
```

## Konfiguration der `.env`

Die lokale `.env` enthält die Einstellungen und Zugangsdaten:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ein-sicheres-einzigartiges-passwort
SESSION_SECRET=eine-lange-zufaellige-zeichenfolge
PUBLIC_BASE_URL=http://127.0.0.1:8000
FORCE_HTTPS=false
SEED_DEMO_DATA=false
```

Ein sicheres `SESSION_SECRET` kann auf beiden Betriebssystemen erzeugt werden:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Den ausgegebenen Wert hinter `SESSION_SECRET=` eintragen.

Die Datei `.env` darf nicht in Git gespeichert werden. Die `.gitignore` muss mindestens Folgendes enthalten:

```gitignore
.env
.venv/
inventory.db
__pycache__/
*.py[cod]
.DS_Store
```

## Zugriff über Smartphone oder Tablet

Für den Zugriff über QR-Code muss das Smartphone die Anwendung über die Netzwerkadresse des Computers erreichen können.

FastAPI auf allen Netzwerkadressen starten:

```bash
fastapi dev app/main.py --host 0.0.0.0
```

### IP-Adresse unter macOS ermitteln

```bash
ipconfig getifaddr en0
```

Beispiel:

```text
192.168.17.20
```

### IP-Adresse unter Windows ermitteln

```powershell
ipconfig
```

Unter dem aktiven Netzwerkadapter nach der IPv4-Adresse suchen.

Beispiel:

```text
IPv4-Adresse: 192.168.17.20
```

Anschließend die `.env` anpassen:

```env
PUBLIC_BASE_URL=http://192.168.17.20:8000
FORCE_HTTPS=false
```

FastAPI danach neu starten. Die Anwendung ist dann beispielsweise erreichbar unter:

```text
http://192.168.17.20:8000
```

Der QR-Code muss ebenfalls eine Adresse nach diesem Muster enthalten:

```text
http://192.168.17.20:8000/device/GERAETE-ID
```

Voraussetzungen für den Smartphone-Zugriff:

- Computer und Smartphone befinden sich im gleichen erreichbaren Netzwerk.
- Es wird kein isoliertes Gast-WLAN verwendet.
- TCP-Port `8000` wird nicht von der Firewall blockiert.
- Python darf eingehende Verbindungen im privaten Netzwerk annehmen.
- `FORCE_HTTPS` steht beim lokalen HTTP-Test auf `false`.

## Dauerhafter Serverbetrieb

Für den Serverbetrieb wird nicht der Entwicklungsmodus verwendet:

```bash
fastapi run app/main.py --host 0.0.0.0 --port 8000
```

Für den produktiven Firmeneinsatz sollten zusätzlich eingerichtet werden:

- automatischer Start als Dienst
- feste IP-Adresse oder DNS-Name
- regelmäßige Sicherung von `inventory.db`
- Firewallfreigabe nur für benötigte Netzwerke
- HTTPS über einen Reverse Proxy
- sichere Admin-Zugangsdaten
- Schutz vor wiederholten Loginversuchen
