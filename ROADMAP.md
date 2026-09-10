# Roadmap dettagliata — Pi_UI

Stato: **M0 completata; M1 è la milestone attiva successiva.** Le versioni indicate sono traguardi proposti, non release esistenti. Aggiornamento: 10 settembre 2026.

## 1. Risultato da ottenere

Un AI OS personale utilizzabile da desktop senza CLI o VS Code, ispirato al partner di ragionamento di Nate Herk. Un unico spazio contiene conoscenze sul lavoro, materiali, obiettivi, vincoli, iniziative e decisioni. Pi Agent usa Ornith 1.5 tramite inferenza LAN; la GUI permette di conversare, consultare e modificare i documenti restando nello stesso ambiente.

Priorità vincolanti:

1. Qualità e continuità della conversazione.
2. Accesso, gestione e consultazione dei file, già nella prima versione utile.
3. Ricerca documentale, fonti e memoria operativa affidabile.
4. Capacità operative e routine introdotte quando servono a workflow reali.

Il test AIOS-bench dell'utente ha già orientato la scelta Pi + Ornith. M0 ha verificato l'integrazione specifica di questa app e non riapre un confronto tra harness.

### Prima esperienza completa da dimostrare

Importare materiali reali, aprire una nuova conversazione, chiedere un parere su una scelta di lavoro. L'agente recupera documenti pertinenti, distingue informazioni e ipotesi, considera decisioni precedenti e permette di aprire ogni fonte accanto alla chat. Una modifica è visibile e recuperabile; riaprendo l'app restano file e conversazioni.

La prima versione utilizzabile è M1; questa esperienza completa diventa criterio di prodotto in M3. Non anticipare in M1 la promessa di comprensione automatica di tutti i formati.

## 2. Ambito iniziale e rinvii espliciti

| Dentro il percorso iniziale | Fuori dalla prima versione |
|---|---|
| Un workspace permanente, molte conversazioni | Gestione multiprogetto e collaborazione multiutente |
| Una sessione agente attiva | Orchestrazione multiagente parallela |
| Pi locale, un profilo Ornith LAN | Marketplace di modelli, training e gestione del server |
| Chat, albero file, editor testuale, diff/versioni | IDE, debugger o terminale come centro della UI |
| Importazione, testo/Markdown e PDF testuale | OCR, audio/video, fogli complessi e office editing completo |
| Ricerca testuale e contesto selettivo | Database vettoriale o knowledge graph obbligatorio |
| Dati locali e backup esplicito | Cloud sync o telemetria automatica |

L'orchestrazione multiagente parallela resta fuori dalla prima versione, ma **la gestione dei subagents è un requisito futuro di prima classe del prodotto**. Dovrà avere un sistema dedicato per definizione/ruolo, modello e contesto, lifecycle, delega, permessi/tool, osservabilità, stato, risultati, errori e rapporto con l'agente principale. La scelta di API, scheduling, parallelismo, memoria condivisa e UX viene deliberatamente rinviata finché non saranno raccolti use case concreti; l'architettura iniziale non deve però rendere strutturale il vincolo di una sola sessione/agente.

I file non supportati possono essere conservati come originali e aperti nell'app esterna, con stato esplicito. “Importato” non equivale a “indicizzato” né a “letto dal modello”.

## 3. Mappa delle milestone

| Milestone | Risultato consegnabile | Dipendenze | Gate |
|---|---|---|---|
| **M0 / 0.1 — completata** | Fondazione e integrazione Pi–LAN verificata | Configurazione locale funzionante dell'utente | Streaming, strumenti, stop, persistenza e shutdown verificati |
| **M1 / 0.2 — prossima** | GUI usabile per chat e file | M0 | Sessione di lavoro completa senza terminale |
| M2 / 0.3 | Conoscenza ricercabile e fonti apribili | M1 | Recupero e citazioni verificati su corpus campione |
| M3 / 0.4 | Memoria operativa e comportamento da partner | M2 | Decisioni persistenti, provenienza e conflitti gestiti |
| M4 / 0.5 | Capacità e routine selezionate | M3 | Almeno una procedura utile, osservabile e interrompibile |
| M5 / 1.0 | Distribuzione e affidabilità consolidata | M0–M4 per le funzioni incluse | Installazione pulita, restore e prove sul desktop target |

