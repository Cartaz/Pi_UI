# M0 — Stato di avanzamento

Aggiornamento: 10 settembre 2026.

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
- `QProcessAgentTransport` asincrono con stderr separato, coda diagnostica limitata/sanitizzata e shutdown `terminate()` → `kill()` temporizzato.
- Un exit non-zero include la coda stderr sanitizzata nell'errore; valori secret env, Bearer token, assegnazioni di credenziali e userinfo URL vengono redatti.
- `AppShutdownCoordinator` mantiene vivo l'event loop durante lo shutdown e ha un watchdog finale.
- Uno stop esplicito di un transport il cui QProcess è già terminato porta anche lo stato `FAILED` a `STOPPED`, evitando che l'app aspetti inutilmente il watchdog finale.
- Session ownership schema 6: se Pi_UI non ha ancora un proprio `last_session_id`, avvia Pi senza `--continue`, `--session` o `--session-id`, quindi acquisisce via `get_state` il nuovo `sessionId` autorevole e lo persiste.
- Reconnect/restart successivi passano l'ID posseduto con `--session-id <id>`. Su Pi 0.85.1 questa opzione riapre l'esatta sessione locale se esiste e crea una nuova sessione con lo stesso ID se il backing file è stato cancellato. Pi_UI verifica comunque l'identità restituita da `get_state` prima di caricare `get_messages` e fallisce chiuso se Pi apre un ID diverso.
- Pi_UI non usa più alcun percorso `continue_latest`; l'adozione/importazione futura di sessioni Pi esistenti dovrà essere un'azione utente esplicita.
- Failure modello dopo prompt accettato: `auto_retry_end(success=false)` viene trattato come terminale, conserva `attempt/finalError`, porta il turno in `FAILED` e non permette al successivo `agent_settled` di tornare silenziosamente `Ready`. Gli errori non retryable sono riconosciuti da `agent_end(willRetry=false)` + assistant `stopReason=error`. Stop/cancellazione esplicita non viene classificata come model failure.
- Un nuovo `AgentClient` pubblica il proprio stato iniziale `IDLE`, quindi Disconnect → Connect è un confine di riconciliazione esplicito e non può ereditare `FAILED` dal client precedente.
- Il failed user turn viene marcato `failed`; al reload lo stato viene ricostruito dall'esito assistant terminale, senza confondere errori di retry intermedi con un failure finale.
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

Macchina target verificata il 9–10 settembre 2026:

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
19. server llama.cpp intenzionalmente spento: GUI resta reattiva e Pi esegue 3 retry, senza replay automatico del prompt. La prima build tornava erroneamente `Ready`; il fix successivo rende visibile il failure terminale, mantiene il composer bloccato e impedisce ad `agent_settled` di cancellare il failure: PASS sul retest target per questi aspetti;
20. dopo riaccensione server + Disconnect → Connect, la build successiva mostrava `Ready` ma `Send` restava disabilitato perché il controller conservava `TurnState.FAILED` dal client precedente: bug target riprodotto e corretto in PR #19;
21. prima del retest di PR #19, l'utente ha cancellato manualmente le vecchie sessioni Pi. Pi_UI conservava `last_session_id` e il successivo `--session <id>` ha fatto terminare Pi 0.85.1 con exit code 1. La nuova diagnostica stderr ha reso visibile `No session found matching ...`; chiudendo l'app già fallita è inoltre scattato il watchdog `Pi shutdown did not settle within 7000 ms`. Entrambi i casi sono coperti dalla PR #21 e richiedono retest target.

## Evidenze CI osservate

GitHub Actions esegue su Python **3.12, 3.13 e 3.14**:

1. installazione PySide6 6.11.x e dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

PR #13 session-resume, PR #14 folder-picker, PR #16 session ownership, PR #18 terminal failure, PR #19 reconnect recovery e PR #20 stderr diagnostics hanno osservato la matrice verde sulle rispettive head finali. La PR #21 aggiunge il contratto `--session-id` e una regressione QProcess per lo stop esplicito dopo un exit già avvenuto.

## Contratti upstream Pi usati

La documentazione/codice upstream della release **0.85.1** confermano:

- `pi --mode rpc` via stdin/stdout JSONL;
- `get_state` espone `sessionId` e `sessionFile`;
- senza `--continue`/`--session`/`--session-id`, Pi crea una nuova sessione;
- `--continue` continua la sessione più recente o ne crea una se non esiste;
- `--session <path|id>` apre una sessione specifica e termina con errore se non viene trovata;
- `--session-id <id>` apre la sessione locale con quell'ID se esiste, altrimenti crea una nuova sessione con lo stesso ID;
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

### Richiede retest target dopo PR #21

- Pull della build con recovery `--session-id` e shutdown del transport già fallito.
- Con il `last_session_id` attuale ma backing session file assente, Connect deve crearere una sessione nuova con lo stesso ID e arrivare a `Ready` senza exit code 1.
- Chiudere Pi_UI dopo un eventuale failure e verificare che non ricompaia il watchdog di 7000 ms.
- Spegnere llama.cpp durante un prompt e verificare end-to-end: retry visibili, errore finale visibile, prompt `failed`, composer bloccato, nessun ritorno silenzioso a Ready, nessun replay automatico.
- Riaccendere server, Disconnect → Connect sulla stessa sessione e inviare un prompt neutro per verificare che `Send` sia di nuovo abilitato e il runtime risponda normalmente.
- Eseguire almeno tre reconnect/riavvii consecutivi dopo il pin dell'ID.
- Verifica grafica/focus finale su KDE/Wayland.

### UX/funzionalità osservate ma non bloccanti per il runtime M0

- Reasoning stream non ancora proiettato in UI benché Pi RPC esponga `thinking_*`; issue #9.
- Metriche grounded token/timing/tok/s; issue #10.
- Copia esplicita messaggi user/assistant; issue #11.
- Il failed user turn resta nel contesto Pi dopo un model failure; non viene cancellato o riscritto implicitamente. Una futura UX di retry/branch/rollback deve essere esplicita, non una mutazione automatica della cronologia.

Folder picker KDE issue #8 e session ownership issue #15 sono state corrette e verificate sul target.

M0 resta **in corso** fino al retest reale di stale-session recovery, terminal retry failure/recovery e giro finale di reconnect/focus.
