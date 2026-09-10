# Decisioni architetturali

Stato delle decisioni distinto dall'implementazione: “adottata” stabilisce la direzione; dove indicato, M0 ha anche prodotto verifica reale sul target. Riferimento requisiti iniziali: conversazione di progetto dell'8 settembre 2026 e contratto Cartaz QML fornito dall'utente. Aggiornamento: 10 settembre 2026.

| ID | Decisione | Motivazione e alternative | Stato |
|---|---|---|---|
| ADR-001 | Un workspace persistente, molte chat, una sessione attiva | Rispecchia l'AI OS personale; multiprogetto e concorrenza multiagente aumentano complessità senza requisito attuale | Adottata |
| ADR-002 | Python/PySide6/QML, Pi locale via RPC | Rispetta il contratto nativo e conserva Pi; SDK Node diretto avrebbe senso in un host Node, non nella UI Python scelta | Adottata; base M0 verificata |
| ADR-003 | Ornith 1.5 via LAN, configurazione della baseline applicativa | Scelta dell'utente dopo AIOS-bench. Pi/Node/Python/Qt, provider/API/model ID, endpoint e contesto esposto sono stati verificati; build/template/flag completi del server sono riproducibilità server, non ownership Pi_UI M0 | Adottata; baseline applicativa M0 verificata |
| ADR-004 | Sessioni canoniche di Pi; conoscenza in file aperti | Evita doppia cronologia e memoria legata alla chat infinita; cataloghi e indici sono derivati | Adottata |
| ADR-005 | Chat e file insieme in M1 | Il file manager è seconda priorità del prodotto, non una funzione tardiva; ricerca/estrazione evolvono in M2 | Adottata |
| ADR-006 | Noto Sans e token Cartaz correnti | News Aggregator usa Cantarell con fallback Noto Sans; prevale il contratto esplicito attuale che prescrive Noto Sans | Adottata; differenza documentata |
| ADR-007 | Ricerca testuale prima, FTS5 candidato | Semplice da verificare e ricostruire; embedding locali solo dopo un confronto sul corpus che dimostri vantaggi | Proposta da verificare M2 |
| ADR-008 | Estensione Pi sottile verso servizi Python | Rende la conoscenza accessibile al modello senza duplicarne l'implementazione in TypeScript; IPC da provare | Proposta da verificare M2 |
| ADR-009 | Snapshot/hash per revisioni, niente Git obbligatorio nei dati | Revisioni comprensibili per documenti anche binari; richiede garanzie sui percorsi di scrittura agente | Proposta da verificare M1 |
| ADR-010 | CI deterministica ospitata; LLM reale solo LAN | Rispetta la preferenza locale e separa verifica del software da qualità/compatibilità del modello | Adottata; verificata M0 |
| ADR-011 | Nessuna sandbox dichiarata implicitamente | Working directory e file picker non limitano shell e processi figli; l'isolamento richiede enforcement di sistema e prove reali | Adottata; Bubblewrap verificato M0 |
| ADR-012 | Inizializzazione documentale prima del codice | L'azione richiesta era fondare la repo e pianificare; nessun launcher fittizio, test vuoto o dipendenza non verificata nel bootstrap | Completata nel bootstrap |
| ADR-013 | Pi_UI usa configurazione/sessioni Pi sotto il workspace controllato, separate dall'installazione globale | `PI_CODING_AGENT_DIR` e `PI_CODING_AGENT_SESSION_DIR` sono supportati upstream. Lo storage può essere condiviso con un altro client Pi intenzionalmente configurato sullo stesso workspace, quindi l'isolamento logico della sessione Pi_UI è ottenuto tramite ownership dell'ID, non assumendo esclusività della directory | Adottata; verificata M0 |
| ADR-014 | Aggiornamenti Pi espliciti e controllati dalla GUI, non automatici all'avvio | Un cambio upstream può rompere RPC/trust/config; l'app disabilita il version check normale e introdurrà update con verifica compatibilità e rollback | Adottata; update manager da implementare |
| ADR-015 | Personalizzazione Pi esposta dalla GUI tramite capacità upstream, senza forkare Pi | Estensioni, skill, prompt template e package sono primitive native di Pi; la GUI deve gestirne stato/origine/versione e lasciare Python proprietario delle policy dell'app | Adottata; UI/runtime manager da implementare |
| ADR-016 | Su Linux Pi e tutti i suoi processi figli vengono eseguiti dentro Bubblewrap; la GUI resta fuori | AIOS root unico albero personale RW; runtime e sistema RO; HOME reale/XDG runtime/DBus/SSH/GPG non esposti. `--share-net` resta necessario per LAN/Internet e non limita l'egress | Adottata; gate reale 11/11 verificato M0 |
| ADR-017 | Pi_UI possiede un `sessionId` esatto; niente `--continue` automatico | `--continue` può adottare la sessione più recente di un altro client. Primo Connect crea una nuova sessione; reconnect/restart usano `--session-id <id>` e verificano l'ID restituito da `get_state` | Adottata dopo bug target; verificata M0 |
| ADR-018 | Recovery di un failed turn tramite session tree/fork pubblico Pi, non editing JSONL | Lasciare il failed user turn nel branch attivo produce un retry implicito al prompt successivo. Al reconnect Pi_UI fa fork prima del failed entry, conserva lineage/audit e non reinvia automaticamente | Adottata dopo bug target; verificata M0 |
| ADR-019 | Build/template/flag completi di llama.cpp non bloccano il gate applicativo M0 | Pi_UI M0 non gestisce il server; il gate richiede compatibilità reale, non riproducibilità completa del deployment server. Questi dati diventano necessari per gestione server o benchmark riproducibili | Adottata; carry-over M5.6/server management |

## Questioni aperte da risolvere quando diventano necessarie

M0 non ha più blocker aperti. Le questioni residue appartengono a milestone successive:

- M1: UX e meccanismo dell'update manager: rilevamento versione, staging, test di compatibilità, attivazione e rollback senza toccare automaticamente l'installazione globale.
- M1: snapshot delle scritture da shell e strumenti non mediati, policy symlink e concorrenza tra editor/agente. Blocca la promessa di ripristino universale finché non provato.
- M1: navigazione/import esplicito di sessioni Pi esistenti e UX `Retry`/branch per i turn falliti; nessuna adozione automatica.
- M1/M5: la rete della sandbox usa `--share-net` e quindi non limita le destinazioni; introdurre egress filtering solo se diventa un requisito esplicito, con enforcement separato.
- M2: formati e dimensioni del corpus reale; extractor e licenze; canale IPC, limiti e cancellazione degli strumenti di conoscenza.
- M3: quali informazioni possono aggiornarsi direttamente per istruzione dell'utente e quali richiedono una proposta; regole di conservazione della memoria.
- M4: prima connessione e routine realmente utili; esecuzione soltanto con app aperta o servizio locale esplicito; design del sistema subagents sui casi d'uso reali.
- M5: licenza del progetto, formati di distribuzione, scaling/X11 se dichiarati supportati, backup/restore e baseline prestazionale riproducibile. Quando necessario registrare anche build llama.cpp, chat template e flag server/generazione pertinenti.

Le decisioni e le evidenze di chiusura M0 sono riportate in [M0_PROGRESS.md](M0_PROGRESS.md). Registrare nuove scelte nella milestone appropriata prima di costruire il comportamento dipendente.