Robustezza, accessibilità e protezione dei dati iniziano in M0/M1: M5 consolida le prove. Nessuna durata in settimane è promessa prima della prova tecnica e del campione documentale; stimare il residuo dopo ciascun gate.

## 4. M0 — Fondazione e collegamento reale

**Stato: COMPLETATA il 10 settembre 2026.** Evidenze e limiti sono registrati in [docs/M0_PROGRESS.md](docs/M0_PROGRESS.md).

**Obiettivo:** portare nella nuova integrazione la configurazione Pi–Ornith già funzionante.

La baseline M0.1 è stata ristretta ai dati necessari all'integrazione posseduta da Pi_UI. L'esatto build commit di llama.cpp, chat template e insieme completo dei flag server/generazione non sono stati inventariati integralmente e non vengono dichiarati noti: saranno raccolti quando Pi_UI assumerà responsabilità di configurazione del server o quando servirà una baseline prestazionale riproducibile.

- [x] M0.1 Inventariare la baseline necessaria all'integrazione: Pi/Node/Python/PySide6, Bubblewrap, provider/API/model ID, endpoint LAN, contesto esposto e quantizzazione riportata dal server. Conservare dati privi di segreti; non inventare capacità dal nome Ornith.
- [x] M0.2 Fissare runtime Pi dedicato e range Python/PySide6 compatibili dopo installazione verificata; nessun aggiornamento Pi automatico all'avvio.
- [x] M0.3 Implementare settings tipizzati, default, validazione, migrazione di schema, scrittura atomica e recupero da file malformato. Endpoint e credenziali restano configurazione locale.
- [x] M0.4 Definire AgentTransport e parser RPC indipendenti dalla presentazione; implementare QProcess asincrono come trasporto Qt. Identificare ogni richiesta, correlare risposte e distinguere accettazione del prompt da completamento del turno.
- [x] M0.5 Gestire frame JSONL spezzati, UTF-8 a cavallo di chunk, più frame per lettura, errori, EOF e output eccedente i limiti. Separare stderr e diagnostica dai messaggi RPC.
- [x] M0.6 Introdurre stato processo/turno e timeout distinti per avvio, richiesta, inattività e arresto; valori configurabili adeguati all'inferenza locale lenta. Nessuna `waitFor*` bloccante nel thread grafico.
- [x] M0.7 Configurare il provider compatibile con la baseline reale `openai-completions`, verificando model ID e context window; nessun fallback a cloud o altro modello.
- [x] M0.8 Implementare invio, streaming, stop e chiusura. Specificare la semantica della coda; per uno stop che svuota tutto, usare i comandi disponibili nella versione fissata e recuperare i messaggi non eseguiti.
- [x] M0.9 Configurare sessioni Pi nello storage del workspace controllato dall'app, con ownership esplicita dell'ID; verificare ripresa, stale-session recovery e isolamento da altre installazioni/client Pi.
- [x] M0.10 Creare il primo shell QML minimale con controlli reali per connessione, invio e stop; introdurre test core/trasporto e smoke QML, più CI deterministica su runner ospitati.
- [x] M0.11 Eseguire in LAN risposta streaming, ciclo lettura → modifica file, server-down recovery, confinement Bubblewrap, shutdown e test KDE/Wayland; salvare esiti e versioni.

**Accettazione:** superata. Tre sessioni/reconnect consecutivi con risposta reale; tool e stop verificati; file di prova corretto; sessione ripresa senza duplicare operazioni; failure server recuperato senza deferred replay; nessun processo posseduto rimasto dopo chiusura; test automatici pertinenti verdi; report LAN distinto da CI.

**Uscita:** raggiunta. L'integrazione Pi–Ornith è provata sul target reale e M1 può estendere chat e file senza riaprire il protocollo di base.

## 5. M1 — Chat e file nella prima GUI utilizzabile

