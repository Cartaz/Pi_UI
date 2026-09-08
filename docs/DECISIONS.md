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
| ADR-011 | Nessuna sandbox dichiarata implicitamente | Working directory e file picker non limitano shell e processi figli; enforcement di sistema da progettare se richiesto | Adottata |
| ADR-012 | Inizializzazione documentale prima del codice | L'azione richiesta è fondare la repo e pianificare; nessun launcher fittizio, test vuoto o dipendenza non verificata | Completata in questo bootstrap |

## Questioni aperte da risolvere quando diventano necessarie

- M0: versione esatta Pi usata nel benchmark; versione Node compatibile; endpoint/provider/model ID, configurazione contesto/tool/reasoning e gestione credenziali locale.
- M0: meccanismo supportato dalla versione fissata per isolare directory di configurazione/sessioni e autorizzare le sole risorse Pi dell'app.
- M1: snapshot di scritture da shell e strumenti non mediati, policy symlink e concorrenza tra editor/agente. Blocca la promessa di ripristino universale finché non provato.
- M2: formati e dimensioni del corpus reale; extractor e licenze; canale IPC, limiti e cancellazione degli strumenti di conoscenza.
- M3: quali informazioni possono aggiornarsi direttamente per istruzione dell'utente e quali richiedono una proposta; regole di conservazione della memoria.
- M4: prima connessione e routine realmente utili; esecuzione soltanto con app aperta o servizio locale esplicito.
- M5: licenza del progetto, formati di distribuzione e requisiti di isolamento effettivo.

Queste questioni non bloccano la documentazione. Registrare la scelta e le evidenze nella milestone appropriata prima di costruire il comportamento dipendente.
