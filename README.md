# Home Assistant – Flur-Touchmonitor

Dieses Repository wird vom Add-on **Git pull** alle 5 Minuten in Home Assistant
(`/config`) eingespielt. Claude pflegt hier die Konfiguration, du musst nichts
mehr kopieren.

| Datei | Inhalt |
|---|---|
| `configuration.yaml` | Grundkonfiguration, bindet alles unten ein |
| `dashboards/flur.yaml` | Dashboard „Flur“ im Apple-Stil (`/flur-display/start`) |
| `themes/apple.yaml` | Design „Apple“ (hell + dunkel) |
| `packages/design.yaml` | setzt das Apple-Design beim Start, Sensor „Lichter an“ |
| `packages/termine.yaml` | Skript „Termin eintragen“ für die Sprachsteuerung |

Alles andere in `/config` (Datenbank, `.storage`, `secrets.yaml`, Backups,
über die Oberfläche gebaute Automationen) bleibt unberührt – siehe `.gitignore`.

---

## Einmalige Einrichtung (ca. 15 Minuten)

### 0. Sicherung
Einstellungen → System → Backups → **Backup jetzt erstellen**.

### 1. Lesezugang für Home Assistant anlegen (GitHub)
1. github.com → oben rechts Profilbild → **Settings** → ganz unten
   **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
   → **Generate new token**.
2. Name: `Home Assistant`, Ablauf: 1 Jahr (oder „No expiration“).
3. Repository access: **Only select repositories** → `homeassistant-config`.
4. Permissions → Repository permissions → **Contents: Read-only**.
5. **Generate token** → Token kopieren (beginnt mit `github_pat_…`).

### 2. Terminal vorbereiten (WICHTIG – vor dem Git-pull-Add-on!)
Ohne diesen Schritt würde das Git-pull-Add-on den Ordner `/config` leeren und
dabei alle Integrationen löschen.

1. Einstellungen → Add-ons → Add-on-Store → **Terminal & SSH** installieren
   und starten → **Web-UI öffnen**.
2. Diese vier Zeilen einfügen (einzeln oder zusammen) und Enter drücken:
   ```
   cd /config
   git init -b main
   git remote add origin https://github.com/holzzaubergmbhhatten-commits/homeassistant-config.git
   git -c user.name=HA -c user.email=ha@local commit --allow-empty -m Start
   ```

### 3. Git-pull-Add-on
1. Add-on-Store → **Git pull** installieren (noch NICHT starten).
2. Reiter **Konfiguration** → ⋮ → **Als YAML bearbeiten** → ersetzen durch:
   ```yaml
   git_branch: main
   git_command: reset
   git_remote: origin
   git_prune: false
   repository: https://github.com/holzzaubergmbhhatten-commits/homeassistant-config.git
   auto_restart: true
   restart_ignore:
     - dashboards/
     - README.md
   repeat:
     active: true
     interval: 300
   deployment_user: holzzaubergmbhhatten-commits
   deployment_password: HIER_DEN_TOKEN_EINFUEGEN
   deployment_key: []
   deployment_key_protocol: ed25519
   ```
   `HIER_DEN_TOKEN_EINFUEGEN` durch das Token aus Schritt 1 ersetzen → Speichern.
3. Reiter Info → **Starten** (und „Beim Booten starten“ an).
4. Reiter **Protokoll**: Dort sollte „Git pull“/„reset“ ohne Fehler stehen.
   Home Assistant prüft die Konfiguration und startet einmal neu.

### 4. Kalender „Termine“ anlegen
Einstellungen → Geräte & Dienste → Integration hinzufügen → **Lokaler
Kalender** → Name `Termine`.

### 5. Apple-Design auf dem Touchmonitor
Das Design wird beim Start automatisch gesetzt. Für den Monitor zusätzlich:
unten links auf den Benutzernamen → **Design: Apple**, Modus **Dunkel**.
Optional für den Milchglas-Effekt: in HACS **card-mod** installieren.

### 6. Monitor-Adresse
`http://homeassistant.local:8123/flur-display/start`

---

## Sprachsteuerung
Siehe `SPRACHE.md`.
