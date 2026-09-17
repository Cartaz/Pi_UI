# Audit remediation — 17 settembre 2026

**Stato: PR correttiva in bozza; il gate sul desktop target non è stato eseguito. M1 non è chiusa.** Il precedente gate M0 (9–10 settembre) riguardava un workspace scrivibile e non è una prova della nuova policy.

## Ownership verificata

- `core/sandbox.py` definisce un'unica policy di mount per Pi e per il gate attivo; `core/agent/runtime.py` costruisce la specifica di avvio RPC. `core/agent/bootstrap.py` prepara directory, config modelli e credenziali prima dell'avvio.
- Qt QProcess in `ui/native` possiede i processi. Pi possiede sessioni/config in `.pi-agent`; `AgentController` possiede la proiezione di chat, workspace e connessione. Browser e preview hanno controller separati e non scrivono documenti.
- Gli adapter sono il confine verso QML. `WorkspaceTreeListModel` è per ora una lista piatta lazy con `depth`, scelta documentata in [ARCHITECTURE.md](ARCHITECTURE.md).

## Correzioni introdotte sulla PR

1. **Sandbox obbligatoria:** il launcher Python rifiuta `sandbox_enabled=False`. Sono stati eliminati la costruzione di ambiente host e il percorso di esecuzione diretta. In assenza di Bubblewrap l'avvio fallisce, senza fallback.
2. **Blocco temporaneo delle scritture ai documenti:** `/workspace` viene montato read-only; il solo bind in scrittura è `/workspace/.pi-agent` per la configurazione e le sessioni. Controlli statici e preparazione del runtime rifiutano state directory sostituite con symlink o file. La rete rimane condivisa (`--share-net`): nessun filtro delle destinazioni.
3. **Gate modificato:** il precedente test `workspace-write` è stato sostituito da `workspace-readonly` (tentativo di creare un file fuori da `.pi-agent`) e `state-write` (round-trip in `.pi-agent`). La fixture del controller è stata sincronizzata dopo un errore CI che aveva lasciato i vecchi ID.
4. **Presentazione e accessibilità:** il pannello Knowledge esplicita la disabilitazione delle modifiche agente, le righe selezionate usano testo arancione, e i testi informativi dei pannelli Knowledge/Document usano `textSecondary` anziché il token decorativo `textMuted`. Il desktop reale deve ancora confermare focus, contrasto e resa.
5. **Documentazione:** AGENTS, README, ADR-020 e ARCHITECTURE distinguono componenti implementati, funzionalità previste e prove M0 storiche.

## Test osservati

- La run CI [#149](https://github.com/Cartaz/Pi_UI/actions/runs/35148342124) è **fallita** su Python 3.12/3.13/3.14: la fixture del gate controller conteneva ancora `workspace-write`, mentre il parser richiedeva `workspace-readonly` e `state-write`.
- Commit correttivo [`308a744`](https://github.com/Cartaz/Pi_UI/commit/308a7440596195fcc9b584bd9b897e8ac7b6c5e5): fixture sincronizzata. La run CI [#150](https://github.com/Cartaz/Pi_UI/actions/runs/35189982630) ha completato **con successo tutti e tre i job**; ciascuno ha eseguito compileall, qmllint a zero warning e pytest inclusi smoke QML offscreen. I cambi puramente documentali successivi non sono un gate di sicurezza aggiuntivo.
- Queste prove verificano il codice e il comportamento sintetico, **non** che il mount read-only funzioni su CachyOS/Wayland o che Pi e Ornith continuino a funzionare con esso.

## Modifiche intenzionali e limiti

- Pi non può più modificare documenti via tool finché un servizio di revisioni *prima* della scrittura, conflitti, ripristino e crash recovery non protegge ogni percorso di mutazione. Il test storico M0 di scrittura del file non deve più risultare positivo. Preview read-only e chat devono invece continuare a funzionare.
- Pi può tuttora modificare `.pi-agent`, comprese configurazione e sessioni. La policy documentale non garantisce revisioni né backup per quella directory.
- Il gate attivo include ora un tentativo di scrittura del documento oltre al round-trip dello stato; la prova effettiva sul target non è ancora stata registrata. Il test di sola creazione non sostituisce la prova di sovrascrittura di un file esistente o quella attraverso i tool reali di Pi.
- La verifica del risultato del probe va resa più stretta: errori diversi da `EROFS` non dovrebbero attestare da soli un mount read-only. Anche i controlli anti-symlink eseguiti prima del lancio hanno una finestra temporale da valutare nel modello di minaccia. Non proclamare una protezione universale prima dell'accettazione reale.

## Gate reale obbligatorio prima del merge

Usare **solo un workspace usa-e-getta con file sintetici**, mai l'archivio personale. Annotare commit, distribuzione/kernel, versioni Qt/PySide6/Pi/Bubblewrap, scenari, risultato e limiti.

1. Preparare un documento sentinella nella radice, conservarne hash e contenuto fuori dal workspace e verificare la configurazione della sandbox.
2. Eseguire il preflight e il gate Bubblewrap dalla GUI: `workspace-readonly` e `state-write` devono entrambi passare; niente fallback unsandboxed. Verificare che l'errore osservato per un tentativo di scrittura nel workspace sia effettivamente un filesystem read-only, non EEXIST o una semplice autorizzazione del file.
3. Avviare Pi e provare via tool sia la creazione di un file nella radice sia la sovrascrittura della sentinella. Entrambe devono fallire senza alterare byte, hash o directory entries; provare anche i percorsi di scrittura alternativi realmente disponibili a Pi.
4. Verificare streaming di Ornith, stop, reconnect della **stessa** sessione e stato persistito in `.pi-agent/sessions`. Chiudere l'app mentre Pi è attivo; nessun processo posseduto deve rimanere orfano.
5. Verificare il blocco di sentinel esterna e symlink escape; tentare symlink al posto di `.pi-agent` e `sessions` prima del bootstrap e confermare failure chiara.
6. Rieseguire l'[issue #27](https://github.com/Cartaz/Pi_UI/issues/27) su Wayland: UTF-8, reload, CRLF/Unicode in copia, stati binario/errore, drawer, layout minimo, scrolling e focus.
7. Controllare avviso di sola lettura, contrasti, selezione e resa delle ombre su GPU reale. PSS di GUI, Pi e worker da `/proc/<pid>/smaps_rollup` solo se si formulano claim prestazionali.

**Nessun test target di questa PR è stato effettuato tramite questa sessione.** Registrare gli esiti qui soltanto dopo esecuzione.

## Debito rimasto prima dello sviluppo di nuove funzionalità

- Rafforzare la verifica del tipo di errore del gate, eliminare l'ambiguità sui falsi pass e confermare il comportamento reale del namespace.
- Ridurre il debito `AgentController` con estrazioni incrementali e test di parità; correggere testo informativo a basso contrasto ancora presente in `Main.qml` e verificarne focus/tastiera sul target.
- Allineare le attività già implementate nella ROADMAP senza dichiarare M1 finita; completare installer idempotente e misure PSS quando entrano nei gate previsti, senza creare placeholder.
- Per riabilitare le scritture dei documenti, progettare un percorso mediato con snapshot preventivo e verificare *tutti* i tool: un watcher post-scrittura è insufficiente.

**Non integrare la PR in `main` finché i controlli di sicurezza, la CI della head finale e il gate reale non sono verificati.**
