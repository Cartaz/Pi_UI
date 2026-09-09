# M0 — Stato di avanzamento

Aggiornamento: 9 settembre 2026.

Questo documento registra evidenze incrementali della milestone M0 distinguendo CI sintetica e prove osservate sulla macchina CachyOS target.

## Implementato e verificato in CI

### Fondazione core e configurazione

- `core/settings.py`: settings tipizzati, percorsi XDG, validazione, migrazioni di schema, scrittura atomica e recovery da JSON malformato/non compatibile.
- Settings schema 6: timeout distinti e puntatore persistito all'esatta sessione Pi attiva (`last_session_id`). La migrazione da schema 5 invalida il puntatore perché le build schema-5 potevano acquisirlo tramite una selezione `--continue` ambigua.
- Configurazione provider/modello Pi derivabile dallo stato canonico Pi_UI, con credenziali soltanto tramite riferimenti a variabili d'ambiente.
- Discovery read-only di `AIOS_ROOT/.pi-agent/models.json`, fingerprint SHA-256 e verifica immediatamente prima del launch; nessuna adozione/sovrascrittura implicita.
- Un `models.json` presente ma corrotto/non interpretabile non fa fallire l'avvio della GUI: produce zero profili e blocca Connect.

### Bubblewrap launch specification

- AIOS root host montata come `/workspace`, unico albero personale read-write previsto.
- Runtime Pi dedicato e `/usr` read-only; home/tmp sintetici, configurazione/sessioni Pi in `/workspace/.pi-agent`.
- HOME sintetica canonica `/home/aios`; `USER`/`LOGNAME=aios`, `TMPDIR=/tmp`, `PI_TELEMETRY=0`.
- `runtime_root` troppo ampi o sovrapposti al workspace writable vengono rifiutati.
- Rete host condivisa per LAN e Internet; `--share-net` **non** limita le destinazioni di rete.
- Ambiente child allow-list; `DISPLAY`, `WAYLAND_DISPLAY`, D-Bus, `SSH_AUTH_SOCK`, `GPG_AGENT_INFO` e `XDG_RUNTIME_DIR` non vengono copiati implicitamente.
- Alias FHS ricreati verso `/usr` quando necessari.
- Nessun fallback automatico sandbox → host.
- La policy mount è costruita da un unico modulo (`core/sandbox.py`) riusato dal launch Pi e dal gate attivo.

### RPC, stato, sessione e lifecycle

- JSONL LF stretto, correlazione request ID, prompt/steer/follow-up, `get_state`, `get_messages`, stato turno e stop `clear_queue → abort`.
- ACK prompt distinto dal completamento; `agent_settled` riporta il turno a idle soltanto quando il turno non è già in failure terminale.
- Deadline RPC senza retry automatico; prompt ACK timeout → outcome `uncertain` e blocco nuovi invii fino a riconciliazione.
- Watchdog inattività non distruttivo.
- `QProcessAgentTransport` asincrono con stderr separato e shutdown `terminate()` → `kill()` temporizzato.
- `AppShutdownCoordinator` mantiene vivo l'event loop durante lo shutdown e ha un watchdog finale.
- Session ownership schema 6: se Pi_UI non ha ancora un proprio `last_session_id`, avvia Pi senza `--continue` e senza `--session`, quindi acquisisce via `get_state` il nuovo `sessionId` autorevole e lo persiste. Reconnect/restart successivi usano `--session <id>` esplicito. Pi_UI verifica l'identità della sessione prima di caricare `get_messages` e fallisce chiuso se Pi apre una sessione diversa.
- Il supporto low-level a `continue_latest` resta una capacità esplicita del runtime Pi, ma non è usato automaticamente dal controller. Un'eventuale futura adozione/importazione di sessioni esistenti dovrà essere un'azione utente esplicita.
- Failure modello dopo prompt accettato: `auto_retry_end(success=false)` viene trattato come terminale, conserva `attempt/finalError`, porta il turno in `FAILED` e non permette al successivo `agent_settled` di tornare silenziosamente `Ready`. Gli errori non retryable sono riconosciuti da `agent_end(willRetry=false)` + assistant `stopReason=error`. Stop/cancellazione esplicita non viene classificata come model failure.
- Nessun replay automatico dopo failure terminale: recovery esplicita tramite Disconnect/Reconnect della stessa sessione.

### Prima shell Qt Quick

