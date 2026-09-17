# Contratto di sviluppo — Pi_UI

## Scopo e stato

Costruire un AI OS desktop personale: uno spazio di conoscenza, più conversazioni, chat prioritaria e gestione file centrale. Pi è l'harness scelto; Ornith 1.5 gira su server LAN. Non trasformare il prodotto in un IDE o in un gestore multiprogetto.

**Stato attuale:** M0 completata; M1 in corso. La GUI, la chat Pi e il browser/preview read-only esistono già. Distinguere sempre funzioni esistenti, proposte e verifiche realmente eseguite. Leggere README, ROADMAP, docs/M0_PROGRESS.md, docs/M1_PROGRESS.md e docs/AUDIT_REMEDIATION.md prima di modificare il codice.

**Blocco di sicurezza temporaneo:** fino a versionamento pre-scrittura, conflitti e ripristino provati per ogni tool, Pi vede i documenti nel workspace in sola lettura. La sola sottodirectory `.pi-agent` è montata read-write per sessioni/config Pi. Non riabilitare scritture ai documenti modificando i mount o la configurazione, né presentare come operativo il tool-write di M0. Il test reale della nuova policy Bubblewrap sul target è ancora obbligatorio.

## Architettura vincolante

- Python 3.12+ → PySide6/Qt 6.11+ → QApplication + QQmlApplicationEngine → Qt Quick/QML.
- `main.py` fa solo wiring: logging, settings, servizi/controller, adapter/modelli, engine, integrazione nativa e lifecycle.
- `core/` possiede comportamento sostanziale, regole, algoritmi, persistenza e interfacce dei servizi; mantenerlo indipendente da Qt dove praticabile.
- Il controller coordina servizi focalizzati. Ogni stato importante ha un solo proprietario. Evitare god object e astrazioni speculative.
- `ui/` contiene integrazione Qt, adapter QObject con `@Slot` tipizzati e modelli Qt. Gli adapter convertono/validano input UI senza duplicare regole o filesystem policy.
- QML possiede presentazione, animazioni e stato temporaneo di interazione. Niente networking, file/settings o stato operativo canonico in QML.
- Liste non banali con QAbstractListModel e ruoli stabili; il browser M1 attuale utilizza intenzionalmente un `QAbstractListModel` piatto con ruoli `depth` e caricamento lazy. Prima di migrare a un modello gerarchico, dimostrare limiti concreti e preservare il comportamento.
- Pi possiede sessioni e ciclo agente; Python mantiene una proiezione UI ricostruibile, senza un secondo archivio canonico dei messaggi.
- Nessun WebEngine, QWebChannel, UI HTML/CSS/JS o stack alternativo senza necessità concreta e decisione documentata.
- Un'eventuale estensione TypeScript di Pi è un confine di integrazione necessario, non un secondo backend: niente indice, policy o persistenza duplicati.

## Sistema visivo

Centralizzare in `Theme.qml`: superficie `rgb(20,20,20)`, accento `rgb(255,102,0)`, testi `rgb(225,225,225)` / `rgb(135,135,135)` / `rgb(90,90,90)`, Noto Sans, raggi 28/22/16/12 px.

Le card mantengono la superficie base. Gerarchia mediante spaziatura, tipografia e profondità. Pannelli principali in rilievo forte; header/card/righe in rilievo morbido; campi, badge, toggle e pressione incassati; selezione incassata con testo arancione e glow/focus contenuto. L'arancione indica stato e non definisce geometria.

Calibrazione: forte dark +8,+8 / blur 20 / alpha .62, light -6,-6 / 15 / .10; soft dark +3.5,+3.5 / 10 / .46, light -3,-3 / 8.5 / .075; hover circa +4.5,+4.5 / 12 e -3.8,-3.8 / 10; inset dark +3.4,+3.4 / 7 e light -3.1,-3.1 / 6.

Componenti condivisi: RaisedSurface, InsetSurface, NeuButton, NeuToggle quando serve un toggle, e righe. Non duplicare stack di effetti. Preferire QtQuick.Effects.RectangularShadow per rilievo/glow; `cached: false` di default, caching solo dopo misure.

