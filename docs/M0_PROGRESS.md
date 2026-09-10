# M0 — Report di chiusura

Aggiornamento: 10 settembre 2026.

Stato: **COMPLETATA**. Il gate applicativo M0 è stato superato sul desktop CachyOS target e la head integrata mantiene la matrice CI verde. M1 può iniziare.

Questo documento distingue deliberatamente prove CI sintetiche, prove reali sul target e dettagli non ancora inventariati. Nessuna prova offscreen viene usata come sostituto di una verifica LAN, Bubblewrap o KDE/Wayland reale.

## Risultato consegnato

M0 ha prodotto una prima shell Qt Quick realmente collegata a Pi Agent e Ornith LAN, con runtime Pi dedicato, sandbox Bubblewrap, trasporto RPC asincrono, ownership deterministica della sessione, streaming, stop, tool file, fault recovery e lifecycle applicativo verificati.

Contratti principali:

- Python/PySide6 possiedono stato, lifecycle, settings, sandbox e coordinamento; QML resta presentazione.
- Pi viene eseguito tramite `QProcess` in modalità RPC, senza shell intermedia e senza fallback unsandboxed.
- `/home/francesco/AI_OS` è montata come `/workspace`, unico albero personale read-write previsto; `/usr` e `/opt/pi-agent` sono read-only.
- La rete host resta condivisa per Ornith LAN e Internet. Questo **non** costituisce egress filtering.
- Pi_UI non adotta automaticamente sessioni di altri client Pi. Il primo Connect crea una sessione propria; reconnect/restart usano l'ID posseduto tramite `--session-id`.
- Un model failure terminale resta fallito; non torna silenziosamente `Ready` e non viene rieseguito implicitamente nel turno successivo. Il reconnect usa le primitive tree/fork pubbliche di Pi per riprendere prima del failed turn.
- Prompt con outcome incerto non vengono reinviati automaticamente.

## Baseline target osservata

Macchina verificata il 9–10 settembre 2026:

- CachyOS/Linux, sessione KDE Wayland (`XDG_SESSION_TYPE=wayland`, `WAYLAND_DISPLAY=wayland-0`).
- Python `3.14.7`.
- PySide6/Qt `6.11.2`.
- Node `26.8.1` in `/usr/bin/node`.
- Bubblewrap `0.12.0` in `/usr/bin/bwrap`.
- Pi Agent `0.85.1` in `/opt/pi-agent/bin/pi`.
- Workspace host `/home/francesco/AI_OS`.
- Provider Pi `aios-llamacpp`, API `openai-completions`.
- Model ID `Ornith`.
- Endpoint LAN osservato durante il gate: `http://192.168.43.104:8080/v1`.
- `/v1/models` ha esposto `n_ctx=98304` e quantizzazione descritta dal server come `Q4_K - Medium`.

L'esatto commit/build di llama.cpp, chat template e insieme completo dei flag di generazione/server non sono stati catturati integralmente. Sono **dettagli di riproducibilità server non necessari al gate applicativo M0** e non vengono dichiarati noti. Andranno inventariati quando Pi_UI assumerà responsabilità di configurazione/gestione del server o quando servirà una baseline prestazionale riproducibile.

## Evidenze target finali

