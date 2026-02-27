  
**CLAUDE CODE**

Agentisches Projekt-Framework

*Vollständige Anleitung für die Planung und Steuerung agentischer Softwareentwicklung*

Version 1.1 – Februar 2026

| Zweck dieses Dokuments Dieses Dokument beschreibt das vollständige Framework für die Zusammenarbeit zwischen Mensch und KI-Agent in einem Claude Code Projekt. Es richtet sich an den Menschen, der die Projektplanung übernimmt, und definiert alle Strukturen, Konventionen und Abläufe, die für eine zuverlässige agentische Softwareentwicklung notwendig sind. |
| :---- |

## **Die fünf Säulen**

Das Framework basiert auf fünf Säulen, die alle Vorbereitungsarbeiten abdecken:

| Säule | Bereich | Kernfrage |
| :---- | :---- | :---- |
| 1 | Input-Dokumentation & Token-Management | Wie bekommt der Agent die richtige Information zur richtigen Zeit? |
| 2 | Projektarchitektur & Modulstruktur | Was wird gebaut und wie ist der Code organisiert? |
| 3 | Aufgabenzerlegung & Task-Planung | Wie zerlegt der Mensch die Arbeit in agententaugliche Tasks? |
| 4 | Instruktionsdesign & Konventionen | Nach welchen Regeln arbeitet der Agent? |
| 5 | Qualitätssicherung & Validierung | Wie stellen wir sicher, dass das Ergebnis funktioniert? |

# **Säule 1 – Input-Dokumentation & Token-Management**

Die zentrale Herausforderung: Der Agent kann nur mit dem arbeiten, was in seinem Kontextfenster liegt. Zu viel Information kostet Token und erzeugt Rauschen. Zu wenig führt zu falschen Annahmen. Die Lösung ist ein Zwei-Schichten-Modell mit strikter Steuerung über Task-Dateien.

## **Das Zwei-Schichten-Modell**

**Schicht A – Immer geladen**

Diese Dokumente sind permanent im Kontext des Agenten. Sie müssen extrem kompakt sein, weil sie bei jedem Arbeitsschritt Token verbrauchen.

| Dokument | Inhalt und Zweck |
| :---- | :---- |
| CLAUDE.md | Projektidentität, Tech-Stack, Coding-Kernregeln, Arbeitsregel. Unveränderlich über die gesamte Projektlaufzeit. |
| STATUS.md | Laufender Arbeitsstand innerhalb der aktuellen Phase. Wird vom Agenten nach jedem Task aktualisiert. Am Phasenende archiviert und geleert. |

| Kernprinzip: CLAUDE.md bleibt unveränderlich Die CLAUDE.md wird nach der initialen Erstellung nie wieder geändert. Alle veränderlichen Informationen – Projektstatus, aktive Phase, Zwischenstände – gehören in die STATUS.md. Die aktive Phase ergibt sich aus der backlog.md und der STATUS.md, nicht aus der CLAUDE.md. |
| :---- |

**Schicht B – Aufgabenbezogen geladen**

Diese Dokumente werden nur geladen, wenn ein Task sie explizit in seiner Lade-Liste aufführt. Die Task-Datei ist die einzige Stelle, die bestimmt, was in den Kontext geladen wird.

* Task-Dateien mit vollständigen Arbeitsanweisungen

* Modul-Spezifikationen

* CODING-GUIDELINES.md

* AGENT-PROTOCOL.md

* Datenbankschema

* API-Spezifikationen

* Testspezifikationen

* Referenzdokumente (externe APIs, Beispiele, Entscheidungsprotokolle)

| Warum keine Schicht C? Ein früherer Entwurf sah eine dritte Schicht für optionales, temporäres Wissen vor. Diese wurde verworfen, weil: (1) Der Agent nicht zuverlässig entscheiden kann, wann er optionale Dokumente laden soll. (2) Anweisungen zum Entladen temporärer Dokumente riskant sind – der Agent könnte bei Iterationen relevantes Wissen ignorieren. (3) Die Token-Kontrolle besser über die Task-Planung gesteuert wird als über Agentenverhalten. Stattdessen wird die Kontextgröße über den Task-Zuschnitt kontrolliert: Wird ein Task zu kontextlastig, wird er in kleinere Tasks aufgeteilt. |
| :---- |