**Obiettivo:** svolgere un lavoro completo su note e documenti senza aprire il terminale.

### M1.A — Shell e conversazione

- [ ] Tema unico e componenti RaisedSurface, InsetSurface, NeuButton, NeuToggle; Noto Sans e token del contratto. Valutare visivamente profondità e contrasto su GPU target.
- [ ] Tre aree ridimensionabili: conoscenze a sinistra, chat centrale, documento a destra. Conversazioni in pannello secondario; modalità stretta che mantiene accessibili tutte le aree.
- [ ] Transcript virtualizzato con testo selezionabile, Markdown e codice, copia, autoscroll solo quando l'utente segue il fondo. Rendering nativo, senza caricare risorse remote dal contenuto.
- [ ] Composer multilinea, invio/stop, riferimento a file/passaggio, gestione bozza. Distinguere messaggio inviato, accettato, in coda e fallito.
- [ ] Lista conversazioni con creazione, nome, ricerca dei titoli e ripresa tramite Pi. Una sessione attiva; cambio gestito senza troncare o perdere il turno corrente.
- [ ] Attività strumenti espandibili con argomenti, esito e output limitato; accesso ai dettagli completi senza appesantire la lista.
- [ ] Steering e follow-up esposti con significato esplicito; dialoghi standard delle estensioni supportati o rifiutati chiaramente, con annullamento e timeout. UI TUI personalizzate non dichiarate compatibili.
- [ ] Onboarding grafico per workspace, Pi e server; stato collegamento e contesto quando disponibile, “non disponibile” dove manca. Nessun indicatore fittizio.

### M1.B — File e revisioni

- [ ] WorkspaceService: crea/apre una sola radice, organizza cartelle e garantisce identità stabile dei documenti durante rinomina/spostamento. Modello gerarchico lazy per l'esploratore.
- [ ] Importazione drag-and-drop e dialogo file, copia degli originali, gestione nomi duplicati e hash; originali sorgente esterni non modificati dall'import.
- [ ] Creazione di note/cartelle, rinomina, spostamento, ricerca per nome, recenti e preferiti. Errori di permesso, disco pieno e destinazione esistente spiegati nella UI.
- [ ] Cestino con ripristino e gestione conflitti nel nome; cancellazione definitiva distinta. Gli originali importati restano recuperabili secondo la policy di conservazione.
- [ ] Editor Markdown/testo con stato modificato, salvataggio atomico, recupero bozza e controllo hash/versione prima di sovrascrivere. Rilevare modifiche esterne e chiedere una risoluzione del conflitto.
- [ ] Anteprima dei formati supportati e apertura esterna degli altri. Nessuna conversione implicita da PDF/Office a documento editabile equivalente.
- [ ] Snapshot e diff testuale, autore user/agent/external quando determinabile, timestamp e hash. Ripristino crea una nuova revisione; non cancella la storia.
- [ ] Prima di attivare scritture autonome di Pi, verificare il percorso di versionamento anche per tool che scrivono direttamente. Un watcher registra cambiamenti ma non garantisce da solo la cattura del contenuto precedente.
- [ ] Risolvere concorrenza editor/agente con controllo versione e coordinamento; niente “last writer wins” silenzioso. Trattare scritture parziali e file binari esplicitamente.

**Accettazione:** importare dieci file di prova inclusi nomi duplicati/Unicode; modificare una nota, farla leggere/modificare all'agente, confrontare e ripristinare; gestire un conflitto esterno; rinominare senza rompere il collegamento interno; chiudere e riaprire ritrovando sessioni, file e bozze. Tutto dalla GUI.

**Uscita:** alpha realmente utilizzabile. La ricerca nel contenuto dei documenti estratti arriva in M2; in M1 i riferimenti manuali devono includere contenuto effettivamente leggibile da Pi.

## 6. M2 — Conoscenza consultabile e citazioni

**Obiettivo:** trovare e leggere materiali pertinenti senza inserire tutto l'archivio nel prompt.

