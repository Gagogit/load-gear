

[**A Executive Summary:**](#a-executive-summary:-load-gear-energy-intelligence)   
[**LOAD-GEAR Energy Intelligence	2**](#a-executive-summary:-load-gear-energy-intelligence)

[1\. Strategische Zielsetzung	2](#1.-strategische-zielsetzung)

[2\. Kernarchitektur & Technologie-Stack	2](#2.-kernarchitektur-&-technologie-stack)

[3\. Schlüsselkomponenten	2](#3.-schlüsselkomponenten)

[A. Spatial Weather Logic (Hybrid-Engine)	2](#a.-spatial-weather-logic-\(hybrid-engine\))

[B. Logische Pipeline & Daten-Lifecycle	2](#b.-logische-pipeline-&-daten-lifecycle)

[C. Financial & Reverse Engine	2](#c.-financial-&-reverse-engine)

[4\. Definition of Done & Sicherheit	2](#4.-definition-of-done-&-sicherheit)

[**A. Claude Spec	3**](#a.-claude-spec)

[**1\. CORE ARCHITECTURE (Globaler Kontext)	4**](#1.-core-architecture-\(globaler-kontext\))

[(Stack, Async-First, No-Pandas)	4](#\(stack,-async-first,-no-pandas\))

[**2\. LOGICAL PIPELINE	4**](#2.-logical-pipeline)

[**3\. Daten Schema	4**](#3.-daten-schema)

[**3.1 Datenquellen & Provenienz	4**](#3.1-datenquellen-&-provenienz)

[**3.2 Daten Lifecycle	4**](#3.2-daten-lifecycle)

[3.2.1 Schema: control (Die Kommandozentrale)	5](#3.2.1-schema:-control-\(die-kommandozentrale\))

[Tabelle: jobs	5](#tabelle:-jobs)

[Tabelle: files	5](#tabelle:-files)

[Tabelle: reader\_profiles	5](#tabelle:-reader_profiles)

[3.2.2 Schema analysis: (Der Erkenntnis-Layer)	6](#3.2.2-schema-analysis:-\(der-erkenntnis-layer\))

[Tabelle: analysis\_profiles (Das Herzstück)	6](#tabelle:-analysis_profiles-\(das-herzstück\))

[3.2.3 Schema data: (Der Vektor-Speicher)	6](#3.2.3-schema-data:-\(der-vektor-speicher\))

[Tabelle: meter\_reads	6](#tabelle:-meter_reads)

[Tabelle: forecast\_series	6](#tabelle:-forecast_series)

[3.3 external Schema: data HPFC (HourlyPriceForwarCurve)	6](#3.3-external-schema:-data-hpfc-\(hourlypriceforwarcurve\))

[3.4 external Schema “Temperatur und Sonnenstrahlung”	6](#3.4-external-schema-“temperatur-und-sonnenstrahlung”)

[**4\. WEATHER & GEO ENGINE	8**](#4.-weather-&-geo-engine)

[4.1 SPATIAL WEATHER LOGIC	8](#4.1-spatial-weather-logic)

[Der Hybrid- Workflow	8](#der-hybrid--workflow)

[WEATHER ENGINE ARCHITECTURE	8](#weather-engine-architecture)

[**5\. Prognosis	9**](#5.-prognosis)

[5\. 1\. Feiertags- und Kalenderlogik	9](#5.-1.-feiertags--und-kalenderlogik)

[5.2. Brückentage	9](#5.2.-brückentage)

[**5.3 PROPHET & Spatial-Temporal Join	10**](#5.3-prophet-&-spatial-temporal-join)

[A. Die Logik des "Spatial-Temporal Joins"	10](#a.-die-logik-des-"spatial-temporal-joins")

[B. SQL-Referenz-Implementierung (KI-Blueprint)	10](#b.-sql-referenz-implementierung-\(ki-blueprint\))

[C. Prophet Feature Engineering Pipeline	10](#c.-prophet-feature-engineering-pipeline)

[Skalierungs-Vorgabe (Worker-Prinzip)	10](#skalierungs-vorgabe-\(worker-prinzip\))

[**5.4 „Ausrollen“ (Projektion in Zielzeitraum)	10**](#5.4-„ausrollen“-\(projektion-in-zielzeitraum\))

[**6\. FINANCIAL Calculations	11**](#6.-financial-calculations)

[**6.1 FINANCIAL ENGINE (HPFC Integration)	11**](#6.1-financial-engine-\(hpfc-integration\))

[**6.2 (not yet) BIDIREKTIONALE ENGINE (Reverse Feedback)	11**](#6.2-\(not-yet\)-bidirektionale-engine-\(reverse-feedback\))

[**7\. DEFINITION OF DONE (DoD)	11**](#7.-definition-of-done-\(dod\))

[**10\. openpoints for programming	13**](#heading=h.csg49o8q5dhc)

[1\. Fehlende forecast\_runs Tabelle — kritisch	13](#heading=h.7qvnciwhqbyz)

[2\. meter\_reads Schema fehlt geom-Feld	13](#heading=h.nz7y2xvrvvtx)

[3\. Keine einzige API-Endpoint-Definition	13](#heading=h.pthsau5a4bwh)

[4\. Die "9 QA-Checks" sind ein Black Box	13](#heading=h.84up813dhyhn)

[5\. Cold Data Format leer	13](#heading=h.lvs0tdfjnp9d)

[6\. Celery vs. Container — kein Entscheid	13](#heading=h.bcv3dqhccmsz)

[7\. control.holidays Tabelle nirgendwo definiert	13](#heading=h.nb9qldns0gh9)

[8\. Authentication/Authorization: komplett absent	13](#heading=h.xjkeof318b50)

[9\. Reader-Profile-Logik: zu vage	14](#heading=h.o5qgwzbzhjyu)

[10\. 6.2 Bidirektionale Engine: Placeholder	14](#heading=h.194oantzwkzl)

# **A Executive Summary:**  **LOAD-GEAR Energy Intelligence** {#a-executive-summary:-load-gear-energy-intelligence}

### **1\. Strategische Zielsetzung** {#1.-strategische-zielsetzung}

LOAD-GEAR ist eine spezialisierte Plattform zur Verarbeitung und Veredelung von Energiedaten. Ziel ist es, aus rohen Lastgangdaten (v1) durch statistische Bereinigung und Wetter-Anreicherung (v2) valide Prognosemodelle (v3) zu erstellen. Diese dienen als Basis für die Energiepreiskalkulation von gewerblichen Energiekunden und Szenarien-Analysen (z. B. PV-Integration oder Spitzenlastkappung).

### **2\. Kernarchitektur & Technologie-Stack** {#2.-kernarchitektur-&-technologie-stack}

Das System setzt konsequent auf Performance und Skalierbarkeit:

* **Sprache & API:** Python 3.12+ mit **FastAPI** (Async-First).  
* **Daten-Engine:** **Polars** (Lazy API) und **NumPy** für Vektor-Processing von Zeitreihen.  
* **Datenbank:** **PostgreSQL 16** mit **TimescaleDB** für Zeitreihen-Massen-Daten und **PostGIS** für geografische Operationen.  
* **Prognose:** Einsatz von **Meta Prophet** für Saisonalitäts- und Feiertagsanalysen.

### **3\. Schlüsselkomponenten** {#3.-schlüsselkomponenten}

#### **A. Spatial Weather Logic (Hybrid-Engine)** {#a.-spatial-weather-logic-(hybrid-engine)}

Die Engine minimiert API-Kosten und Latenz durch eine zweistufige Strategie:

* **Tier 1:** Jährlicher Bulk-Import historischer DWD-Daten (Temperatur/Strahlung).  
* **Tier 2:** Dynamischer API-Fallback (BrightSky/Open-Meteo) nur bei Datenlücken.  
* **Innovation:** Ein **Spatio-Temporal Join** via SQL (Lateral Join) verknüpft Lastgänge automatisch mit der geografisch nächsten Wetterstation unter Berücksichtigung eines dynamischen **Confidence-Scores**.

#### **B. Logische Pipeline & Daten-Lifecycle** {#b.-logische-pipeline-&-daten-lifecycle}

Daten durchlaufen einen definierten Evolutionsprozess:

1. **v1 (Raw):** Normalisierung unterschiedlicher Quellformate via `reader_profiles`.  
2. **v2 (Imputed):** Anwendung von 9 QA-Checks (Lücken, Peaks, Baseload) und statistische Bereinigung.  
3. **v3 (Forecast):** Projektion in Zielzeiträume unter Einbeziehung von Wetter-Regressoren, Feiertagslogiken und Brückentag-Erkennung.

#### **C. Financial & Reverse Engine** {#c.-financial-&-reverse-engine}

Das System verbindet physikalische Lastgänge mit wirtschaftlichen Parametern:

* Integration von **Hourly Price Forward Curves (HPFC)** für Kostenkalkulationen via Vektor-Skalarprodukt.  
* Simulation von Einspar-Szenarien durch Lastverschiebung oder Asset-Erweiterungen (PV/Speicher).

### **4\. Definition of Done & Sicherheit** {#4.-definition-of-done-&-sicherheit}

Jeder Rechenschritt ist durch eine strikte **Data-Lineage** (`job_id`) rückverfolgbar. Das System trennt rechenintensive Forecast-Tasks konsequent vom API-Thread durch ein **Worker-Prinzip**.

# 

# **A. Claude Spec** {#a.-claude-spec}

\# CLAUDE\_SPEC.md: LOAD-GEAR (LG) ENERGY INTELLIGENCE

\#\# 1\. TECH-STACK & CORE PRINCIPLES

\- \*\*Language:\*\* Python 3.12+ (Unified Backend)

\- \*\*API-Framework:\*\* FastAPI (Asynchron)

\- \*\*Data Engine:\*\* Polars (Lazy API) & NumPy (Vektor-Prinzip: 8.760h Arrays)

\- \*\*Database:\*\* PostgreSQL 16+ mit PostGIS (Geo) & TimescaleDB (Time-Series)

\- \*\*ORM:\*\* SQLAlchemy 2.0 (Async) mit Psycopg3

\- \*\*Forecasting:\*\* Prophet (Facebook/Meta)

\- \*\*(not yet):\*\* not in scop of actual programming

\#\# 2\. DATA ARCHITECTURE (SQL)

\- \*\*Schema \`control\`\*\*: Jobs, Files, Reader-Profiles (Metadata & Lineage).

\- \*\*Schema \`data\`\*\*: 

    \- \`meter\_reads\`: Hypertable für Lastgänge (v1 Raw, v2 Imputed).

    \- \`weather\_observations\`: Hypertable für Temp & Globalstrahlung (Source-centered).

    \- \`forecast\_series\`: Projizierte Zeitreihen inkl. Quantile (q10, q50, q90).

\#\# 3\. SPATIAL WEATHER LOGIC (Bulk-Driven)

\- \*\*Storage Strategy:\*\* Datenhaltung basiert auf einem deutschlandweiten Raster von Wetterstationen (DWD-"CDC").

\- \*\*Ingestion:\*\* Jährlicher Bulk-Import (historisch) reduziert API-Abhängigkeit auf ein Minimum.

\- \*\*Truth-Function:\*\* \`Confidence \= 1.0 \- (Distance / 50km)\`.

\- \*\*Spatio-Temporal Join:\*\* Wetterdaten werden via SQL \`LATERAL JOIN\` und PostGIS \`\<-\>\` Operator auf das Lastgang-Raster gemappt.

\#\# 4\. PROCESSING PIPELINE

1\. \*\*Normalizer:\*\* Parsing via Reader-Profiles in Polars DataFrames.

2\. \*\*Validator:\*\* 9 Statistik-Checks (Lücken, Peaks, DST, Baseload).

3\. \*\*Intelligence:\*\* Prophet-Training unter Einbezug von geografisch und gesetzlich relevanten Feiertagen und Wetter-Regressoren.

4\. \*\*Reverse-Feedback:\*\* Berechnung von Einspar-Szenarien basierend auf Lastgang-Optimierung (Tarif-Constraints).

\#\# 5\. SYSTEM CONSTRAINTS (For Claude)

\- \*\*No Pandas:\*\* Nutze Polars für alle transformativen Operationen.

\- \*\*Async First:\*\* Datenbank- und API-Operationen müssen nicht-blockierend sein.

\- \*\*Lineage:\*\* Jeder berechnete Wert muss auf einen \`job\_id\` und eine Quelldatei 

zurückführbar sein.

# 

# **1\. CORE ARCHITECTURE (Globaler Kontext)** {#1.-core-architecture-(globaler-kontext)}

## (Stack, Async-First, No-Pandas) {#(stack,-async-first,-no-pandas)}

* **Vektor-Processing:** Alle Berechnungen operieren auf 8.760h-Arrays (Vektor-Prinzip).  
* **Multi-Layer Storage:** \* **SQL:** Metadaten, Jobs, Analysen, Wetter-Metriken (PostgreSQL/TimescaleDB/postGIS).  
  * **Object Store:** Originale (Raw), Normalisierte Zeitreihen Forecast-Artefakte.  
* **Zeit-Referenz:** ts\_utc ist der intern führende Zeitstempel; lokale Zeit (Europe/Berlin) dient nur dem Ausgabe+Reporting und wird umgerechnet.  
* **Modell-Trennung:** Prophet für Analyse und Ausrollen (Python-Spezialist-Level).  
* **Language:** Python 3.12+ (Unified Environment)  
* **API-Framework:** **FastAPI** (Asynchron)  
* **Data Engine:** Polars & NumPy  
* **Datenbank:** PostgreSQL 16+ (mit **PostGIS** für Geo-Logik & **TimescaleDB** für Zeitreihen).  
* **ORM / Database Toolkit:** **SQLAlchemy 2.0** (Async-Modus).  
* **Treiber:** `psycopg3` (der moderne Standard für asynchrone Python-Postgres-Verbindungen).

# **2\. LOGICAL PIPELINE** {#2.-logical-pipeline}

	2.1 Input  
2.2 Homogenisierung  
	2.3 QA  
	2.4 Analysis  
2.5 Forecast

# **3\. Daten Schema** {#3.-daten-schema}

## 3.1 Datenquellen & Provenienz {#3.1-datenquellen-&-provenienz}

| Data-Schema | Source | Description | Storage |
| :---- | :---- | :---- | :---- |
| User-Input | Frontend | Manuelle Parameter (MaLo, PLZ, Szenarien), die der User direkt im Konfigurator eingibt. | control.jobs (JSONB) |
| Primary Time Series | Dateiupload | Der Lastgang (CSV/Excel), der das Herzstück der Analyse bildet. | data.meter\_reads (v1) |
| Enrichment data | API (extern)E-Mail/FTP | automated API-Call Wetterdaten (**DWD**)**HPFC** (HourlyPriceForwardCurves) | data.weather\_observationsdata.dropzone |

## 

## 3.2 Daten Lifecycle {#3.2-daten-lifecycle}

| Data\_Type | Evolution | Examples, patterns |
| :---- | :---- | :---- |
| `control` v1\_raw | Ingestion & Normalisierung. | Ingestion: Automatisches Erkennen der Quelllogik und Homogenisierung in meter\_reads v1. |
| `analysis` v2\_imputed | Die 9 QA-Checks & Prophet-Imputation. | Statistik (Check 1-9): Analyse von Vollständigkeit, Spitzenlast, Baseload und DST-Konformität. |
| `data` v3\_forecast | Prophet Projection. | Prophet-Analyse: Erstellung der Day-Fingerprints und Wetter-Feature-Matrix. |
|  |  | Imputation (v2): Erstellung der bereinigten Zeitreihe (normalized\_v2) basierend auf dem Analysis-Profile. |
|  |  | Forecast: Projektion der historischen Muster in den Zielzeitraum (Ausrollen). |

### 3.2.1 Schema: `control` (Die Kommandozentrale) {#3.2.1-schema:-control-(die-kommandozentrale)}

Diese Tabellen steuern den Prozess und halten die Metadaten. Sie sind das „Gedächtnis“ für jeden Job.

#### **Tabelle: `jobs`** {#tabelle:-jobs}

*Der Startpunkt für jede Aktion.*

* `id`: UUID (Primary Key)

* `status`: ENUM ('pending', 'processing', 'completed', 'failed')

* `payload`: JSONB (Enthält alle Frontend-Parameter: Zählpunkt, Zielzeitraum, Skalierung)

* `created_at`: TIMESTAMPTZ (Default: now())

  #### **Tabelle: `files`** {#tabelle:-files}

  *Verwaltung der physischen Dateien.*

* `id`: UUID (Primary Key)

* `storage_uri`: TEXT (Pfad im GCS/MinIO, z. B. `raw/2026/file.csv`)

* `sha256`: TEXT (Zur Duplikaterkennung und Integrität)

* `meta_data`: JSONB (Größe, Import-Quelle, Originalname)

  #### **Tabelle: `reader_profiles`** {#tabelle:-reader_profiles}

  *Das technische Verständnis der Datei.*

* `id`: UUID (Primary Key)

* `file_id`: UUID (FK zu `files`)

* `rules`: JSONB (Delimiter, Encoding, Datumsformat, Spaltenmapping)

* `technical_quality`: JSONB (Anzahl Zeilen, valide/invalide Zeilen, Warnungen)

  ##    

  ### 3.2.2 Schema `analysis`: (Der Erkenntnis-Layer) {#3.2.2-schema-analysis:-(der-erkenntnis-layer)}

  Hier speichern wir, was Prophet und die statistischen Checks herausgefunden haben. Dies ist die Basis für das „Rückwärts-Denken“.

  #### **Tabelle: `analysis_profiles` (Das Herzstück)** {#tabelle:-analysis_profiles-(das-herzstück)}

* `id`: UUID (Primary Key)

* `job_id`: UUID (FK zu `jobs`)

* `day_fingerprints`: JSONB (Clustering-Ergebnisse: Werktag, Feiertag, Störung)

* `weather_correlations`: JSONB (Sensitivität für Temperatur und Globalstrahlung)

* `asset_hints`: JSONB (Erkannte Muster für PV oder Speicher)

  ## 

  ### 3.2.3 Schema `data`: (Der Vektor-Speicher) {#3.2.3-schema-data:-(der-vektor-speicher)}

  Hier liegen die Massendaten. Diese Tabellen werden als **TimescaleDB Hypertables** angelegt, um Milliarden von Zeilen performant zu verarbeiten.

  #### **Tabelle: `meter_reads`** {#tabelle:-meter_reads}

  *Die "Golden Row" (Normalisierte Zeitreihe).*

* `ts_utc`: TIMESTAMPTZ (Leading Reference)

* `meter_id`: TEXT (Zählpunkt-ID)

* `value`: DOUBLE PRECISION (Der Messwert)

* `unit`: ENUM ('kW', 'kWh')

* `version`: INT (1 \= Raw, 2 \= Imputiert/Bereinigt)

* `quality_flag`: INT (Indikator für die Datenquelle/Güte)

  #### **Tabelle: `forecast_series`** {#tabelle:-forecast_series}

  *Der Blick in die Zukunft.*

* `ts_utc`: TIMESTAMPTZ

* `forecast_id`: UUID (FK zu einer `forecast_runs` Tabelle)

* `y_hat`: DOUBLE PRECISION (Prognosewert)

* `q10`, `q50`, `q90`: DOUBLE PRECISION (Quantile für die Risikoanalyse)

##  3.3 external Schema: `data HPFC` (HourlyPriceForwarCurve) {#3.3-external-schema:-data-hpfc-(hourlypriceforwarcurve)}

wirtschaftliches Gegenstück zu Last Zeitreihe

| Header |  |  |
| :---- | :---- | :---- |
| provider\_id | TEXT | ID des Energieversorgers (z.B. "EON", "Vattenfall"). |
| snapshot\_at | TIMESTAMPTZ | Wann wurde diese Kurve erstellt? (Wichtig für die Versionierung). |
| curve\_type | ENUM | HPFC', 'Spot', 'Intraday'. |
|  |  |  |
|  |  |  |
| Spalte | Typ | Beschreibung |
| ts\_utc | TIMESTAMPTZ | Die Stunde, für die der Preis gilt. |
| price\_mwh | DOUBLE | Der Preis in €/MWh. |

## 3.4 external Schema “Temperatur und Sonnenstrahlung” {#3.4-external-schema-“temperatur-und-sonnenstrahlung”}

**DWD (deutscher Wetterdienst) BULK INGESTION & PERSISTENCE LAYER**

* **Datenquelle & Format:** Der Import erfolgt automatisiert vom **DWD-"CDC" FTP-Server** (opendata.dwd.de). Es werden primär die stündlichen historischen Datensätze für Temperatur (TT\_TU) und Globalstrahlung (FG\_LUM) im **CSV-Format** (ASCII) abgerufen.

* **Ingestion Tool (Polars):** Die Verarbeitung der massiven CSV-Daten erfolgt über **Polars Lazy-Queries**. Polars liest die CSV-Dateien direkt ein, führt das Typ-Mapping (z. B. Konvertierung der DWD-Zeitstempel in ISO-8601 UTC) durch und berechnet ggf. Einheitenumrechnungen (z. B. $J/cm^2$ zu $W/m^2$).

* **Speicherformat** 

  * **Hot Data (PostgreSQL/TimescaleDB):** Die bereinigten Daten werden mittels SQLAlchemy/Psycopg3 in die data.weather\_observations Hypertable geschrieben. Dabei wird die Geo-Position der Station als GEOGRAPHY(POINT) indiziert.

  * **Cold Data ():** Als Backup und für extrem schnelle Batch-Analysen werden die Roh-Importe im Vektor-Prinzip (8.760h Werte) der Speicherplatzbedarf im Vergleich zu CSV um ca. 90% reduziert.

* **Daten-Integrität:** Jeder Wetter-Datensatz erhält ein (Confidence Score)

# 

# **4\. WEATHER & GEO ENGINE** {#4.-weather-&-geo-engine}

## **4.1 SPATIAL WEATHER LOGIC** {#4.1-spatial-weather-logic}

### **Der Hybrid- Workflow** {#der-hybrid--workflow}

1. **Januar-Routine: Bulk-Download des Vorjahres vom DWD-FTP (CSV/ASCII) für ein definiertes Raster von Stationen.**  
2. **Transformation: Einlesen via Polars und Speichern in data.weather\_observations.**  
3. **API-Fallback: Die DWD-API wird *nur* noch als "Lückenfüller" benutzt, falls ein Job läuft, für den es noch keine** DWD-CDC **Archivdaten gibt.**

* **Caching-Strategie:** Fordere keine neuen Wetterdaten an, wenn ein Datensatz für innerhalb eines Radius von 10 km existiert.  
* **Wahrheitsfunktion (Confidence Score):** Berechne die Genauigkeit dynamisch beim Abruf: $Confidence \= 1.0 \- (Distanz / 50km)$.  
* **API-Trigger:** Rufe Wetter-API nur auf, wenn der confidence\_score unter einen definierten Schwellenwert fällt oder keine Daten vorliegen. 

  ### **WEATHER ENGINE ARCHITECTURE** {#weather-engine-architecture}

* **Step 1 (Historical Bulk): Jährlicher Import aus DWD-"CDC" (FTP/HTTP) für das deutschlandweite Stationsnetz. Parameter: TT\_TU (Temp) und FG\_LUM (Strahlung).**

* **Step 2 (Real-time Fallback): Dynamischer Abruf via API nur für Lücken im Bulk-Bestand.**

## 

## 

# **5\. Prognosis** {#5.-prognosis}

## 5\. 1\. Feiertags- und Kalenderlogik {#5.-1.-feiertags--und-kalenderlogik}

* **Source:** Verwenden Sie die Python-Feiertagsbibliothek für deutsche Bundes- und Landesfeiertage.  
* **Persistence:** Feiertage für das benötigte Analysejahr werden in \`control.holidays\` zwischengespeichert.  
* **Granularity:** Unterstützung für Bundes- (DE), Landes- (ISO-Codes wie BY, NW) und benutzerdefinierte lokale Überschreibungen über die Postleitzahlzuordnung.  
* **Classification:**  Die Engine muss Zeitstempel vor der Datenübergabe an Prophet mit \`is\_holiday: boolean\` kennzeichnen, um ein korrektes Training der Saisonalität zu gewährleisten.

## 5.2. Brückentage   {#5.2.-brückentage}

Wir teilen das Problem in zwei Phasen auf: Identifikation und Verifikation.

Phase A: Identifikation (Statische Logik)  
Deine Holiday-Engine markiert Tage im Kalender vorab als „Potenzielle Brückentage“ (PBT), wenn sie:

- Ein Freitag nach Christi Himmelfahrt/Fronleichnam sind.  
- Ein Montag vor einem Feiertag am Dienstag sind.  
- Tage zwischen Weihnachten und Neujahr sind.

Phase B: Verifikation (Statistische Lastgang-Analyse)  
Die Engine vergleicht nun den Lastgang dieser PBTs mit einem „normalen“ Referenz-Werktag derselben Saison.

- Fall 1: Last sinkt um \>20% \-\> Bestätigter Brückentag (z.B. produzierendes Gewerbe).  
- Fall 2: Last bleibt gleich \-\> Ignorierter Brückentag (z.B. Einzelhandel oder Pflegeheim).  
- Fall 3: Last steigt (selten) \-\> Sonderbetrieb.

## 

## 

## 5.3 PROPHET & Spatial-Temporal Join {#5.3-prophet-&-spatial-temporal-join}

Spatial-Temporal Join (räumlich-zeitliche Verknüpfung) ist das Bindeglied um zwei unterschiedliche Datentypen – Zeitreihen und Geodaten miteinander zu verschmelzen.

###  **A. Die Logik des "Spatial-Temporal Joins"** {#a.-die-logik-des-"spatial-temporal-joins"}

Um Prophet mit Features zu füttern, muss das System für jeden Zeitstempel des Lastgangs (`data.meter_reads`) die geografisch nächste Wetterbeobachtung finden. Da Wetterdaten stündlich vorliegen, die Lastgänge aber 15-minütig sein können, wird ein **Forward-Join** auf Stundenbasis durchgeführt.

### **B. SQL-Referenz-Implementierung (KI-Blueprint)** {#b.-sql-referenz-implementierung-(ki-blueprint)}

Nutze einen `LATERAL JOIN`, um die räumliche Suche (`ST_Distance`) pro Zeitstempel hocheffizient in der Datenbank auszuführen:

`SQL`

`-- Erstellt den Feature-Vektor für das Prophet-Modell`

`SELECT` 

    `m.ts_utc AS ds,` 

    `m.value AS y,`

    `w.temp_c,`

    `w.ghi_wm2,`

    `-- Dynamische Konfidenzberechnung`

    `(1.0 - (ST_Distance(m.geom, w.source_location) / 50000.0)) AS confidence`

`FROM data.meter_reads m`

`LEFT JOIN LATERAL (`

    `SELECT temp_c, ghi_wm2, source_location`

    `FROM data.weather_observations`

    `WHERE ts_utc = date_trunc('hour', m.ts_utc) -- Stündliches Wetter-Matching`

    `ORDER BY m.geom <-> source_location        -- Spatial Index Operator (KNN)`

    `LIMIT 1`

`) w ON true`

`WHERE m.meter_id = :target_meter_id`

`AND m.ts_utc BETWEEN :start AND :end;`

### 

### **C. Prophet Feature Engineering Pipeline** {#c.-prophet-feature-engineering-pipeline}

1. **Data Fetching:** Lade das SQL-Ergebnis direkt in einen Polars DataFrame.

2. **Imputation Check:** Falls `confidence < 0.5`, triggere einen asynchronen API-Call für die exakte Koordinate und wiederhole den Join.

3. **Regressoren:** Füge `temp_c` und `ghi_wm2` als "Additional Regressors" zum Prophet-Modell hinzu.

4. **Lag-Handling:** Berücksichtige thermische Trägheit durch Erstellung von Lag-Features (z.B. `temp_c_lag_2h`), falls im `AnalysisProfile` gefordert.

### 

### **Skalierungs-Vorgabe (Worker-Prinzip)** {#skalierungs-vorgabe-(worker-prinzip)}

* Prophet-Berechnungen dürfen **nie** im Hauptthread der API laufen.

* Jeder Forecast-Job wird in einen isolierten Python-Container oder Celery-Worker ausgelagert, der nur lesend auf die `AnalysisProfile` Artefakte zugreift.

## 5.4 „Ausrollen“ (Projektion in Zielzeitraum) {#5.4-„ausrollen“-(projektion-in-zielzeitraum)}

**Ziel:** Historische Muster sinnvoll auf die Zukunft übertragen.  
Kats/Prophet (Meta) **Strategien (kombinierbar):**

1. **Kalender-Mapping:** Passende Tagesklassen (Mo–So, Feiertage etc.) 1:1/nearest-neighbor auf Zieltermine legen.

2. **Wetter-konditioniert:** Für Zieltage ähnliche Wetterlagen aus Vergangenheit wählen (z. B. k-NN auf \[Temp,GHI,Tagestyp\]).

3. **Skalierung:** Wachstum/Lastverschiebung, Öffnungszeiten, Effizienzmaßnahmen.

4. **Asset-Szenarien:** PV/ Speicher-Profile hinzufügen/entfernen.

5. **Energie-/Monatsbudgets:** Optionale Nebenbedingungen, damit Summen (z. B. pro Monat) realistisch bleiben.

6. **DST-Korrekt:** Zielland-DST beachten (92/96/100 Intervalle).

**Output:** Ziellastgang als Intervallreihe inkl. Metadaten/Provenienz.   
**Tools:** Prophet (\!Kompatibilitäten prüfen auf python / 3.x-slim-buster / Container)

# 6\. FINANCIAL Calculations {#6.-financial-calculations}

(HPFC Integration, Constraint-Matrix, "Next-Step" 

##  **6.1 FINANCIAL ENGINE (HPFC Integration)** {#6.1-financial-engine-(hpfc-integration)}

* **Source:** Multi-provider HPFC (Hourly Price Forward Curves) ingestion.  
* **Versioning:** Support for multiple snapshots per provider. Always use the latest available snapshot for the target forecast period unless specified otherwise.  
* **Vector Operation:** Cost calculation is performed as a scalar multiplication of the consumption forecast values ​​from Prophet with the HPFC’s:  
  Total cost \= Consumption/hour (prophet) × Price/hour (HPFC).  
* **Automation:** Ingestion routines must handle CSV/XLSX/API delivery based on a provider\_profile (storing URL/FTP credentials and update frequency).

Da HPFCs (externe Daten) oft geliefert werden (E-Mail/FTP), sollte Claude einen **`Dropzone-Watcher`** oder einen **`API-Poller`** bauen, der neue Dateien erkennt, via Polars validiert und in die TimescaleDB schiebt.

## **6.2 (not yet) BIDIREKTIONALE ENGINE** (Reverse Feedback) {#6.2-(not-yet)-bidirektionale-engine-(reverse-feedback)}

* **Grundsatz:** Keine Ablehnung ohne Lösungsvorschlag.  
* **Forward-Impact:** Berechnung des Preiseffekts basierend auf Lastgang und Versorger-Regeln.  
* **Reverse-Feedback:** Definition von Schwellenwerten (Constraints), bei denen Einsparungen triggern (z. B. "Spitzenlast um 15% senken bringt 5% Rabatt").

## 

# **7\. DEFINITION OF DONE (DoD)** {#7.-definition-of-done-(dod)}

1. Code folgt dem Controller-Service-Repository Pattern.  
2. Jeder Task beinhaltet einen Integrationstest.  
3. Data-Lineage ist gewahrt (V2-Daten verweisen auf V1-Original und Analyse-Run-ID).  
   **1\. Controller-Service-Repository Pattern**

Dies ist ein bewährtes Architektur-Muster zur Trennung von Verantwortlichkeiten (Separation of Concerns). Stell dir vor, der Code ist in drei spezialisierte Schichten unterteilt:

* **Controller (Die Schnittstelle):** Er nimmt die Anfragen (z. B. von der FastAPI) entgegen, validiert die Eingabe und gibt die Antwort zurück. Er "weiß" nicht, wie die Logik funktioniert, sondern delegiert nur.  
* **Service (Die Geschäftslogik):** Hier schlägt das Herz der Anwendung. Hier finden die Berechnungen, die Prophet-Analysen und die Wetter-Logik statt.  
* **Repository (Der Datenzugriff):** Diese Schicht spricht exklusiv mit der Datenbank (SQLAlchemy/PostgreSQL). Sie kümmert sich nur um das Speichern und Laden von Daten.  
  **2\. Integrationstests für jeden Task**

Im Gegensatz zu Unit-Tests (die nur kleine Code-Schnipsel isoliert prüfen) testen **Integrationstests**, ob das Zusammenspiel der Komponenten funktioniert:

* Es wird geprüft, ob der Service die Daten korrekt aus dem Repository lädt, sie verarbeitet und der Controller das richtige Ergebnis liefert.  
* **Ziel:** Sicherstellen, dass neue Funktionen keine bestehenden Prozesse (wie den Spatio-Temporal Join) beschädigen.  
  **3\. Data-Lineage (Daten-Provenienz)**

Dies ist die "Geburtsurkunde" deiner Daten. In einem komplexen System wie LOAD-GEAR, das Daten transformiert (v1 → v2 → v3), muss man jederzeit beweisen können, woher ein Wert kommt:

* **V2-Daten verweisen auf V1-Original:** Wenn ein korrigierter Lastgang (v2) eine Spitze glättet, speichert das System die ID der ursprünglichen CSV-Datei (v1), aus der dieser Wert stammt.  
* **Analyse-Run-ID:** Jeder Forecast oder jede Bereinigung ist mit einer eindeutigen `job_id` oder `analysis_run_id` verknüpft.

# **10\. solution while programming**

1. ***WICHTIG*** **Fehler-Handling & Retry-Strategien:** Es gibt zwar einen `status` in der `jobs`\-Tabelle, aber keine Logik für:  
- Was passiert, wenn `kats-analyse` fehlschlägt? Soll der `kats-forecast` mit Standardwerten laufen oder abbrechen?  
* grundlegende Fehlerbehandung ist in dieser Präsentationsphase notwendig

2. ***WICHTIG*** **Infrastruktur-Broker:** Der "Container-Schnitt" ist da, aber der **Kleber** fehlt.  
   1. Wie kommunizieren die Container? (z.B. Task-Queue via Redis/RabbitMQ oder eine rein zustandsgesteuerte Datenbank-Pipeline?).  
* containerisiert innerhalb der API? Ja/Nein beides ist möglich

3. **Sicherheit & Mandantenfähigkeit:** Dieser Punkt bleibt **offen**. Das Dokument erwähnt zwar `company` im Job-JSON, aber es fehlen weiterhin Angaben zu:  
   * Authentifizierung (JWT, OAuth2?).  
   * Data-Isolation (Trennen wir Daten auf DB-Schema-Ebene pro Firma oder nur durch eine `company_id` Spalte?).  
* (not yet) keine Sicherheit in dieser Präsentationsphase notwendig

4. ***Authentication/Authorization** — weiterhin kein Wort. Für einen Energie-SaaS mit Kundendaten kritisch.*  
* (not yet)

5. 

# **11\. real openpoints**

1. ***WICHTIG API-Endpoint-Definitionen** —keine REST-Endpoint beschrieben. Die Pipeline ist jetzt als Container-Workflow klar, aber die Frage bleibt:*   
   *Wer triggert `kats-ingest`? Ein `POST /jobs` Endpoint?*   
   *Ein Queue-Event? Wie fragt das Frontend den Status ab — `GET /jobs/{job_id}`?*   
   *Ein Agent müsste die gesamte FastAPI-Schicht noch erfinden.*  
* API Endpoints \- dringend definieren

2. ***Inkonsistenzen WICHTIG Wetter***   
   ***`normalized` als Speicherort** — Dokument 2 schreibt mehrfach in eine `normalized`\-Tabelle/Bucket (v1, v2), die in Dokument 1 nicht vorkommt. Im ersten Spec landen die Daten direkt in `data.meter_reads` mit `version`\-Flag.* 

   *Jetzt scheint es einen separaten `normalized`\-Layer zu geben. Doppelte Datenhaltung oder Ersatz?*

   ***`kats-qa` schreibt `normalized/_v2`** — laut Container-Tabelle erzeugt der QA-Container bereits v2. Aber Phase 4 (Analyse/Imputation) beschreibt ebenfalls das Erzeugen von v2 als Imputation-Output. Wer ist der echte Eigentümer von v2? QA oder Analyse?*

3. ***Inkonsistenzen WICHTIG Daten*** **Datenspeicherung (Files vs. DB):**  
   * Phase 2 sagt: Normierte Serie → "TimescaleDB \+ Object-Storage".  
   * Phase 3 sagt für den Output: "Korrigierte Serie → `normalized` \+ Verweis in `quality_runs`".  
   * **Frage:** Speichern wir die Zeitreihen für jeden Zwischenschritt (v1, v2, v3) redundant sowohl in der SQL-Datenbank (für Abfragen) *als auch* als CSV im GCS (für Bulk-ML-Training)? Das hat massive Auswirkungen auf die Kosten und die Synchronität

# **12\. Fragen die zur Programmierung helfen**

### **Zur Authentifizierung & zum Job-Eingang**

*"Wer ruft Phase 1 auf — REST-Endpoint, Message-Queue, oder beides? Gibt es Auth (OAuth2, API-Key)? Wie kommt die Quelldatei in GCS — Upload durch den Client direkt, oder über euren Ingest-Service?"*

Das Dokument beschreibt den Input als "Nutzer-Formular (Web/Mobile, Spracheingabe)" ohne eine einzige API-Route.

### **Zur Fehlerbehandlung zwischen Phasen**

*"Was passiert wenn Phase 2 einen unbekannten Dateityp erhält? Wird der Job auf `failed` gesetzt und der User benachrichtigt, oder gibt es einen manuellen Review-Schritt? Wie kommunizieren die Container Fehler untereinander — über die `jobs`\-Tabelle, oder über eine separate Queue?"*

Kein Retry-Konzept, kein Dead-Letter-Mechanismus dokumentiert.

### **Zum `ReaderProfil` (Phase 2a → 2b)**

*"Das ReaderProfil ist als JSON beschrieben — gibt es ein Schema (Pydantic-Model, JSON Schema)? Wird es persistiert, oder ist es nur ein In-Memory-Zwischenobjekt zwischen 2a und 2b?"*

### **Zur Wetterstation-Zuordnung (Phase 4.2)**

*"DWD-API: Welcher konkrete Endpoint — CDC Open Data, Brightsky, oder direkter FTP? Wie geht ihr mit Wetterstationen um, die nicht die volle historische Abdeckung haben? Ist die Haversine-Suche eine eigene Tabelle oder on-the-fly?"*

### **Zum Versionierungskonzept (`v1` / `v2`)**

*"normalized\_v1 \= Original, v2 \= imputiert — sind das separate GCS-Objekte mit eigenem Pfad, oder Versionen im selben Bucket? Wie referenziert `meter_reads` die beiden Versionen — Foreign Keys auf eine `file_versions`\-Tabelle?"*

### ***2\. `tasks[]` ist undefiniert in der Ausführung***

*Die Liste `{Statistik, Fehleranalyse, Umformatierung, Imputation, Prognose, Aggregation}` erscheint im Job, aber nirgends steht, **wie ein Job ohne `Prognose` durch die Pipeline läuft**. Überspringt er Phase 5? Was ist der Output-Kontrakt für "nur Statistik"?*

### ***3\. Phase 4.3 ist als `(not yet)` markiert — aber der Imputation-Algorithmus referenziert sie***

*"Asset-bereinigt (4.3)" steht als Schritt 3 im Imputation-Stack — aber 4.3 ist nicht implementiert. Ein Agent würde hier fragen: "Soll ich 4.3 als No-Op/Stub implementieren, oder die Imputation ohne diesen Schritt bauen?"*

### ***4\. `output_format: EDIFACT` ohne Spezifikation***

*EDIFACT/MSCONS ist ein komplexes Format mit Subsets. Der Agent hat keine Chance ohne:*

* *Welches MSCONS-Subset (UTILMD? MSCONS?)*

* *Welche Qualifier-Codes*

* *Validierungsregeln*

### ***5\. Szenarien-Logik (`scenarios{}`) völlig offen***

*`Wachstum %, PV an/aus, Speicher-Config` — aber wie werden diese Parameter in Prophet-Regressoren übersetzt? Das ist das Herzstück der Business-Logik und fehlt komplett.*

### ***6\. Keine Concurrency-/Locking-Strategie***

*Wenn zwei Jobs denselben `meter_id`\-Zeitraum gleichzeitig berechnen — wer gewinnt? Gibt es einen Lock auf `meter_id + horizon`?*

### ***A. Die "v2"-Identitätskrise (Eigentumsfrage)***

*Das ist der größte Blocker.*

* ***Phase 3 (`kats-qa`)** sagt: Ich schreibe `normalized/_v2`.*  
* ***Phase 4 (`kats-analyse`)** sagt: Ich mache die Imputation und erzeuge `normalized_v2`.*  
* ***Der Kopfschüttel-Moment:** Die KI weiß nicht, wer die "v2" besitzt. Wenn die QA Lücken nur erkennt, aber die Analyse sie füllt, wer darf die finale Version 2 in die Datenbank schreiben? Ohne Klärung würde die KI hier zwei konkurrierende Schreib-Logiken programmieren.*

### ***B. Die "Storage-Schizophrenie" (DB vs. Object Store)***

* *Das Dokument schwankt zwischen "TimescaleDB für Massendaten" und "GCS/MinIO für normierte Serien".*  
* ***Der Kopfschüttel-Moment:** Bei 15-Minuten-Intervallen über Jahre entstehen Millionen Datenpunkte. Ein Agent würde fragen: "Soll ich die Zeitreihe beim Ingest in die Hypertable streamen ODER als Parquet/CSV ins GCS legen?" Beides redundant zu führen (wie in Punkt 11.3 angedeutet), führt ohne klare "Source of Truth"-Definition zu Synchronisationsfehlern.*

### ***C. Der fehlende "Kleber" (Orchestrierung)***

* *Du hast Container definiert, aber keinen **Workflow-Manager**.*  
* ***Der Kopfschüttel-Moment:** Wie erfährt Phase 3, dass Phase 2 fertig ist? Wenn die KI die API bauen soll, fehlen die Webhooks oder die Task-Queue (z.B. Celery/RabbitMQ). Ein Agent kann keinen "Service" bauen, der nur im luftleeren Raum existiert.*