## **Steuerungsprinzip**

Die Task-Datei ist die einzige Stelle, die bestimmt, was in den Kontext geladen wird. Kein Dokument verweist auf später zu ladende Inhalte. Was der Agent nicht sehen soll, wird nicht referenziert. Wenn der Agent es nicht braucht, existiert es für ihn nicht.

## **Die Ordnerstruktur**

/docs  
├── CLAUDE.md  
├── STATUS.md  
├── /architecture  
│   ├── overview.md  
│   └── decisions.md  
├── /modules  
│   ├── auth.md  
│   ├── api.md  
│   └── ...  
├── /schema  
│   └── users.md  
├── /references  
│   ├── external-apis.md  
│   └── examples/  
└── /tasks  
    ├── backlog.md  
    ├── task-001.md  
    ├── task-002.md  
    └── ...

## **Der Status-Lebenszyklus**

Die STATUS.md durchläuft in jeder Phase denselben Zyklus:

1. Während einer Phase: Der Agent dokumentiert Entscheidungen und Entscheidungsgründe nach jedem abgeschlossenen Task in der STATUS.md.

2. Am Phasenende: Der Agent überführt den gesamten Inhalt der STATUS.md in eine Archivdatei (z.B. phase-1-complete.md).

3. Nach der Überführung: Die STATUS.md wird geleert und steht für die nächste Phase bereit.

4. Ein kontrollierender Agent kann jede abgeschlossene Phase unabhängig prüfen, indem er die entsprechende Archivdatei liest.

/docs  
├── STATUS.md                    ← aktuelle Phase, wird befüllt  
└── /status  
    ├── phase-1-complete.md      ← abgeschlossen, vollständig  
    ├── phase-2-complete.md  
    └── ...

# **Säule 2 – Projektarchitektur & Modulstruktur**

Säule 2 produziert die technischen Dokumente, die als Schicht-B-Inhalte in den Task-Dateien referenziert werden. Sie beantwortet: Was wird gebaut und wie ist der Code organisiert?

## **2.1 – Technische Zielarchitektur**

Das Gesamtbild der Software auf höchster Ebene: Welche großen Bausteine gibt es, wie kommunizieren sie miteinander, welche Architekturmuster werden verwendet. Dieses Dokument liegt unter /docs/architecture/overview.md.

## **2.2 – Modulaufteilung**

Jedes Modul erhält ein eigenes Spezifikationsdokument unter /docs/modules/. Es beschreibt: Verantwortung des Moduls, Endpunkte oder Funktionen, Datenstrukturen, Abhängigkeiten zu anderen Modulen.

| Wichtig: Keine versteckten Abhängigkeiten Jedes Schicht-B-Dokument muss so geschrieben sein, dass der Agent es versteht, ohne gleichzeitig andere Schicht-B-Dokumente geladen zu haben – es sei denn, die Task-Datei lädt beide explizit zusammen. Wenn die auth.md das Datenbankschema braucht, muss die Task-Datei beides auflisten. |
| :---- |

## **2.3 – Ordner- und Dateistruktur des Codes**

Die physische Organisation der Codebasis: Wo liegen Components, Services, Utils, Types, Tests. Diese Struktur muss vor dem ersten Task feststehen, damit der Agent weiß, wohin er Code schreibt.

## **2.4 – Abhängigkeiten und Schnittstellen**

Welches Modul ruft welches auf, welche Daten fließen wohin, welche externen Libraries werden genutzt. Liegt unter /docs/architecture/overview.md und verhindert, dass der Agent unkontrolliert Kopplungen einbaut.

## **2.5 – Datenbankdesign**

Schema, Relationen, Migrations-Strategie. Die Grundlage, auf der alle Module aufbauen. Liegt unter /docs/schema/.

# **Säule 3 – Aufgabenzerlegung & Task-Planung**

Diese Säule richtet sich an den Menschen. Sie beschreibt, wie die Gesamtarbeit in Tasks zerlegt wird, die der Agent zuverlässig abarbeiten kann. Die Qualität der Task-Planung bestimmt die Qualität der Ergebnisse.

## **3.1 – Task-Zuschnitt**

Die entscheidende Begrenzung ist das Kontextfenster. Wenn alle Lade-Dokumente plus der zu schreibende Code zusammengenommen den Kontext sprengen, muss der Task kleiner werden.

