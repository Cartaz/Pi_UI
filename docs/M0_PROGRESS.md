# M0 — Stato di avanzamento

Aggiornamento: 8 settembre 2026.

Questo documento registra evidenze incrementali della milestone M0 senza dichiarare completati i gate che richiedono la configurazione Pi/Ornith reale sulla LAN e la macchina CachyOS target.

## Implementato e verificato in CI

### Fondazione core e configurazione

- `core/settings.py`: settings tipizzati, percorsi XDG per le preferenze globali, validazione, migrazioni di schema, scrittura atomica con `fsync`/`os.replace`, preservazione e recupero da file JSON malformato o non compatibile.
- Settings schema 4: timeout distinti per startup processo, acknowledgement RPC, inattività del turno e shutdown.
- Configurazione provider/modello Pi derivabile dallo stato canonico Pi_UI, con credenziali soltanto tramite riferimenti a variabili d'ambiente.
- Discovery read-only di un `AIOS_ROOT/.pi-agent/models.json` esistente, senza restituire credenziali letterali e senza adottarlo o sovrascriverlo implicitamente.
- Fingerprint SHA-256 della baseline esistente e verifica immediatamente prima del launch; una modifica nel frattempo blocca l'avvio.
- Un `models.json` presente ma corrotto/non interpretabile non fa fallire l'avvio della GUI: produce zero profili utilizzabili e impedisce il connect.

### Bubblewrap launch specification

- AIOS root host montata come `/workspace`, unico albero personale read-write previsto.
- Runtime `/opt/pi-agent` e `/usr` read-only; home/tmp sintetici, configurazione/sessioni Pi in `/workspace/.pi-agent`.
- Rete host condivisa per mantenere la connettività LAN; questa scelta **non** limita le destinazioni di rete.
- Ambiente child allow-list: HOME/PATH/locale, variabili Pi e soltanto l'eventuale variabile credenziale nominata nei settings. `DISPLAY`, `SSH_AUTH_SOCK` e ambiente desktop non vengono copiati implicitamente.
- Alias FHS `/bin`, `/sbin`, `/lib`, `/lib64` ricreati verso `/usr` quando necessari.
- Nessun fallback automatico sandbox → host.

Questa parte è verificata come costruzione deterministica dell'argv/ambiente. L'efficacia reale del namespace Bubblewrap resta da provare sulla macchina target.

### RPC, stato e process lifecycle

- `core/agent/protocol.py`: JSONL incrementale con LF stretto, CRLF tollerato, UTF-8 spezzato, più record per chunk, EOF parziale, record non validi e limiti dimensionali.
- `AgentClient`: request ID, correlazione, prompt/steer/follow-up, `get_messages`, stato turno e stop `clear_queue → abort`.
- L'ACK positivo del prompt è distinto dal completamento; `agent_settled` riporta il turno a idle.
- Deadline RPC per richiesta: se manca l'ACK, Pi_UI **non reinvia** il comando. Per un prompt l'esito diventa `uncertain` e nuovi invii restano bloccati fino alla riconciliazione della sessione.
- Watchdog di inattività separato: segnala un turno silenzioso senza uccidere Pi, senza retry e lasciando Stop disponibile.
- `QProcessAgentTransport`: stdout RPC e stderr diagnostico separati, startup/shutdown asincroni, `terminate()` con escalation temporizzata a `kill()`, nessun `waitFor*` nel GUI thread.
- `AppShutdownCoordinator`: la chiusura dell'ultima finestra mantiene vivo l'event loop Qt mentre QProcess completa lo shutdown; un watchdog applicativo finale evita un hang infinito.

### Prima shell Qt Quick

- Entry point `pi-ui` con `QApplication` + `QQmlApplicationEngine` e wiring soltanto in `main.py`.
- Controller Python presentation-independent.
- `AgentAdapter` focalizzato e due `QAbstractListModel` per profili e transcript.
- QML dark-neumorphic con Theme, RaisedSurface, InsetSurface e NeuButton centralizzati.
- Workspace/profile selection, connect/disconnect, cronologia via RPC, transcript virtualizzato, composer, send e stop collegati a operazioni reali.
- Dipendenze backend QML dichiarate come proprietà `required` e inizializzate con `setInitialProperties()`.

## Evidenze CI osservate