- `QApplication` + `QQmlApplicationEngine`; `main.py` solo wiring/lifecycle.
- Controller Python presentation-independent, adapter focalizzati e `QAbstractListModel` per profili/transcript.
- QML dark-neumorphic centralizzato.
- Workspace/profile selection, connect/disconnect, cronologia RPC, transcript virtualizzato, composer, send e stop reali.
- Folder picker KDE: l'accept usa la cartella attualmente visualizzata (`currentFolder`) con azione esplicita `Use this folder`, evitando la selezione incidentale del primo figlio.

### Preflight e gate attivo

- Host preflight read-only per OS, workspace, policy sandbox, Bubblewrap, Pi, runtime root, Node e `models.json`.
- Probe versioni tramite `QProcess` senza shell, ambiente ridotto e timeout.
- Node deve essere visibile in un albero realmente montato nel sandbox.
- Controller/adapter/model diagnostici separati da `AgentController`.
- Cancellazione protetta contro callback tardivi e manifest sanitizzati.
- Gate attivo Bubblewrap usa **lo stesso builder** del runtime Pi e un payload Node controllato, senza contattare Ornith.
- Il gate verifica working directory, workspace RW, sentinel esterno, symlink escape, child-process inheritance, runtime e `/usr` RO, HOME sintetica, variabili/socket desktop e PID namespace.
- Parser fail-closed e cleanup fixture su successo/errore/cancellazione.

## Evidenze reali osservate — CachyOS target

Macchina target verificata il 9 settembre 2026:

- CachyOS/Linux; Python `3.14.7`; PySide6/Qt `6.11.2`.
- Node `26.8.1` in `/usr/bin/node`.
- Bubblewrap `0.12.0` in `/usr/bin/bwrap`.
- Pi Agent `0.85.1` in `/opt/pi-agent/bin/pi`.
- Workspace `/home/francesco/AI_OS`.
- Provider esistente `aios-llamacpp`, API `openai-completions`, model ID `Ornith`, endpoint LAN `http://192.168.43.104:8080/v1`.
- llama.cpp `/v1/models` ha esposto Ornith con `n_ctx=98304`.

Prove osservate:

1. installazione editable su Python 3.14.7: riuscita;
2. `compileall`: PASS;
3. `qmllint --max-warnings 0`: PASS;
4. pytest locale: **134 passed** sulla build M0 precedente ai fix sessione/failure;
5. Host checks GUI: **Blocking 0, Warnings 1, Pending target gate 1**; unico warning previsto `--share-net`;
6. Sandbox gate GUI reale: **Passed 11, Failed 0**;
7. Pi → Ornith LAN: PASS;
8. streaming risposta finale progressivo: PASS;
9. Stop durante generazione + nuovo prompt `STOP_OK`: PASS;
10. tool file: lettura e modifica reale `m0_file_test.txt` da `VALORE_INIZIALE=41` a `VALORE_FINALE=42`: PASS;
11. `/home/francesco` non accessibile all'agente: PASS;
12. Internet raggiungibile dal sandbox: PASS;
13. Disconnect: i processi Bubblewrap/Pi_UI sono terminati; i soli processi rimasti appartenevano a una sessione `pi-aios` indipendente già esistente: PASS;
14. reconnect processo/modello sulla prima build: PASS (`RECONNECT_OK`), ma la cronologia è sparita perché veniva creata una nuova sessione: bug riprodotto;
15. folder picker KDE dopo il fix #14: entrando in `AI_OS` e confermando la cartella, Pi_UI seleziona correttamente `/home/francesco/AI_OS`: PASS;
16. primo Connect della build schema-5 session-resume con un altro `pi-aios` concorrente: Pi `--continue` ha adottato la sessione attiva/più recente dell'altro agente invece di crearne una Pi_UI. Nessun nuovo messaggio è stato inviato; l'utente ha disconnesso. Bug riprodotto, poi corretto con schema 6;
17. schema 6 sul target, mantenendo un altro `pi-aios` attivo: primo Connect Pi_UI apre una sessione nuova e propria, `PI_UI_OWN_SESSION_OK` passa, Disconnect → Connect conserva la cronologia: PASS;
18. chiusura completa della GUI con Pi connesso: processo Pi_UI presente prima della chiusura, nessun orphan dopo, riapertura app + Connect conserva la stessa cronologia: PASS;
19. server llama.cpp intenzionalmente spento: GUI resta reattiva e Pi esegue 3 retry, senza replay automatico del prompt; **FAILURE UX riprodotto** sulla build precedente perché dopo il retry terminale Pi_UI non mostrava `finalError` e tornava `Ready`. Issue #17 / PR #18 correggono il lifecycle;
20. dopo riaccensione server + reconnect, il modello ha risposto ma non ha rispettato il marker `SERVER_RECOVERED`: il failed user turn era correttamente ancora nella sessione e il modello ha interpretato le due richieste come prompt injection. Questo non dimostra replay; il recovery funzionale va ritestato dopo il fix #17 con un prompt neutro e verificando separatamente l'assenza di replay.