1. Installazione editable nella venv su Python 3.14.7: PASS.
2. `compileall`: PASS.
3. `qmllint --max-warnings 0`: PASS.
4. Suite pytest locale iniziale: **134 passed** sulla build M0 precedente ai successivi fix sessione/failure; le head finali successive sono state validate dalla CI ospitata.
5. Host preflight GUI: **Blocking 0**, **Warnings 1**, **Pending target gate 1**; il warning è la rete condivisa prevista.
6. Bubblewrap gate reale: **Passed 11, Failed 0**.
7. Working directory sandbox `/workspace`: PASS.
8. Workspace AIOS read-write: PASS.
9. Sentinel esterno non leggibile e symlink escape bloccato: PASS.
10. Child process confinato; runtime e `/usr` read-only; HOME/session environment isolati: PASS.
11. Pi → Ornith LAN: PASS.
12. Streaming della risposta finale progressivo: PASS.
13. Stop durante generazione e successivo nuovo prompt: PASS.
14. Tool file reale: lettura e modifica `m0_file_test.txt` da `VALORE_INIZIALE=41` a `VALORE_FINALE=42`: PASS.
15. `/home/francesco` non accessibile all'agente: PASS.
16. Internet raggiungibile dal sandbox: PASS.
17. Disconnect termina i processi Bubblewrap/Pi posseduti da Pi_UI senza terminare una sessione `pi-aios` indipendente: PASS.
18. Primo Connect con un altro Pi concorrente crea una sessione Pi_UI propria: PASS.
19. Disconnect → Connect conserva la cronologia della sessione esatta: PASS.
20. Chiusura della finestra mentre Pi è connesso: nessun processo Pi_UI orfano; riapertura + Connect conserva la sessione: PASS.
21. Cancellazione manuale del backing file di sessione: `--session-id` recupera deterministicamente senza agganciarsi ad altre sessioni: PASS.
22. Shutdown dopo processo già terminato: nessun watchdog spurio da 7000 ms: PASS.
23. Server llama.cpp spento durante un prompt: GUI reattiva, 3 retry Pi, failure terminale visibile, prompt marcato `failed`, composer bloccato, nessun ritorno silenzioso a `Ready`: PASS.
24. Riaccensione server senza azione utente: nessun replay automatico: PASS.
25. Disconnect → Connect dopo failure: branch recovery tramite RPC tree/fork prima del failed user turn; il prompt fallito non entra nel successivo contesto attivo: PASS.
26. Primo prompt dopo recovery risponde solo alla nuova richiesta, senza deferred retry del failed turn: PASS.
27. Tre reconnect consecutivi sulla stessa sessione, con cronologia conservata e `Send` abilitato: PASS; marcatore `THREE_RECONNECTS_OK` ricevuto.
28. Folder picker KDE: entrando in `AI_OS` e usando `Use this folder`, viene selezionata esattamente `/home/francesco/AI_OS`: PASS.
29. Focus composer, `Shift+Enter` newline, `Enter` send e round-trip `Alt+Tab` su KDE/Wayland: PASS.
30. Layout alla `minimumWidth=860`: header responsive 2×2, `Connect/Disconnect` e le altre azioni restano dentro il pannello senza sovrapposizioni: PASS reale e regressione QML offscreen.

## Evidenze CI finali

GitHub Actions esegue su Python **3.12, 3.13 e 3.14**:

1. installazione PySide6 6.11.x e dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

La PR #23, ultima modifica applicativa di M0, ha osservato la matrice completa verde sulla propria head finale. Le regressioni introdotte durante M0 coprono tra l'altro parser JSONL, request correlation, deadline, QProcess lifecycle, sandbox planning/gate, session ownership, stale session, retry failure, reconnect recovery, no deferred replay e geometria QML alla larghezza minima.

## Difetti trovati sul target e chiusi durante M0

Le prove reali hanno trovato e portato alla correzione di problemi che la sola CI non avrebbe dimostrato: folder picker KDE ambiguo; reconnect che creava una sessione vuota; bootstrap `--continue` che poteva adottare la sessione di un altro Pi; failure dopo retry nascosto da `Ready`; `Send` bloccato dopo recovery; puntatore stale dopo cancellazione manuale del file sessione; watchdog shutdown spurio; failed turn ancora presente nel contesto successivo; overflow del pulsante Connect alla dimensione minima.

Il percorso di recovery finale conserva la lineage delle sessioni tramite primitive pubbliche Pi e non riscrive i JSONL a mano.

## Funzionalità osservate ma rinviate a M1+

Non bloccano M0 e hanno issue dedicate:

- reasoning stream nella UI: Pi RPC espone già `thinking_*`; issue #9;
- metriche grounded token/timing/tok/s: issue #10;
- copia esplicita dei messaggi user/assistant: issue #11;
- UX esplicita per navigazione delle conversazioni, branch e `Retry` manuale dei turn falliti: da integrare nel lavoro M1 sulle conversazioni.

## Revisione strategica M0

Ownership confermata:

- Pi è canonico per session tree e messaggi di sessione;
- Pi_UI possiede selezione della sessione, lifecycle del processo e policy di recovery;
- settings Python possiedono il puntatore `last_session_id`;
- Bubblewrap policy è costruita da un unico modulo condiviso tra launch e gate;
- QML non possiede stato operativo persistente.

Debito da non trascinare in M1:

- `AgentController` è cresciuto durante i fix M0. Prima di aggiungere gestione file o molte conversazioni, estrarre responsabilità coese dove riduce realmente il coupling, in particolare proiezione transcript/session recovery/profile selection. **Non aggiungere file management ad `AgentController`.**
- La rete condivisa è una scelta esplicita per LAN/Internet, non una sandbox di egress.
- Le sessioni Pi CLI esistenti non vengono adottate automaticamente; un futuro import/selettore deve essere un'azione utente esplicita.

## Chiusura

Il gate M0 definito dalla roadmap è soddisfatto: integrazione Pi–Ornith reale, streaming/tool/stop, session persistence, fault recovery, confinement osservato, shutdown senza orphan, tre reconnect consecutivi e comportamento KDE/Wayland verificati.

**M0 è chiusa. Il prossimo lavoro applicativo è M1: chat e file nella prima GUI utilizzabile.**
