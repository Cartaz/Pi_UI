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
- Runtime Pi dedicato e `/usr` read-only; home/tmp sintetici, configurazione/sessioni Pi in `/workspace/.pi-agent`.
- HOME sintetica canonica `/home/aios`, non derivata da `$USER` o dalla HOME reale.
- `runtime_root` troppo ampi o sovrapposti al workspace writable vengono rifiutati invece di ampliare implicitamente la superficie leggibile.
- Rete host condivisa per mantenere la connettività LAN e gli strumenti internet; questa scelta **non** limita le destinazioni di rete.
- Ambiente child allow-list: HOME/PATH/locale, variabili Pi e soltanto l'eventuale variabile credenziale nominata nei settings. `DISPLAY`, `WAYLAND_DISPLAY`, D-Bus, `SSH_AUTH_SOCK`, `GPG_AGENT_INFO` e `XDG_RUNTIME_DIR` non vengono copiati implicitamente.
- Alias FHS `/bin`, `/sbin`, `/lib`, `/lib64` ricreati verso `/usr` quando necessari.
- Nessun fallback automatico sandbox → host.
- La policy mount è costruita da un unico modulo (`core/sandbox.py`) riusato sia dal launch Pi sia dal gate attivo, per evitare drift tra sandbox testata e sandbox realmente usata.

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
- `AgentAdapter` focalizzato e `QAbstractListModel` per profili e transcript.
- QML dark-neumorphic con Theme, RaisedSurface, InsetSurface e NeuButton centralizzati.
- Workspace/profile selection, connect/disconnect, cronologia via RPC, transcript virtualizzato, composer, send e stop collegati a operazioni reali.
- Dipendenze backend QML dichiarate come proprietà `required` e inizializzate con `setInitialProperties()`.

### Preflight host integrato

- `PreflightPlanner` read-only: classifica OS, workspace, policy sandbox, Bubblewrap, Pi, runtime root, Node e `models.json` senza modificare il workspace.
- Le versioni Pi/Bubblewrap/Node vengono sondate sequenzialmente con `QProcess`, senza shell, ambiente ridotto, timeout per probe e stdout/stderr separati.
- Node non è considerato valido solo perché eseguibile sull'host: con sandbox attiva deve trovarsi in un albero realmente montato (`/usr` o `runtime_root`).
- Controller, adapter e model diagnostici separati da `AgentController`.
- Cancellazione protetta sia nel runner sia tramite generation token: callback tardivi non possono trasformare una run cancellata in una run completata.
- Manifest diagnostico sanitizzato con redazione dei path locali.
- Pagina `Host checks` nel pannello M0 Preflight della GUI.

### Gate attivo Bubblewrap

Il ramo M0 target-gate introduce un secondo workflow esplicito, separato dal preflight statico. Usa lo stesso builder Bubblewrap del launch Pi e un payload Node controllato, senza contattare Ornith.

Il gate prepara soltanto fixture temporanee app-owned e verifica:

- working directory `/workspace`;
- round-trip di scrittura nella AIOS root;
- impossibilità di leggere un sentinel esterno direttamente;
- impossibilità di raggiungerlo tramite symlink dal workspace;
- ereditarietà del confinement da parte di un child process Node;
- `runtime_root` read-only;
- `/usr` read-only;
- HOME sintetica `/home/aios` realmente presente;
- assenza delle variabili desktop/sessione proibite;
- assenza di `/run/user` dal namespace;
- invisibilità del PID della GUI host nel `/proc` del sandbox.

Il parser del report è fail-closed: schema/check mancanti, duplicati o ambigui non producono un PASS. Fixture interne ed esterne vengono rimosse su successo, errore e cancellazione. Il manifest condivisibile omette i detail raw potenzialmente contenenti path locali.

**Importante:** i test CI verificano planner, argv, parser, lifecycle e QML con dati sintetici. Solo l'esecuzione sul CachyOS dell'utente può costituire evidenza del confinement reale.

## Evidenze CI osservate

Il gate ospitato GitHub esegue, su Python 3.12 e 3.13:

1. installazione PySide6 6.11.x e dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

PR precedenti M0 hanno osservato questi step verdi su entrambe le versioni Python. La suite include subprocess RPC sintetico, caricamento QML offscreen, scheduler Qt, timeout RPC/inattività, configurazione corrotta, escalation terminate→kill, preflight QProcess e test deterministici della policy/gate Bubblewrap.

Il head della PR target-gate deve essere nuovamente verde dopo ogni hardening prima del merge. Queste restano prove su runner ospitato e dati sintetici, **non** prove della configurazione privata dell'utente o del confinement Bubblewrap reale.

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

Bubblewrap costruisce un mount namespace la cui esposizione dipende dagli argomenti dichiarati. Pi_UI usa questo meccanismo per progettare il confine filesystem, non la sola convenzione del workspace. La rete è un confine distinto: `--share-net` mantiene la LAN/internet ma non applica egress filtering.

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

### Richiede la macchina/rete dell'utente

- Eseguire dalla GUI `Host checks` sul CachyOS reale e conservare il manifest sanitizzato.
- Eseguire dalla GUI `Sandbox gate` e verificare tutti i check del namespace sulla macchina target.
- Inventario reale: Pi package/versione, Node, build llama.cpp, model ID, quantizzazione, template, tool/reasoning, context window e parametri della baseline.
- Pin della versione Pi/Node effettivamente compatibile.
- Conferma del provider/API/model ID/capabilities contro Ornith reale.
- Tre sessioni Pi–Ornith consecutive, streaming, stop, resume sessione, tool di lettura/modifica file, errore server e riavvio.
- Verifica dei processi shell/tool figli e assenza di processi posseduti orfani dopo shutdown.
- Verifica grafica reale su KDE/Wayland e GPU target.

### Residuo preparabile senza il target

Dopo il merge del gate attivo non restano altri blocchi M0 ad alto valore che possano sostituire in modo affidabile la prova sulla macchina target. Ulteriore simulazione aumenterebbe soprattutto duplicazione del test harness; il prossimo passo corretto è raccogliere evidenza reale e usare gli eventuali failure per guidare gli ultimi fix M0.

M0 resta quindi **in corso** fino al gate CachyOS + Pi → Ornith LAN.