- [ ] M2.1 Pipeline asincrona con stati `imported`, `extracting`, `indexed`, `unsupported`, `failed`, `stale`; avanzamento, annullamento e retry esplicito. Identificare ogni job per documento/revisione.
- [ ] M2.2 Estrarre TXT/Markdown e PDF testuale; preservare originali e riferimenti a pagina/paragrafo. Documenti vuoti, cifrati, scansioni e layout problematici producono uno stato spiegabile. DOCX/ODT seguono se presenti nel campione reale.
- [ ] M2.3 Indicizzare con SQLite FTS5, previa verifica disponibilità nella distribuzione. Indice incrementale per hash, aggiornamento/cancellazione coerenti e ricostruzione completa. Originali e metadati canonici bastano a ricostruirlo.
- [ ] M2.4 Ricerca nomi/contenuto con estratti, filtri, titolo, percorso, revisioni e stato; query eseguite fuori dal thread GUI. Risultati paginati, nessuna scansione completa a ogni tasto.
- [ ] M2.5 Esporre a Pi strumenti minimi di ricerca e lettura attraverso un'estensione sottile, usando servizi Python come unica implementazione. Definire e testare il canale IPC locale prima di integrarlo.
- [ ] M2.6 Costruire contesto selettivo: profilo compatto e mappa, query, lettura dei passaggi, eventuale approfondimento. Registrare budget e fonti lette; riservare spazio a output e tool senza inventare token usage esatto.
- [ ] M2.7 Citazioni con ID documento, hash/revisione e locator; risoluzione nella UI anche dopo spostamenti. Se il documento è cambiato, mostrare versione citata oppure stato non risolvibile, mai il passaggio sbagliato in silenzio.
- [ ] M2.8 Verificare che un riferimento citato esista e sia stato letto; distinguere questa validazione meccanica dalla correttezza semantica della risposta, che richiede valutazione separata.
- [ ] M2.9 Definire corpus di prova sintetico e campione privato locale. Misurare recupero di fonti attese, citazioni, assenza di evidenza, aggiornamento e cancellazione dell'indice.
- [ ] M2.10 Valutare ricerca semantica solo se errori reali di recupero la giustificano; confrontare costi, latenza e risultati con FTS sullo stesso campione prima di introdurre embedding locali.

**Accettazione:** almeno venti domande curate, incluse cinque senza risposta nel corpus. Target iniziale da confermare col campione: fonte attesa nei primi cinque risultati per almeno il 90% delle domande rispondibili; 100% dei riferimenti mostrati risolvibili o esplicitamente segnalati come non disponibili. Le domande senza evidenza non devono produrre fatti documentali inventati. Valutazione delle risposte separata dal punteggio del retriever.

**Uscita:** report con errori residui e corpus/versioni identificabili. Nessun “RAG funzionante” basato sulla sola presenza di un indice.

## 7. M3 — Memoria operativa e partner di ragionamento

**Obiettivo:** conservare ciò che conta del lavoro anche iniziando nuove conversazioni.

- [ ] M3.1 Onboarding conversazionale per ruolo, attività, obiettivi, vincoli, preferenze e criteri decisionali. Importare contesto esistente; distinguere conferme dell'utente e inferenze.
- [ ] M3.2 Struttura iniziale modificabile: contesto, originali, conoscenze, decisioni, iniziative, archivio. I nomi delle cartelle non diventano dipendenze rigide del codice.
- [ ] M3.3 Note in formati aperti con ID, provenienza, data, revisione e stato. La data di importazione non sostituisce la data di validità della fonte.
- [ ] M3.4 Registro decisioni append-only a livello applicativo: proposta, confermata, superata/revocata, riferimenti e motivazione. La decisione nuova collega quella precedente. Non promettere immutabilità contro modifiche esterne dei file.
- [ ] M3.5 Flusso di aggiornamento memoria: proposta diff → autorizzazione pertinente → scrittura versionata. Un'istruzione esplicita a registrare una decisione può costituire autorizzazione; non aggiungere conferme rituali per ogni operazione reversibile.
- [ ] M3.6 Separare fatti documentati, affermazioni dell'utente, decisioni e ipotesi dell'agente. Un suggerimento non viene promosso automaticamente a fatto sul lavoro.
- [ ] M3.7 Segnalare conflitti tra fonti, informazioni superate e assenza di dati; dare precedenza contestuale a decisioni confermate più recenti senza cancellare le precedenti.
- [ ] M3.8 Prompt/istruzioni AI OS distinti dall'AGENTS.md che governa lo sviluppo del software. Versionarli con l'app e renderne visibile l'effetto; non usare una chat infinita come memoria.
- [ ] M3.9 Aggiornamenti di conoscenza durante la compattazione solo con le stesse regole di provenienza; il riassunto di sessione di Pi resta un oggetto diverso dal profilo persistente.
- [ ] M3.10 Valutazione con scenari: parere strategico, obiezione motivata, conflitto tra decisioni, domanda senza evidenza e ripresa in chat nuova.