Il gate ospitato GitHub attuale esegue, su Python 3.12 e 3.13:

1. installazione PySide6 6.11.x e dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

Sul head della PR M0 timeout/lifecycle questi quattro step sono stati osservati verdi su entrambe le versioni Python. La suite include un vero subprocess RPC sintetico, caricamento QML offscreen, scheduler Qt, timeout RPC/inattività, configurazione corrotta e un subprocess che installa un handler SIGTERM, segnala readiness, ignora `terminate()` e viene poi chiuso tramite l'escalation temporizzata del transport.

Queste sono prove su runner ospitato e dati sintetici. **Non sono** prove della configurazione privata dell'utente o del confinement Bubblewrap reale.

## Contratti upstream usati

### Pi

La documentazione ufficiale corrente di Pi conferma:

- `pi --mode rpc` via stdin/stdout JSONL;
- LF come delimitatore e ID opzionali per correlazione;
- ACK prompt distinto dal completamento;
- `agent_settled` dopo retry/compattazione/continuazioni automatiche;
- `clear_queue` prima di `abort` per uno stop interattivo con recupero della coda;
- `--session-dir`, `PI_CODING_AGENT_SESSION_DIR` e `PI_CODING_AGENT_DIR` per isolamento;
- estensioni, skill, prompt template e package come primitive upstream da esporre senza forkare Pi.

Riferimenti primari:

- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md

Questi link seguono il ramo upstream corrente. M0 deve ancora fissare e provare la versione Pi esatta realmente usata dall'utente.

### Bubblewrap

Bubblewrap costruisce un mount namespace la cui esposizione dipende dagli argomenti dichiarati. Pi_UI usa questo meccanismo per progettare il confine filesystem, non la sola convenzione del workspace. La rete è un confine distinto: `--share-net` mantiene la LAN ma non applica egress filtering.

Riferimenti:

- https://github.com/containers/bubblewrap/blob/main/README.md
- https://man.archlinux.org/man/bwrap.1.en

## Politica aggiornamenti e personalizzazione Pi

1. **Runtime isolato:** configurazione/sessioni dell'app non devono modificare l'installazione Pi globale dell'utente.
2. **Nessun auto-update implicito:** aggiornamenti Pi saranno un'azione GUI esplicita con compatibility gate e rollback.
3. **Inferenza canonica nei settings:** endpoint, provider/API, model ID, contesto, output e thinking appartengono al servizio settings; `models.json` gestito è derivato da questo stato.
4. **Baseline utente preservata:** un `models.json` preesistente può essere usato read-only dopo discovery/fingerprint; non viene adottato silenziosamente.
5. **Personalizzazioni dalla GUI:** estensioni, skill, prompt e package verranno mostrate/gestite usando capacità upstream di Pi con origine/versione/trust visibili.
6. **Subagents:** la roadmap registra un futuro sistema di gestione di prima classe, ma orchestrazione/parallelismo/memoria condivisa restano da progettare sui casi d'uso reali.

## Lavoro M0 ancora aperto

### Può essere preparato senza la macchina target

- Preflight/diagnostica applicativa che raccolga in modo non mutante versioni/runtime/path e produca un manifest sanitizzato.
- UI del preflight e report locale per rendere il test target un singolo workflow guidato.
- Checklist automatizzata dei tentativi di accesso che Pi dovrà eseguire dentro Bubblewrap.
- Verifica/aggiornamento della documentazione di installazione e troubleshooting sulla base del preflight.

### Richiede la macchina/rete dell'utente

- Inventario reale: Pi package/versione, Node, build llama.cpp, model ID, quantizzazione, template, tool/reasoning, context window e parametri della baseline.
- Pin della versione Pi/Node effettivamente compatibile.
- Conferma del provider/API/model ID/capabilities contro Ornith reale.
- Prove Bubblewrap su CachyOS: accesso fuori `/workspace`, symlink verso l'esterno, HOME reale, socket desktop, process discovery, shell/tool figli e shutdown/orfani.
- Tre sessioni Pi–Ornith consecutive, streaming, stop, resume sessione, tool di lettura/modifica file, errore server e riavvio.
- Verifica grafica reale su KDE/Wayland e GPU target.

M0 resta quindi **in corso**. Il prossimo obiettivo prima dell'intervento dell'utente è costruire il preflight/diagnostica e la procedura di gate locale.