## Evidenze CI osservate

GitHub Actions esegue su Python **3.12, 3.13 e 3.14**:

1. installazione PySide6 6.11.x e dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

PR #13 session-resume, PR #14 folder-picker e PR #16 session ownership hanno osservato questi step verdi su tutte e tre le versioni. La suite copre pin `--session <id>`, persistenza/restart, mismatch sessione fail-closed, QML e sandbox/lifecycle. La PR #18 aggiunge failure terminale da retry/non-retryable, latch attraverso `agent_settled`, cancellazione esplicita e proiezione controller non-sendable senza replay.

## Contratti upstream Pi usati

La documentazione/codice upstream corrente confermano:

- `pi --mode rpc` via stdin/stdout JSONL;
- `get_state` espone `sessionId` e `sessionFile`;
- senza `--continue`/`--session`, Pi crea una nuova sessione;
- `--continue` continua la sessione più recente o ne crea una se non esiste;
- `--session <path|id>` apre una sessione specifica e fallisce se non viene trovata;
- `--session-dir`, `PI_CODING_AGENT_SESSION_DIR` e `PI_CODING_AGENT_DIR` isolano lo storage;
- ACK prompt distinto dal completamento; i failure successivi all'ACK sono eventi/message stream, non una seconda response dello stesso request ID;
- `auto_retry_start` descrive i retry automatici e `auto_retry_end(success=false)` espone `attempt` e `finalError` al termine dei tentativi;
- `agent_end` espone `willRetry`; `agent_settled` arriva solo quando Pi non continuerà automaticamente dopo retry/compattazione/continuazioni;
- `clear_queue` prima di `abort` per stop interattivo;
- estensioni, skill, prompt template e package sono primitive upstream da esporre senza forkare Pi.

Riferimenti primari:

- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/main.ts
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/session-manager.ts
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md

## Politica aggiornamenti e personalizzazione Pi

1. runtime Pi isolato dall'installazione globale;
2. nessun auto-update implicito: aggiornamenti futuri via azione GUI con compatibility gate/rollback;
3. inferenza canonica nei settings Python;
4. baseline `models.json` utente preservata e usata read-only dopo fingerprint;
5. estensioni/skill/prompt/package futuri gestiti tramite primitive upstream con origine/versione/trust visibili;
6. sistema subagent di prima classe pianificato, con orchestrazione/parallelismo/memoria condivisa da progettare sui casi reali.

## Lavoro M0 ancora aperto

### Richiede retest target dopo PR #18

- Pull della build con failure terminale corretto.
- Spegnere llama.cpp durante un prompt e verificare: retry visibili, errore finale visibile, composer bloccato, nessun ritorno silenzioso a Ready, nessun replay automatico.
- Riaccendere server, Disconnect → Connect sulla stessa sessione e inviare un prompt neutro (non un marker imperativo) per distinguere recovery del runtime da comportamento del modello sul failed-turn context.
- Eseguire almeno tre reconnect/riavvii consecutivi dopo il pin dell'ID.
- Verifica grafica/focus finale su KDE/Wayland.

### UX/funzionalità osservate ma non bloccanti per il runtime M0

- Reasoning stream non ancora proiettato in UI benché Pi RPC esponga `thinking_*`; issue #9.
- Metriche grounded token/timing/tok/s; issue #10.
- Copia esplicita messaggi user/assistant; issue #11.
- Il failed user turn resta nel contesto Pi dopo un model failure; non viene cancellato o riscritto implicitamente. Una futura UX di retry/branch/rollback deve essere esplicita, non una mutazione automatica della cronologia.

Folder picker KDE issue #8 e session ownership issue #15 sono state corrette e verificate sul target.

M0 resta **in corso** fino al retest reale del terminal retry failure, recovery e giro finale di reconnect/focus.