**Accettazione:** una decisione confermata è recuperata in una nuova chat; una successiva la supera senza cancellarla; una proposta rifiutata non riappare come fatto; un'inferenza è etichettata; citazioni apribili; raccomandazione coerente con obiettivi e vincoli del corpus. Valutazione umana locale registrata, senza dichiarare deterministico il giudizio sul ragionamento.

## 8. M4 — Capacità operative e routine

**Obiettivo:** aggiungere capacità che risolvono attività ricorrenti osservate nell'uso reale.

- [ ] M4.1 Scegliere con l'utente una procedura prioritaria: revisione settimanale, preparazione riunione o aggiornamento iniziativa. Prima manuale dalla GUI, poi automatizzabile.
- [ ] M4.2 Procedure riutilizzabili mediante capacità native di Pi, con input/output, fonti necessarie e criterio di completamento. UI per eseguirle e leggere esiti/errori.
- [ ] M4.3 Registro connessioni con capacità, stato e ambito. Iniziare da una sola integrazione necessaria; API ufficiali, segreti separati e nessuna duplicazione di dati senza necessità.
- [ ] M4.4 Azioni esterne osservabili e autorizzate, con anteprima quando utile e nessuna dichiarazione di invio/salvataggio prima dell'esito reale. Le policy risiedono nei servizi e negli strumenti, non nei soli pulsanti.
- [ ] M4.5 Scheduler locale con timezone, ora legale, macchina sospesa, esecuzioni perse, lock contro sovrapposizione e idempotenza. Definire se opera solo con app aperta o tramite servizio esplicito.
- [ ] M4.6 Cronologia delle esecuzioni, sorgenti usate, stop e retry controllato. Le routine entrano nella stessa coda dell'unica sessione attiva.
- [ ] M4.7 Progettare e implementare un sistema dedicato di gestione dei subagents, dopo aver definito con l'utente i casi d'uso prioritari. Devono essere espliciti almeno identità/ruolo, stato e lifecycle, modello/contesto, delega e ritorno risultati, permessi/tool, osservabilità, error handling e relazione con l'agente principale. Evitare di fissare oggi parallelismo, memoria condivisa o UX senza evidenze d'uso.

**Accettazione:** una procedura utile completata manualmente e, se schedulata, una volta sola nella finestra prevista; disconnessione e riavvio non duplicano effetti; nessun invio esterno senza autorizzazione applicabile; errore visibile e recuperabile. I criteri di accettazione specifici dei subagents saranno definiti quando il relativo design verrà aperto.

## 9. M5 — Robustezza e distribuzione