| Faustregel für den Task-Zuschnitt Zählen Sie die Lade-Dokumente in der Task-Datei. Wenn es mehr als 3–4 substanzielle Dokumente sind, ist der Task wahrscheinlich zu groß. Teilen Sie ihn auf. Lieber zu viele kleine Tasks als zu wenige große. |
| :---- |

## **3.2 – Task-Reihenfolge und Abhängigkeiten**

Jeder Task baut auf einer funktionierenden Basis auf. Der Agent kann kein Modul nutzen, das noch nicht existiert. Keine Vorwärts-Referenzen, keine Annahmen über noch nicht geschriebenen Code. Die Reihenfolge in der backlog.md ist verbindlich.

## **3.3 – Die Task-Datei als vollständiges Arbeitspaket**

Jede Task-Datei muss alles enthalten, was der Agent braucht, um ohne Rückfragen zu arbeiten:

\# Task 003: Auth-Modul implementieren

Lade:  
  \`/docs/modules/auth.md\`  
  \`/docs/schema/users.md\`  
  \`/docs/CODING-GUIDELINES.md\`

Ziel:  
  Login- und Registrierungs-Endpunkte mit JWT-Authentifizierung

Schritte:  
  1\. User-Model gemäß Schema anlegen  
  2\. Registrierungs-Endpunkt POST /api/auth/register  
  3\. Login-Endpunkt POST /api/auth/login  
  4\. JWT-Middleware für geschützte Routen  
  5\. Unit-Tests für alle Endpunkte

Akzeptanzkriterien:  
  \- Registrierung erstellt User in DB mit gehashtem Passwort  
  \- Login gibt JWT mit exp-Claim zurück  
  \- Ungültige Credentials geben 401 zurück  
  \- Alle Tests bestehen

Einschränkungen:  
  \- Keine OAuth-Integration (kommt in Task 007\)  
  \- Keine Passwort-Reset-Funktion (kommt in Task 008\)

## **3.4 – Der Arbeitszyklus**

Der Agent folgt einem festen Zyklus, der in der CLAUDE.md als Arbeitsregel definiert ist:

1. Agent liest CLAUDE.md (Schicht A)

2. Agent öffnet backlog.md, findet den nächsten offenen Task

3. Agent öffnet die entsprechende task-xxx.md und lädt die genannten Dokumente

4. Agent arbeitet den Task ab

5. Agent dokumentiert Entscheidungen in der STATUS.md

6. Agent hakt den Task in der backlog.md ab

7. Zurück zu Schritt 2

8. Bei Phasengrenze: Stopp, Freigabe abwarten

## **3.5 – Die backlog.md**

Die backlog.md ist die geordnete Liste aller Tasks mit Phasengrenzen:

\# Task-Backlog

\#\# Phase 1 – Grundgerüst  
1\. \[x\] task-001.md – Projekt-Setup und Konfiguration  
2\. \[x\] task-002.md – Datenbankschema anlegen  
3\. \[ \] task-002r.md – Review: Setup und Schema  
4\. \[ \] task-003.md – Auth-Modul implementieren  
5\. \[ \] task-004.md – Basis-API-Routen  
6\. \[ \] task-004r.md – Review: Auth und API  
7\. \[ \] task-005.md – Integrationstests Phase 1

STOPP – Freigabe für Phase 2 erforderlich

\#\# Phase 2 – Kernfunktionen  
8\. \[ \] task-006.md – User-Verwaltung  
9\. \[ \] task-007.md – ...

## **3.6 – Review-Tasks als fester Bestandteil**

Nach jeweils zwei bis drei regulären Tasks wird systematisch ein Review-Task eingeplant. Diese Reviews sind keine Ausnahme, sondern fester Bestandteil des Arbeitsrhythmus. Der Grund: Viele kleine Review-Token sind günstiger als ein großes Refactoring, bei dem ein Agent mehrere Module gleichzeitig im Kontext halten und aufeinander abstimmen muss.

Review-Tasks sind normale Tasks – sie haben eine Lade-Liste, ein Ziel und Akzeptanzkriterien. Der einzige Unterschied: Sie produzieren keinen neuen Code, sondern prüfen den bestehenden gegen die Architektur.

Beispiel einer Review-Task-Datei:

\# Task 002r: Review Setup und Schema

Lade:  
  \`/docs/architecture/overview.md\`  
  \`/docs/STATUS.md\`

Ziel:  
  Prüfe ob die Entscheidungen aus Task 001 und 002  
  mit der Zielarchitektur vereinbar sind.

Akzeptanzkriterien:  
  \- Keine Widersprüche zwischen Schema und Architektur  
  \- Alle Entscheidungen in STATUS.md sind nachvollziehbar  
  \- Keine Vorwärts-Blockaden für kommende Tasks erkennbar

Bei Befund:  
  Fix-Task erstellen und vor dem nächsten regulären Task  
  in die backlog.md einfügen.

| Kosten-Nutzen-Rechnung Ein Review-Task verbraucht wenig Kontext – er lädt nur die Architektur und den Status, nicht den gesamten Code. Ein Refactoring-Task nach fünf fehlerhaften Tasks dagegen muss mehrere Module laden, verstehen und umbauen. Frühes Erkennen ist immer günstiger als spätes Reparieren. |
| :---- |

## **3.7 – Phasenplanung**

Phasen dürfen nicht zu viele Tasks enthalten. Am Phasenende muss ein kontrollierender Agent alle Task-Ergebnisse und Status-Einträge lesen können, ohne sein Kontextfenster zu sprengen. Fünf bis sieben Tasks pro Phase (inklusive Review-Tasks) ist ein guter Richtwert.

## **3.8 – Typische Fehler bei der Task-Planung**

Der Mensch muss folgende Eigenschaften des Agenten kennen und berücksichtigen:

| Eigenschaft des Agenten | Konsequenz für die Planung |
| :---- | :---- |
| Kennt nur den geladenen Kontext | Alles, was der Agent wissen muss, muss in den Lade-Dokumenten oder der CLAUDE.md stehen. |
| Optimiert lokal, nicht global | Wenn Task 003 eine Entscheidung trifft, die Task 007 unmöglich macht, erkennt er das nicht. Vorausschauende Planung ist Menschensache. |
| Fragt selten nach | Bei Mehrdeutigkeiten trifft er eine Annahme und arbeitet weiter. Klarheit in der Task-Datei ist wichtiger als bei menschlichen Entwicklern. |
| Vergisst zwischen Tasks | Jeder Task ist ein Neuanfang. Wissen aus dem letzten Task existiert nur, wenn es dokumentiert wurde. |

## **3.9 – Agent pro Phase, nicht pro Task**

Idealerweise bearbeitet ein Agent alle Tasks einer Phase am Stück. So behält er den Kontext über Schnittstellen innerhalb der Phase. Erst an der Phasengrenze endet die Session. Das reduziert Schnittstellenprobleme erheblich.

Falls ein Task über eine Session-Grenze läuft, hält die STATUS.md den Zwischenstand fest. Der nächste Agent findet dort alle Informationen, die er zum Weiterarbeiten braucht.

# **Säule 4 – Instruktionsdesign & Konventionen**

Säule 4 ist das Regelwerk für alles, was der Agent tut. Säule 1 sagt, wann er was liest. Säule 2 sagt, was gebaut wird. Säule 3 sagt, wie die Arbeit geplant wird. Säule 4 sagt, wie er sich dabei verhält.

## **4.1 – CLAUDE.md – Das unveränderliche Kerndokument**

Die CLAUDE.md enthält ausschließlich Informationen, die immer gelten und sich nie ändern. Jedes Wort kostet dauerhaft Token. Beispielstruktur:

\# Projektname

Kurzbeschreibung: Was wird gebaut, für wen, warum.

\#\# Tech-Stack  
\- Runtime: Node.js 20 / TypeScript 5.x  
\- Framework: Next.js 14 (App Router)  
\- DB: PostgreSQL \+ Prisma  
\- Auth: NextAuth.js  
\- Testing: Vitest

\#\# Coding-Kernregeln  
\- TypeScript strict mode, keine \`any\`  
\- Jede Funktion hat Error-Handling  
\- Keine Abhängigkeit ohne Freigabe in \`/docs/architecture/dependencies.md\`  
Vollständig: \`/docs/CODING-GUIDELINES.md\`

\#\# Arbeitsregel  
Arbeite nach: \`/docs/tasks/backlog.md\`  
Finde den nächsten offenen Task.  
Öffne die entsprechende Task-Datei.  
Lade alle dort genannten Dokumente.  
Dokumentiere Entscheidungen in: \`/docs/STATUS.md\`

## **4.2 – AGENT-PROTOCOL.md**

Das vollständige Verhaltensprotokoll als Schicht-B-Dokument. Wird von Task-Dateien referenziert, wenn der Agent detaillierte Arbeitsanweisungen braucht. Inhalte:

* Wie geht der Agent an einen Task heran?

* Wie dokumentiert er Entscheidungen in der STATUS.md?

* Wie sieht der Phasenabschluss aus (Archivierung der STATUS.md)?

* Wann stoppt er und wartet auf Freigabe?

* Wie aktualisiert er die backlog.md?

## **4.3 – Dokumentkonventionen**

**Verweisformat**

Alle Verweise auf andere Dokumente folgen einem einheitlichen Format:

Details: \`/docs/architecture/overview.md\`  
Schema: \`/docs/schema/users.md\`  
Vollständig: \`/docs/CODING-GUIDELINES.md\`  
Siehe: \`/docs/modules/auth.md\`

Regeln:

* Kein →, kein \>, keine Sonderzeichen vor Verweisen

* Immer ein beschreibendes Wort vor dem Pfad

* Pfade immer in Backticks und als absolute Pfade ab Projektroot

* Ein Verweis pro Zeile, keine Verschachtelung

**Nicht verwenden**

→ Details siehe \`/docs/...\`  
\> Mehr unter \`/docs/...\`  
\- → \`/docs/...\`  
(Details: /docs/... )

**Header-Format für Schicht-B-Dokumente**

Jedes Schicht-B-Dokument beginnt mit einem standardisierten Header:

\# Auth-Modul Spezifikation  
Schicht: B  
Letzte Aktualisierung: 2026-02-20

## **4.4 – Coding-Konventionen**

Die ausführlichen CODING-GUIDELINES.md enthalten alles, was über die Kernregeln in der CLAUDE.md hinausgeht: Namensgebung, Import-Reihenfolge, Kommentarstil, Fehlerbehandlungsmuster, Testmuster. Dieses Dokument wird als Schicht-B-Dokument von den meisten Coding-Tasks referenziert.

## **4.5 – Commit- und Änderungskonventionen**

Wie dokumentiert der Agent seine Codeänderungen: Commit-Messages, wie wird die backlog.md aktualisiert, wie wird die STATUS.md geschrieben.

# **Säule 5 – Qualitätssicherung & Validierung**

Qualität wird auf drei Ebenen sichergestellt: innerhalb jedes Tasks, am Ende jeder Phase und durch menschliche Prüfpunkte.

## **5.1 – Task-Ebene: Selbstvalidierung**

Der Agent prüft nach jedem Task, ob seine Akzeptanzkriterien erfüllt sind. Das setzt voraus, dass die Task-Datei klare, prüfbare Kriterien enthält.

| Schlecht | Gut |
| :---- | :---- |
| Auth soll funktionieren | Login-Endpunkt gibt bei korrekten Credentials ein JWT mit exp-Claim zurück, bei falschen einen 401 |

## **5.2 – Zwischen-Reviews: Früherkennung von Problemen**

Zwischen den regulären Tasks werden systematisch Review-Tasks eingeplant (siehe Säule 3.6). Dies ist die zweite Sicherungslinie: Während die Selbstvalidierung prüft, ob ein einzelner Task seine eigenen Kriterien erfüllt, prüfen Review-Tasks, ob die bisherigen Ergebnisse im Gesamtkontext stimmig sind.

Der Vorteil gegenüber einer reinen Prüfung am Phasenende: Probleme werden nach zwei bis drei Tasks erkannt, nicht erst nach fünf. Ein kleiner Review-Task verbraucht wenig Kontext. Ein Refactoring-Task, der mehrere fehlerhafte Module gleichzeitig korrigieren muss, verbraucht sehr viel. Frühes Erkennen ist immer günstiger als spätes Reparieren.

Wenn ein Review-Task ein Problem findet, wird ein Fix-Task erstellt und vor dem nächsten regulären Task in die backlog.md eingefügt. So bleibt der Schaden lokal und wird sofort behoben.

## **5.3 – Phasen-Ebene: Integrationskontrolle**

Am Ende einer Phase prüft ein Agent das Zusammenspiel aller Tasks. Er liest die phase-x-complete.md mit allen Entscheidungen, lädt den relevanten Code und prüft, ob die Module korrekt zusammenwirken. Hier werden Schnittstellenfehler gefunden, die innerhalb einzelner Tasks unsichtbar waren.

## **5.4 – Teststrategie**

| Testart | Wann | Wo |
| :---- | :---- | :---- |
| Unit-Tests | Innerhalb jedes Tasks | Im selben Task wie der Code |
| Integrationstests | Am Phasenende | Eigener Task am Ende der Phase |
| End-to-End-Tests | Nach mehreren Phasen | Eigener Task für kritische User-Flows |

## **5.5 – Menschliche Prüfpunkte**

Der Mensch prüft nicht jeden Task einzeln, sondern die Ergebnisse an kritischen Stellen:

* Nach Architektur-Tasks: Stimmt die Richtung?

* An Phasengrenzen: Funktioniert das Gesamtbild?

* Bei Entscheidungen, die spätere Phasen stark beeinflussen

Die phase-x-complete.md gibt dem Menschen alles, was er für die Prüfung braucht: Alle Entscheidungen mit Begründungen aus der gesamten Phase.

## **5.6 – Fehlermanagement**

Fehler werden nicht im laufenden Kontext gefixt. Stattdessen wird ein neuer Task erstellt und in die backlog.md eingefügt:

\# Task 003a: Fix Auth-Token-Validierung

Lade:  
  \`/docs/modules/auth.md\`  
  \`/docs/schema/users.md\`

Fehler: JWT wird ohne Expiry ausgestellt  
Ursache: Task 003 hat Expiry-Config nicht berücksichtigt

Korrektur:  
  1\. Token-Generierung um exp-Claim ergänzen  
  2\. Test für Token-Ablauf hinzufügen

Akzeptanzkriterien:  
  \- Token enthält exp-Claim  
  \- Test validiert Ablauf nach konfigurierter Zeit

| Der geschlossene Kreislauf Fehler aus Säule 5 fließen als neue Tasks zurück in Säule 3\. So bleibt das Prinzip erhalten: Jede Arbeit läuft über eine Task-Datei mit definiertem Kontext. Kein Ad-hoc-Fixing, keine unkontrollierten Änderungen. |
| :---- |

# **Zusammenfassung – Der Gesamtablauf**

Das Framework lässt sich auf einen einfachen Kreislauf reduzieren:

| \# | Schritt |
| :---- | :---- |
| 1 | Mensch erstellt CLAUDE.md, Projektdokumentation (Säule 2\) und backlog.md mit Task- und Review-Dateien (Säule 3\) |
| 2 | Agent liest CLAUDE.md (immer geladen) |
| 3 | Agent öffnet backlog.md, findet nächsten offenen Task |
| 4 | Agent öffnet Task-Datei, lädt genannte Dokumente (Schicht B) |
| 5 | Agent arbeitet Task ab, dokumentiert Entscheidungen in STATUS.md |
| 6 | Agent hakt Task in backlog.md ab, weiter mit Schritt 3 |
| 7 | Alle 2–3 Tasks: Review-Task prüft bisherige Ergebnisse gegen Architektur |
| 8 | Bei Review-Befund: Fix-Task wird erstellt und vor dem nächsten regulären Task eingefügt |
| 9 | Bei Phasengrenze: Agent archiviert STATUS.md, stoppt, wartet auf Freigabe |
| 10 | Mensch prüft Phase anhand der Archivdatei, gibt nächste Phase frei |

## **Die Kernprinzipien**

| 1\. Jede Information existiert genau einmal. 2\. Jedes Dokument hat genau eine Aufgabe. 3\. Zwei Schichten, kein optionales oder temporäres Laden. 4\. Die Task-Datei steuert den Kontext vollständig. 5\. Kontextgröße wird durch Task-Zuschnitt kontrolliert. 6\. CLAUDE.md bleibt unveränderlich. 7\. Die Intelligenz steckt in der Vorbereitung, nicht in der Laufzeit-Entscheidung des Agenten. |
| :---- |

