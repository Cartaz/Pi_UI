# Decisioni iniziali

Stato delle decisioni distinto dall'implementazione: “adottata” stabilisce la direzione, non significa codice pronto. Riferimento requisiti: conversazione di progetto dell'8 settembre 2026 e contratto Cartaz QML fornito dall'utente.

| ID | Decisione | Motivazione e alternative | Stato |
|---|---|---|---|
| ADR-001 | Un workspace persistente, molte chat, una sessione attiva | Rispecchia l'AI OS personale; multiprogetto e concorrenza multiagente aumentano complessità senza requisito attuale | Adottata |
| ADR-002 | Python/PySide6/QML, Pi locale via RPC | Rispetta il contratto nativo e conserva Pi; SDK Node diretto avrebbe senso in un host Node, non nella UI Python scelta | Adottata |
| ADR-003 | Ornith 1.5 via LAN, configurazione della baseline | Scelta dell'utente dopo AIOS-bench; model ID, template, contesto e versioni effettivi non verificati qui | Adottata, dettagli M0 |
| ADR-004 | Sessioni canoniche di Pi; conoscenza in file aperti | Evita doppia cronologia e memoria legata alla chat infinita; cataloghi e indici sono derivati | Adottata |
| ADR-005 | Chat e file insieme in M1 | Il file manager è seconda priorità del prodotto, non una funzione tardiva; ricerca/estrazione evolvono in M2 | Adottata |
| ADR-006 | Noto Sans e token Cartaz correnti | News Aggregator usa Cantarell con fallback Noto Sans; prevale il contratto esplicito attuale che prescrive Noto Sans | Adottata; differenza documentata |
| ADR-007 | Ricerca testuale prima, FTS5 candidato | Semplice da verificare e ricostruire; embedding locali solo dopo un confronto sul corpus che dimostri vantaggi | Proposta da verificare M2 |
| ADR-008 | Estensione Pi sottile verso servizi Python | Rende la conoscenza accessibile al modello senza duplicarne l'implementazione in TypeScript; IPC da provare | Proposta da verificare M2 |
| ADR-009 | Snapshot/hash per revisioni, niente Git obbligatorio nei dati | Revisioni comprensibili per documenti anche binari; richiede garanzie sui percorsi di scrittura agente | Proposta da verificare M1 |
| ADR-010 | CI deterministica ospitata; LLM reale solo LAN | Rispetta la preferenza locale e separa verifica del software da qualità/compatibilità del modello | Adottata |
| ADR-011 | Nessuna sandbox dichiarata implicitamente | Working directory e file picker non limitano shell e processi figli; l'isolamento va ottenuto con enforcement di sistema e prove reali | Adottata |
| ADR-012 | Inizializzazione documentale prima del codice | L'azione richiesta era fondare la repo e pianificare; nessun launcher fittizio, test vuoto o dipendenza non verificata nel bootstrap | Completata nel bootstrap |
| ADR-013 | Pi_UI usa una directory Pi e una directory sessioni isolate | `PI_CODING_AGENT_DIR` e `PI_CODING_AGENT_SESSION_DIR` sono supportati upstream; evita di sovrascrivere configurazione e sessioni dell'installazione globale dell'utente | Adottata; launch spec implementata M0 |
| ADR-014 | Aggiornamenti Pi espliciti e controllati dalla GUI, non automatici all'avvio | Pi espone update e package management, ma un cambio upstream può rompere RPC/trust/config; l'app disabilita il version check normale e introdurrà update con verifica compatibilità e rollback | Adottata; update manager da implementare |
| ADR-015 | Personalizzazione Pi esposta dalla GUI tramite capacità upstream, senza forkare Pi | Estensioni, skill, prompt template e package sono già primitive native di Pi; la GUI deve gestirne stato/origine/versione e lasciare Python proprietario delle policy dell'app | Adottata; UI/runtime manager da implementare |
| ADR-016 | Su Linux Pi e tutti i suoi processi figli vengono eseguiti dentro una sandbox Bubblewrap; la GUI resta fuori | Bubblewrap costruisce un mount namespace vuoto e rende visibili solo i mount dichiarati. L'AIOS root è l'unico albero dati personale montato read-write; runtime/config/sessioni Pi vivono sotto una sottocartella nascosta della stessa radice. Directory di sistema necessarie sono read-only, HOME reale/XDG runtime/DBus/SSH agent non vengono esposti. La rete host resta inizialmente condivisa per raggiungere Ornith sulla LAN; limitare l'egress al solo endpoint richiederà una policy di rete separata | Adottata; da implementare e verificare in M0 |

## Questioni aperte da risolvere quando diventano necessarie

- M0: versione esatta Pi usata nel benchmark; versione Node compatibile; endpoint/provider/model ID, configurazione contesto/tool/reasoning e gestione credenziali locale.
- M0: meccanismo supportato dalla versione fissata per isolare directory di configurazione/sessioni e autorizzare le sole risorse Pi dell'app. Il launch spec usa le variabili documentate upstream, ma trust e risorse vanno ancora provati con la versione fissata.
- M0: formato finale della configurazione derivata `models.json`, inclusa autenticazione/no-auth del server llama.cpp e compatibilità OpenAI/Anthropic realmente usata dalla baseline.
- M0: profilo Bubblewrap minimo realmente necessario a Node/Pi su CachyOS: mount read-only di `/usr` e certificati, `/proc`, `/dev`, tmpfs, ambiente ripulito, AIOS root read-write, lifecycle e comportamento dei processi figli. Verificare symlink, shell, estensioni e assenza di accesso al vero `$HOME`.
- M0: la rete della sandbox deve raggiungere il server Ornith. `--share-net` conserva la rete host e quindi non limita le destinazioni; valutare separatamente un meccanismo per permettere soltanto l'endpoint LAN se il requisito diventa anche di isolamento di rete.
- M0/M1: UX e meccanismo dell'update manager: rilevamento versione, staging, test di compatibilità, attivazione e rollback senza toccare automaticamente l'installazione globale.
- M1: snapshot di scritture da shell e strumenti non mediati, policy symlink e concorrenza tra editor/agente. Blocca la promessa di ripristino universale finché non provato.
- M2: formati e dimensioni del corpus reale; extractor e licenze; canale IPC, limiti e cancellazione degli strumenti di conoscenza.
- M3: quali informazioni possono aggiornarsi direttamente per istruzione dell'utente e quali richiedono una proposta; regole di conservazione della memoria.
- M4: prima connessione e routine realmente utili; esecuzione soltanto con app aperta o servizio locale esplicito.
- M5: licenza del progetto, formati di distribuzione e requisiti di isolamento effettivo.

Queste questioni non bloccano la tranche core M0. Registrare la scelta e le evidenze nella milestone appropriata prima di costruire il comportamento dipendente.