- [ ] M5.1 Consolidare crash recovery, server irraggiungibile, processo Pi terminato, schema RPC incompatibile, disco pieno e file/database danneggiati. Nessun replay automatico di tool dopo esito incerto.
- [ ] M5.2 Sessioni molto lunghe, output strumenti voluminosi, PDF grandi e importazioni massive: paginazione, limiti, cancellazione, risorse rilasciate e GUI reattiva.
- [ ] M5.3 Backup consistente di file, metadati, revisioni, settings e sessioni Pi; indice escluso se ricostruibile. Restore provato in un workspace separato, con hash e verifica delle citazioni.
- [ ] M5.4 Installer Bash idempotente e indipendente dalla CWD, venv riparabile, dipendenze fissate, verifiche QML/shader e launcher desktop. Aggiornamento con backup e rollback compatibile con le migrazioni dati.
- [ ] M5.5 Test su KDE/CachyOS target, Wayland e X11 se dichiarati supportati, scaling 100/125/150/200%, tastiera e focus. Windows è un target successivo finché non verificato.
- [ ] M5.6 Misurare avvio, latenza UI, ricerca, scroll e PSS di GUI/Pi/worker. Pubblicare hardware, backend grafico, dataset, condizioni e ripetizioni; distinguere inferenza LAN da overhead client. Quando serve riproducibilità server, registrare anche build llama.cpp, chat template e flag di generazione/server pertinenti.
- [ ] M5.7 Documentare accessi file/rete, trust delle estensioni e limiti di isolamento. Se si vuole confinamento alla cartella, adottare sandbox di sistema e provare anche shell, symlink e processi figli prima di dichiararlo.
- [ ] M5.8 Scegliere licenza, verificare licenze delle dipendenze e del font distribuito, preparare note di rilascio, guida breve e troubleshooting.

**Accettazione:** installazione da ambiente pulito e ripetuta riuscite, prima configurazione interamente guidata, crash recovery e restore dimostrati, nessun processo orfano nei casi coperti, verifiche della release verdi e limiti documentati.

## 10. Rischi e decisioni che bloccano il passo successivo

| Rischio | Azione concreta | Gate |
|---|---|---|
| Differenze rispetto alla configurazione Ornith validata | Manifest locale e test del medesimo ciclo strumenti | M0 |
| RPC/trust/estensioni cambiano tra versioni | Versione fissata e contratti verificati contro quella versione | M0, aggiornamenti |
| Due proprietari delle sessioni o della memoria | Pi canonico per sessioni; file canonici per conoscenza; indice derivato | Tutte |
| Scritture Pi o shell saltano versioni/policy | Integrare e provare tutti i percorsi di scrittura abilitati; restringere capacità non coperte | Prima delle scritture M1 |
| Editor e agente sovrascrivono lavoro | Confronto hash, gestione conflitti e snapshot prima delle operazioni | M1 |
| Citazioni inventate o obsolete | ID/revisione/locator e registro letture; validazione separata della pertinenza | M2 |
| PDF non estraibile | Originale conservato, errore esplicito, OCR rinviato | M2 |
| Archivio saturo nel contesto | Recupero selettivo e budget; compattazione Pi visibile | M2–M3 |
| Prompt injection da documenti | Documenti trattati come dati; capacità limitate e policy applicate fuori dal modello | M1–M4 |
| Estensione TypeScript duplica il backend | Trasporto minimo verso servizi Python; contratto unico | M2 |
| Neumorfismo compromette leggibilità/prestazioni | Focus/contrasto e misure su GPU, effetti condivisi | M1, M5 |
| Automazione ripete un'azione esterna | ID esecuzione, stato persistente e recupero dell'esito prima del retry | M4 |
| Subagents introducono ownership o concorrenza ambigua | Definire casi d'uso, ownership, lifecycle, permessi, stato e osservabilità prima di scegliere l'orchestrazione | Design subagents |

## 11. Ordine delle prime attività

1. **M0 completata:** baseline applicativa, parser/stato/processo, provider LAN, session ownership, sandbox, shell minima, fault recovery e prove target concluse.
2. **M1 attiva:** chat e file in incrementi completi, prima lettura e poi scrittura/versioni verificate.
3. M2–M3: ricerca, citazioni e memoria valutate sul campione reale.
4. M4: una routine selezionata e design subagents quando i casi d'uso sono definiti; M5: consolidamento e release.

Ogni milestone chiude con revisione strategica di ownership, duplicazioni, confini Qt/Python/Pi e complessità introdotta. Eventuali deviazioni vanno in [DECISIONS.md](docs/DECISIONS.md); criteri e prove in [VALIDATION.md](docs/VALIDATION.md). Fonti e fatti upstream sono raccolti in [SOURCES.md](docs/SOURCES.md).