ShaderEffect/SDF consentito per un inset non ottenibile con qualità sufficiente da componenti semplici: nascondere la complessità in un componente, sorgenti in `ui/qml/shaders/`, bake con `pyside6-qsb --qt6` della venv, varianti richieste incluse GLSL Linux/OpenGL e fallimento esplicito su errore. Non applicare shader pesanti a ogni delegate.

Controlli semantici, tastiera, focus visibile, Accessible, contrasto, layout responsive. Hover/pressed/selected/disabled distinti ma sobri; animazioni 80–200 ms. Non usare il colore muted per contenuti essenziali senza verificarne il contrasto.

## Prestazioni, settings e lifecycle

- ListView/TableView per collezioni dinamiche, `reuseItems: true` dove applicabile. Delegate piccoli, senza stato persistente, clip/layer/effects superflui. Cache minima finché non profilata.
- Un'unica astrazione settings Python, default nel codice, migrazioni e recupero da configurazione malformata. `pathlib.Path` e percorsi XDG.
- Nessun lavoro pesante o attesa bloccante nel thread GUI. Worker/processi con proprietario esplicito, cancellazione e shutdown deterministico.
- Pi tramite QProcess asincrono, stdout protocollo separato da stderr. Nessun processo orfano, fallback silenzioso o interpolazione shell non fidata; evitare `shell=True`.
- Qt gestisce finestre, shortcut, tray se necessario e integrazione piattaforma. URL esterni nel browser di sistema.
- Misurare memoria Linux con PSS da `/proc/<pid>/smaps_rollup`; non sommare RSS come memoria fisica. Dichiarare separatamente il server LAN.
- Originali e memoria utente fuori dal repository. Indice ricostruibile; niente credenziali o contenuti privati in log/fixture/commit.
- Selezionare una cartella non realizza una sandbox. Non dichiarare isolamento senza enforcement di sistema e prove sugli strumenti realmente abilitati.
- Bubblewrap è obbligatorio nel lancio ordinario anche quando un'impostazione preesistente chiede il contrario: fallire prima di avviare Pi, mai lanciare direttamente.

## Installazione e verifiche

`install.sh` non è ancora implementato: quando introdotto sarà Bash, CWD-independent, idempotente, con `set -Eeuo pipefail`: crea/ripara `.venv`, installa dipendenze fissate e verifica import, QML e shader. Usare tool della venv coerenti con PySide6. Non creare un installer che finga un'app funzionante.

Usare logging Python, mai ingoiare eccezioni. Per cambi applicativi: verifiche pertinenti compileall, pytest, ruff se adottato, QML lint/load/offscreen e shader. Testare core, controller, settings, adapter/modelli e lifecycle. Offscreen non dimostra qualità degli shader su GPU.

Test con LLM reale solo nella LAN dell'utente. CI ordinaria su runner GitHub ospitati, con fixture sintetiche e processi di test; nessun self-hosted runner o accesso CI alla LAN. Mocks ammessi nei test, mai come successo di produzione.

## Metodo e completamento

Prima di modificare: ispezionare moduli, ownership, test e comportamento. Per decisioni non banali confrontare alternative, definire stato canonico/API/errori/concorrenza/persistenza, implementare backend → API minima → QML → verifiche.

Preservare architettura sana e parità dei workflow nelle migrazioni. Migrare una schermata alla volta, verificare comportamento/tastiera/lifecycle/memoria e rimuovere vecchia UI solo dopo parità. Rivedere a ogni milestone duplicazioni, confini e soluzioni tattiche.

Ogni consegna deve riportare cosa cambia, prove eseguite, limiti e lavoro incompleto. Aggiornare roadmap e decisioni con evidenze; nessun placeholder operativo, controllo scollegato, hardcoded success o validazione disabilitata. Per sola documentazione verificare coerenza, link interni e diff; non dichiarare test applicativi inesistenti.
