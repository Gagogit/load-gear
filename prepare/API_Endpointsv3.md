**LOAD-GEAR Energy Intelligence**

API Endpoint Spezifikation

Basis: CLAUDE\_SPEC.md \+ LG\_Pipeline\_AgentContext.md  
Stack: FastAPI · Python 3.12+ · PostgreSQL 16 · TimescaleDB · GCS · Prophet · Polars

[1\.  Endpoint-Übersicht (alle Bereiche)	1](#1.-endpoint-übersicht-\(alle-bereiche\))

[2\.  Request / Response — Kritische Endpoints	5](#2.-request-/-response-—-kritische-endpoints)

[2.1  Job anlegen	5](#2.1-job-anlegen)

[2.2  Forecast anlegen	6](#2.2-forecast-anlegen)

[2.3  QA-Findings Struktur	6](#2.3-qa-findings-struktur)

[2.4  HPFC Upload	7](#2.4-hpfc-upload)

[3\.  Job Status-Machine	7](#3.-job-status-machine)

[4\.  Container-zu-Container Kommunikation	8](#4.-container-zu-container-kommunikation)

[5\.  Offene Punkte — Klärungsbedarf für Implementierung	8](#5.-offene-punkte-—-klärungsbedarf-für-implementierung)

**Legende & Konventionen**

| GET | Synchroner Abruf — sofortige Antwort |
| :---: | :---- |
| **POST** | Ressource erstellen oder asynchronen Worker-Job starten → gibt job\_id / forecast\_id zurück, Status via GET abrufen |
| **PUT** | Vollständige Ersetzung einer Ressource (z.B. ReaderProfil-Override) |
| **DELETE** | Ressource löschen oder Job abbrechen |
| **Phase P1–P6** | Container-Zuordnung: P1=INPUT, P2=Homogenisierung, P3=QA, P4=Analyse/Imputation, P5=Forecast, P6=Financial |
| **async · worker** | Endpoint gibt HTTP 202 Accepted zurück. Ergebnis via GET /{id}/status pollen oder Webhook. |

# 

### **1\.  Endpoint-Übersicht (alle Bereiche)** {#1.-endpoint-übersicht-(alle-bereiche)}

Alle Endpoints unter Basispfad: https://{host}/api/v1/   |   Content-Type: application/json   |   Auth: (not yet — JWT geplant)

| Method | Endpoint / Pfad | Beschreibung | Phase | Tags / Scope |
| ----- | ----- | ----- | :---: | ----- |
|   **A  JOB MANAGEMENT  —  /api/v1/jobs** |  |  |  |  |
| **POST** | **/api/v1/jobs** | Neuen Job anlegen & validieren. Gibt job\_id (UUID) zurück. | **P1** | *sync · ctrl* |
| **GET** | **/api/v1/jobs** | Alle Jobs auflisten (Filter: company, status, meter\_id, Datum). | **P1** | *sync · ctrl* |
| **GET** | **/api/v1/jobs/{job\_id}** | Job-Status, Phase, Timestamps, Fehler abrufen. | **P1–5** | *sync · ctrl* |
| **DELETE** | **/api/v1/jobs/{job\_id}** | Job abbrechen (pending/running) oder Ergebnis löschen. | **P1** | *sync · ctrl* |
| **GET** | **/api/v1/jobs/{job\_id}/log** | Streaming-Log einer laufenden oder abgeschlossenen Phase. | **ALL** | *stream* |
| **GET** | **/api/v1/jobs/{job\_id}/lineage** | Vollständige Data-Lineage (v1→v2→v3, alle Run-IDs, Hashes). | **ALL** | *audit* |
|   **B  FILE UPLOAD & DOWNLOAD  —  /api/v1/files** |  |  |  |  |
| **POST** | **/api/v1/files/upload** | Quelldatei hochladen (CSV/Excel/EDIFACT). Gibt file\_id \+ SHA-256. | **P2** | *multipart* |
| **GET** | **/api/v1/files/{file\_id}** | File-Metadaten abrufen (Größe, Hash, Format, Status). | **P2** | *sync* |
| **GET** | **/api/v1/files/{file\_id}/download** | Original-Rohdatei aus GCS raw/ herunterladen (WORM). | **P2** | *stream* |
| **GET** | **/api/v1/files/{file\_id}/reader-profile** | Erkanntes ReaderProfil (Delimiter, Encoding, Datumsformat…). | **P2a** | *sync* |
| **PUT** | **/api/v1/files/{file\_id}/reader-profile** | ReaderProfil manuell überschreiben (Parser-Override). | **P2a** | *sync* |
|   **C  INGESTION & HOMOGENISIERUNG  —  /api/v1/ingest** |  |  |  |  |
| **POST** | **/api/v1/ingest** | Ingest starten: job\_id \+ file\_id → kats-ingest Container triggern. | **P2** | *async · worker* |
| **GET** | **/api/v1/ingest/{job\_id}/status** | Ingest-Status: pending/running/done/failed \+ Fortschritt %. | **P2** | *sync* |
| **GET** | **/api/v1/ingest/{job\_id}/normalized** | Normierte Zeitreihe (v1) als JSON-Array oder CSV abrufen. | **P2b** | *stream* |
|   **D  QA / STATISTIK  —  /api/v1/qa** |  |  |  |  |
| **POST** | **/api/v1/qa** | QA-Lauf starten für job\_id → kats-qa Container. | **P3** | *async · worker* |
| **GET** | **/api/v1/qa/{job\_id}/status** | QA-Status \+ Fortschritt. | **P3** | *sync* |
| **GET** | **/api/v1/qa/{job\_id}/report** | Vollständiger QA-Report (9 Checks) als JSON. | **P3** | *sync* |
| **GET** | **/api/v1/qa/{job\_id}/report/pdf** | QA-Report als PDF-Artefakt aus GCS reports/ herunterladen. | **P3** | *stream* |
| **GET** | **/api/v1/qa/{job\_id}/findings** | Einzelne QA-Findings (Lücken, Peaks, DST-Fehler) als Liste. | **P3** | *sync* |
| **GET** | **/api/v1/qa/{job\_id}/profile** | Stunden-/Wochentagsprofil (24h \+ 7-Tage-Array) als JSON. | **P3** | *sync* |
|   **E  ANALYSE & IMPUTATION  —  /api/v1/analysis** |  |  |  |  |
| **POST** | **/api/v1/analysis** | Analyse starten (Tagesklassif., Wetter, Imputation) → kats-analyse. | **P4** | *async · worker* |
| **GET** | **/api/v1/analysis/{job\_id}/status** | Analyse-Status \+ aktive Sub-Phase (4.1 / 4.2 / 4.3 / Imputation). | **P4** | *sync* |
| **GET** | **/api/v1/analysis/{job\_id}/profile** | Analysis-Profile JSON (day\_profiles, seasonality, weather\_links…). | **P4** | *sync* |
| **GET** | **/api/v1/analysis/{job\_id}/day-labels** | Tagesklassifizierung aller historischen Tage (Label \+ Score). | **P4.1** | *sync* |
| **GET** | **/api/v1/analysis/{job\_id}/weather** | Wetter-Features je Zeitstempel (temp, GHI, confidence-Score). | **P4.2** | *sync* |
| **GET** | **/api/v1/analysis/{job\_id}/imputation** | Imputation-Report: ersetzt Slots, Methode, Fallback-Flags. | **P4** | *sync* |
| **GET** | **/api/v1/analysis/{job\_id}/normalized-v2** | Bereinigte Zeitreihe (v2) als JSON-Array oder CSV. | **P4** | *stream* |
|   **F  FORECAST / PROGNOSE  —  /api/v1/forecasts** |  |  |  |  |
| **POST** | **/api/v1/forecasts** | Forecast-Job anlegen (Zielzeitraum, Strategien, Szenarien). | **P5** | *async · worker* |
| **GET** | **/api/v1/forecasts** | Alle Forecasts (Filter: meter\_id, Zeitraum, Status) auflisten. | **P5** | *sync* |
| **GET** | **/api/v1/forecasts/{forecast\_id}** | Forecast-Metadaten \+ Status \+ data\_snapshot\_id. | **P5** | *sync* |
| **GET** | **/api/v1/forecasts/{forecast\_id}/series** | Prognosezeitreihe (q10/q50/q90) als JSON. | **P5** | *sync* |
| **GET** | **/api/v1/forecasts/{forecast\_id}/export** | Export CSV/Excel/EDIFACT (query: format, unit, rounding). | **P5** | *stream* |
| **GET** | **/api/v1/forecasts/{forecast\_id}/report** | JSON-Bericht: Parameter, Strategien, Warnungen, Audit-Trail. | **P5** | *sync* |
| **DELETE** | **/api/v1/forecasts/{forecast\_id}** | Forecast-Artefakt löschen. | **P5** | *sync* |
|   **G  FINANCIAL ENGINE  —  /api/v1/financial** |  |  |  |  |
| **POST** | **/api/v1/financial/calculate** | Kostenberechnung: forecast\_id × HPFC → Gesamtkosten je Stunde. | **P6** | *async* |
| **GET** | **/api/v1/financial/{calc\_id}/result** | Ergebnis: Kosten-Zeitreihe (€/h) \+ Summen je Monat. | **P6** | *sync* |
| **GET** | **/api/v1/financial/{calc\_id}/export** | Export Kostenkalkulation (CSV/Excel). | **P6** | *stream* |
|   **H  HPFC — PREISKURVEN  —  /api/v1/hpfc** |  |  |  |  |
| **POST** | **/api/v1/hpfc/upload** | HPFC-Datei hochladen (CSV/XLSX) \+ Provider-Profil. | **P6** | *multipart* |
| **GET** | **/api/v1/hpfc** | Alle HPFC-Snapshots auflisten (Provider, Datum, Zeitraum). | **P6** | *sync* |
| **GET** | **/api/v1/hpfc/{snapshot\_id}** | Einzelnen Snapshot abrufen (Metadaten \+ Zeitraum). | **P6** | *sync* |
| **GET** | **/api/v1/hpfc/{snapshot\_id}/series** | Stündliche Preiskurve als JSON. | **P6** | *sync* |
| **DELETE** | **/api/v1/hpfc/{snapshot\_id}** | Snapshot löschen. | **P6** | *sync* |
|   **I  MESSPUNKTE / METER  —  /api/v1/meters** |  |  |  |  |
| **GET** | **/api/v1/meters** | Alle bekannten Messpunkte der Company (MaLo/ZP) auflisten. | **P1** | *sync* |
| **GET** | **/api/v1/meters/{meter\_id}** | Messpunkt-Details: PLZ, Koordinaten, letzter Import. | **P1** | *sync* |
| **GET** | **/api/v1/meters/{meter\_id}/jobs** | Alle Jobs zu einem Messpunkt (History). | **P1** | *sync* |
| **GET** | **/api/v1/meters/{meter\_id}/series** | Historische Zeitreihe (v1/v2) direkt abrufen (Filter: von/bis). | **P2–4** | *sync* |
|   **J  WETTER / GEO ENGINE  —  /api/v1/weather** |  |  |  |  |
| **GET** | **/api/v1/weather/stations** | Alle DWD-Stationen in DB auflisten (Koordinaten, Datenlücken). | **P4.2** | *sync* |
| **GET** | **/api/v1/weather/stations/nearest** | Nächste Station zu PLZ/Koordinate (Haversine) finden. | **P4.2** | *sync · geo* |
| **GET** | **/api/v1/weather/observations** | Wetter-Zeitreihe einer Station (Temp, GHI, Wind) abrufen. | **P4.2** | *sync* |
| **POST** | **/api/v1/weather/fetch** | Fallback-API-Pull auslösen (BrightSky/Open-Meteo) für Datenlücke. | **P4.2** | *async* |
| **POST** | **/api/v1/weather/bulk-import** | Jährlicher DWD-Bulk-Import anstoßen (Admin-Aktion). | **P4.2** | *admin · async* |
|   **K  KALENDER & FEIERTAGE  —  /api/v1/calendar** |  |  |  |  |
| **GET** | **/api/v1/calendar/holidays** | Feiertage abrufen (state, year) aus control.holidays Tabelle. | **P4.1** | *sync* |
| **POST** | **/api/v1/calendar/holidays** | Feiertage manuell ergänzen (z.B. Betriebsferien). | **P4.1** | *admin* |
| **GET** | **/api/v1/calendar/bridge-days** | Brückentage für Jahr \+ Bundesland berechnen. | **P4.1** | *sync* |
|   **L  ADMIN & KONFIGURATION  —  /api/v1/admin** |  |  |  |  |
| **GET** | **/api/v1/admin/config** | Globale QA-Konfiguration abrufen (Min/Max kW, Max-Sprung, Top-N). | **P3** | *admin* |
| **PUT** | **/api/v1/admin/config** | Globale QA-Konfiguration aktualisieren. | **P3** | *admin* |
| **GET** | **/api/v1/admin/health** | System-Health aller Container \+ DB-Connections. | **ALL** | *ops* |
| **GET** | **/api/v1/admin/queue** | Worker-Queue-Status (pending/running Tasks). | **ALL** | *ops* |

# 

### **2\.  Request / Response — Kritische Endpoints** {#2.-request-/-response-—-kritische-endpoints}

#### *2.1  Job anlegen* {#2.1-job-anlegen}

| POST /api/v1/jobs — Request Body (job.json) |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **meter\_id** | *string · UUID/MaLo* | MaLo- oder Zählpunktbezeichnung (Pflichtfeld) |
| **company** | *string* | Firmen-ID (zukünftig: Mandanten-Isolation) |
| **plz** | *string · 5-stellig* | Postleitzahl für Geo-Matching zur Wetterstation |
| **horizon\_start** | *datetime · ISO 8601* | Start des Prognosezeitraums (UTC) |
| **horizon\_end** | *datetime · ISO 8601* | Ende des Prognosezeitraums (UTC) |
| **unit** | *enum: kWh | kW* | Zieleinheit für Ausgabe |
| **interval\_min** | *integer (z.B. 15\)* | Zeitraster der Ausgabe in Minuten |
| **tasks\[\]** | *array · enum* | Auftragsliste: Statistik | Fehleranalyse | Umformatierung | Imputation | Prognose | Aggregation |
| **scenarios{}** | *object* | Szenario-Konfiguration: growth\_pct, pv\_enabled, battery\_config |
| **output\_format** | *enum: CSV|Excel|EDIFACT* | Gewünschtes Ausgabeformat |
| **file\_id** | *UUID (optional)* | Vorab hochgeladene Quelldatei (alternativ: Upload im Ingest-Schritt) |

| POST /api/v1/jobs — Response Body |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **job\_id** | *UUID v4* | Eindeutige Job-ID für alle Folge-Requests |
| **status** | *enum: pending* | Initialer Status des Jobs |
| **created\_at** | *datetime · ISO 8601* | Zeitstempel der Job-Erstellung (UTC) |
| **tasks** | *array* | Echo der beauftragten Tasks |
| **\_links.self** | *URL* | GET /api/v1/jobs/{job\_id} |
| **\_links.ingest** | *URL* | POST /api/v1/ingest (nächster Schritt) |

#### *2.2  Forecast anlegen* {#2.2-forecast-anlegen}

| POST /api/v1/forecasts — Request Body |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **job\_id** | *UUID* | Referenz auf abgeschlossenen Analyse-Job (Phase 4 done) |
| **horizon\_start** | *datetime · ISO 8601* | Forecast-Startzeitpunkt (UTC) |
| **horizon\_end** | *datetime · ISO 8601* | Forecast-Endzeitpunkt (UTC) |
| **strategies\[\]** | *array · enum* | Kalender-Mapping | Wetter-konditioniert | DST-korrekt | Skalierung | Asset-Szenarien | Energie-Budgets |
| **scenarios** | *object* | Identisch zu job.scenarios — Wachstum, PV, Speicher |
| **quantiles\[\]** | *array (z.B. \[10,50,90\])* | Konfidenzintervalle für Output |
| **output\_format** | *enum: CSV|Excel|EDIFACT* | Exportformat |
| **energy\_constraints** | *object (optional)* | Monatliche Summen-Constraints (kWh) |

| POST /api/v1/forecasts — Response (Async) |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **forecast\_id** | *UUID v7* | Eindeutige Forecast-ID |
| **status** | *enum: queued* | Worker-Status: queued → running → ok | warn | failed |
| **data\_snapshot\_id** | *SHA-256* | Reproduzierbarkeitshash (Meter \+ Zeitraum \+ v2 \+ Analysis-Params) |
| **model\_alias** | *string: prophet* | Verwendetes Modell |
| **model\_version** | *semver / git-hash* | Exakte Modellversion |
| **\_links.status** | *URL* | GET /api/v1/forecasts/{forecast\_id} |
| **\_links.series** | *URL* | GET /api/v1/forecasts/{forecast\_id}/series |
| **\_links.export** | *URL* | GET /api/v1/forecasts/{forecast\_id}/export |

#### *2.3  QA-Findings Struktur* {#2.3-qa-findings-struktur}

| GET /api/v1/qa/{job\_id}/findings — Response-Struktur (je Check) |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **check\_id** | *integer 1–9* | Nummer des QA-Checks |
| **check\_name** | *string* | z.B. interval\_completeness, gap\_analysis, dst\_conformity |
| **status** | *enum: ok|warn|error* | Ergebnis des Checks |
| **metric\_key** | *string* | z.B. completeness\_pct, gap\_max\_duration\_min, kw\_peak\_value |
| **metric\_value** | *number | string* | Numerischer oder textueller Messwert |
| **threshold** | *number (optional)* | Konfigurierter Schwellenwert (aus admin/config) |
| **affected\_slots** | *array (optional)* | Betroffene Zeitstempel-Liste (Lücken, Duplikate, DST-Fehler) |
| **recommendation** | *string* | Automatische Imputation-Empfehlung oder manueller Hinweis |

#### *2.4  HPFC Upload* {#2.4-hpfc-upload}

| POST /api/v1/hpfc/upload — Request (multipart/form-data) |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **file** | *binary (CSV/XLSX)* | HPFC-Datei mit stündlichen Preisen |
| **provider** | *string* | Provider-Bezeichnung (z.B. EPEXSpot, EEX) |
| **delivery\_start** | *date* | Erster Liefertag der Kurve |
| **delivery\_end** | *date* | Letzter Liefertag der Kurve |
| **currency** | *string: EUR* | Währung der Preise |
| **unit** | *string: EUR/MWh* | Preiseinheit |
| **snapshot\_label** | *string (optional)* | Versionsbeschreibung (z.B. 'Q1-2026-Revision-2') |

# 

### **3\.  Job Status-Machine** {#3.-job-status-machine}

Jeder Job durchläuft eine definierte State-Machine. Der aktuelle Status ist immer über GET /api/v1/jobs/{job\_id} abrufbar.

| Job Status-Machine — Übergänge |  |  |
| :---- | :---- | :---- |
| **Feld / Parameter** | **Typ / Format** | **Beschreibung** |
| **pending** | *→ ingesting* | Job angelegt, kats-ingest wartet auf Start |
| **ingesting** | *→ qa\_pending | failed* | kats-ingest läuft: Parse, Normierung, GCS-Upload |
| **qa\_pending** | *→ qa\_running* | kats-qa in Queue |
| **qa\_running** | *→ analysis\_pending | failed* | 9 QA-Checks laufen |
| **analysis\_pending** | *→ analysis\_running* | kats-analyse in Queue |
| **analysis\_running** | *→ forecast\_pending | done | failed* | Tagesklassif., Wetter, Imputation |
| **forecast\_pending** | *→ forecast\_running* | kats-forecast in Queue (nur wenn tasks\[Prognose\]) |
| **forecast\_running** | *→ done | warn | failed* | Prophet-Modell läuft im Worker |
| **done** | *Terminal* | Alle beauftragten Tasks erfolgreich |
| **warn** | *Terminal* | Ergebnis vorhanden, aber mit Qualitätswarnungen |
| **failed** | *Terminal* | Phase fehlgeschlagen — Retry via POST /api/v1/jobs/{id}/retry |

WICHTIG: Ein Job ohne tasks=\[Prognose\] endet nach analysis\_running → done (kein Forecast-Schritt).  
Retry-Logik: POST /api/v1/jobs/{job\_id}/retry startet die fehlgeschlagene Phase neu (offener Punkt — noch zu spezifizieren).

# 

### **4\.  Container-zu-Container Kommunikation** {#4.-container-zu-container-kommunikation}

Offener Architektur-Entscheid: Zwei Varianten sind möglich — DB-State-Poll oder Message-Queue. Empfehlung: DB-basierter Poll für v0.1 (einfacher), Queue-Upgrade für Produktion.

| Container | Trigger-Mechanism | Liest | Schreibt / Status-Update |
| :---- | :---- | :---- | :---- |
| **kats-ingest** | POST /api/v1/ingest | job.json \+ Quelldatei (GCS) | raw/, normalized/\_v1, control.jobs → ingesting/done |
| **kats-qa** | DB-Poll: status=ingesting\_done | normalized/\_v1 | quality\_findings, normalized/\_v2, jobs → qa\_running/done |
| **kats-analyse** | DB-Poll: status=qa\_done | normalized/\_v2 | analysis\_params, day\_labels, weather\_features, jobs → analysis\_running/done |
| **kats-forecast** | DB-Poll: status=analysis\_done (wenn tasks\[Prognose\]) | analysis\_params (Artefakt-JSON) | forecasts/, SQL forecasts-Tabelle, jobs → forecast\_running/done |

### **5\.  Offene Punkte — Klärungsbedarf für Implementierung** {#5.-offene-punkte-—-klärungsbedarf-für-implementierung}

| \# | Offener Punkt | Auswirkung auf Endpoint-Design | Empfehlung |
| :---: | :---- | :---- | :---- |
| **1** | Retry-Logik: Kein Endpoint für Wiederanlauf einer fehlgeschlagenen Phase definiert | POST /api/v1/jobs/{id}/retry fehlt → Container-Kette blockiert bei Fehler | **POST /jobs/{id}/retry mit optionalem body {from\_phase}** |
| **2** | v2-Eigentümer: Sowohl kats-qa als auch kats-analyse schreiben normalized\_v2 — Konflikt | GET /api/v1/.../normalized-v2 liefert ggf. falschen Stand | **Klares Ownership: QA \= v2-Kandidat, Analyse \= v2-Final (überschreibt)** |
| **3** | Webhook vs. Polling: Kein Push-Mechanismus für async-Ergebnisse spezifiziert | Frontend muss GET /status pollen — ineffizient bei langen Forecast-Jobs | **Webhook-URL im POST-Body optional: on\_complete\_url** |
| **4** | EDIFACT-Subset: Welches MSCONS-Subset und welche Qualifier-Codes? | GET /forecasts/{id}/export?format=EDIFACT kann nicht implementiert werden | **MSCONS-Beispieldatei \+ Qualifier-Tabelle liefern** |
| **5** | Scenarios → Prophet: Wie wird growth\_pct in Regressoren übersetzt? | POST /api/v1/forecasts ohne diese Logik ist ein Black Box | **Scenarios-zu-Prophet-Mapping-Dokument erstellen** |
| **6** | Auth (not yet): Kein Token-Mechanismus → alle Endpoints offen | Für Produktion: JWT Bearer in Authorization-Header | **OpenID Connect / OAuth2 Password Flow für v1.0 vormerken** |
| **7** | Mandantenfähigkeit: company nur im Job-JSON, keine DB-Isolation | Queries ohne company-Filter geben Cross-Tenant-Daten zurück | **Row-Level-Security in PostgreSQL auf company\_id aktivieren** |

