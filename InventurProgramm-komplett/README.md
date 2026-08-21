## Start unter Windows

Die Anwendung funktioniert unter Windows, macOS und Linux. Die virtuelle Python-Umgebung wird auf jedem Computer neu erstellt und gehört nicht in das Git-Repository.

### Voraussetzungen

- Python 3.12 oder neuer
- Git
- Visual Studio Code
- Zugriff auf das Projekt-Repository

### Repository herunterladen

Öffne PowerShell und wechsle in den gewünschten Projektordner:

```powershell
cd C:\Pfad\zum\Projektordner
```

Repository klonen:

```powershell
git clone git@github.com:DEIN-USERNAME/DEIN-REPOSITORY.git
```

Anschließend in das Projekt wechseln:

```powershell
cd DEIN-REPOSITORY
```

### Virtuelle Python-Umgebung erstellen

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

Eine aktive Umgebung wird im Terminal so angezeigt:

```text
(.venv) PS C:\Pfad\zum\InventurProgramm>
```

### Abhängigkeiten installieren

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

SQLite ist bereits in Python enthalten und muss nicht separat installiert werden.

### Umgebungsdatei erstellen

Falls eine `.env.example` vorhanden ist:

```powershell
Copy-Item .env.example .env
```

Andernfalls:

```powershell
New-Item .env -ItemType File
```

Die `.env` muss beispielsweise folgende Einstellungen enthalten:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ein-sicheres-einzigartiges-passwort
SESSION_SECRET=eine-lange-zufaellige-zeichenfolge
PUBLIC_BASE_URL=http://127.0.0.1:8000
FORCE_HTTPS=false
SEED_DEMO_DATA=false
```

Ein sicheres Session-Secret kann mit Python erzeugt werden:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Den ausgegebenen Wert in `.env` hinter `SESSION_SECRET=` eintragen.

Die Datei `.env` darf nicht in das Git-Repository übertragen werden.

### Anwendung lokal starten

```powershell
fastapi dev app/main.py
```

Der Adminbereich ist anschließend erreichbar unter:

```text
http://127.0.0.1:8000/admin/
```

### Zugriff über Smartphone oder Tablet

Damit andere Geräte im lokalen Netzwerk auf die Anwendung zugreifen können, muss FastAPI auf allen Netzwerkadressen lauschen:

```powershell
fastapi dev app/main.py --host 0.0.0.0
```

Die IPv4-Adresse des Windows-Geräts ermitteln:

```powershell
ipconfig
```

Unter dem aktiven Netzwerkadapter steht beispielsweise:

```text
IPv4-Adresse: 192.168.17.20
```

Die `.env` entsprechend anpassen:

```env
PUBLIC_BASE_URL=http://192.168.17.20:8000
FORCE_HTTPS=false
```

FastAPI danach neu starten.

Auf dem Smartphone kann die Anwendung dann beispielsweise unter dieser Adresse geöffnet werden:

```text
http://192.168.17.20:8000
```

Windows fragt beim ersten Start möglicherweise, ob Python Netzwerkzugriff erhalten darf. Der Zugriff sollte ausschließlich für private beziehungsweise vertrauenswürdige Netzwerke erlaubt werden.

Falls keine Abfrage erscheint, muss gegebenenfalls eine eingehende Firewallregel für TCP-Port `8000` eingerichtet werden. Dafür sind Administratorrechte erforderlich.

Smartphone und Windows-Gerät müssen sich im gleichen erreichbaren Netzwerk befinden. Gast-WLANs blockieren häufig die Kommunikation zwischen einzelnen Geräten.

### Dauerhafter Betrieb auf einem Windows-Server

Für den Serverbetrieb wird nicht der Entwicklungsmodus verwendet:

```powershell
fastapi run app/main.py --host 0.0.0.0 --port 8000
```

Für einen produktiven Firmeneinsatz sollten zusätzlich eingerichtet werden:

- automatischer Start als Windows-Dienst
- feste IP-Adresse oder DNS-Name
- regelmäßige Sicherung von `inventory.db`
- Firewallfreigabe nur für benötigte Netzwerke
- HTTPS über IIS, Caddy oder einen anderen Reverse Proxy
- sichere Admin-Zugangsdaten

### Virtuelle Umgebung beenden

```powershell
deactivate
```
