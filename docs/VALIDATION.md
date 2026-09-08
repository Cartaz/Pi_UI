# Strategia di validazione

Questo documento descrive verifiche **future**. Nel bootstrap documentale non sono esistenti né eseguiti test dell'app, QML, shader, LAN o pipeline CI.

## Livelli e prove necessarie

| Livello | Casi rilevanti | Ambiente |
|---|---|---|
| Core/settings | Config malformata, default/migrazioni, Unicode, path, hash/revisioni, rollback, indice ricostruito | pytest senza modello |
| RPC | Frame parziali/multipli, UTF-8, LF/CRLF, Unicode interno, correlazione, errori prima/dopo accettazione, EOF e limiti | Fixture sintetiche e processo di test |
| Controller | Invio/coda/stop, cambio sessione rifiutato, crash, stato incerto, nessun replay, job obsoleti | Test deterministici |
| Modelli/adapter Qt | Ruoli stabili, insert/remove/update, reset, validazione slot e notifiche corrette | Qt test/event loop |
| QML | Load, binding, segnali, focus, tastiera, layout e controlli con backend di test | Lint e smoke offscreen |
| Filesystem | Import duplicato, symlink, rename, conflitto editor/agente, disco pieno simulato, cestino, crash tra file e metadati | Directory temporanee isolate |
| Grafica reale | Inset, ombre, contrasto, shader GLSL, scala, scroll e focus | Desktop KDE con GPU |
| LAN reale | Ornith streaming/tool use, context usage, compattazione, stop, disconnessione e ripresa | Solo macchina/rete dell'utente |
| Prodotto | Recupero fonti, decisioni, obiezioni, assenza di evidenza e nuova chat | Corpus sintetico + campione privato locale |
| Distribuzione | Installazione pulita/ripetuta, launcher, aggiornamento, rollback, backup/restore | Ambiente target controllato |

Un processo finto serve a verificare la gestione del protocollo, non prova che Ornith sappia usare strumenti. Offscreen prova il caricamento, non il risultato grafico di uno shader su GPU. Nessuna delle due verifiche sostituisce l'altra.

## Gate per cambi applicativi

Quando saranno presenti codice e toolchain:

1. Eseguire compileall sui package applicativi e sui test; pytest pertinente e ruff se adottato.
2. Eseguire lint QML della venv e smoke con engine, adapter e modelli reali per il percorso modificato.
3. Se presenti shader, bake con PySide6-matched `pyside6-qsb --qt6`, verifica varianti e load; prova grafica Linux/OpenGL per affermazioni di resa.
4. Per processi/concorrenza, verificare annullamento e chiusura inclusi processi figli; non limitarsi a osservare la scomparsa della finestra.
5. Registrare comando, commit, ambiente, risultato e limiti. Non sostituire una prova non eseguita con una spunta.

I comandi esatti saranno definiti insieme al primo codice M0. Non aggiungere una CI che risulta verde solo perché non raccoglie test. I controlli ordinari usano runner GitHub ospitati e dati sintetici; nessun runner self-hosted, modello scaricato o endpoint LAN in CI.

## Scenari di accettazione del prodotto

| ID | Preparazione e azione | Esito osservabile |
|---|---|---|
| E01 | Configurare Pi/Ornith e inviare una richiesta dalla GUI | Risposta reale in streaming, errore distinguibile dal completamento |
| E02 | Accodare un messaggio durante il turno, poi fermare | Semantica dichiarata della coda rispettata, testo non perso, nessuna azione inattesa |
| E03 | Importare, rinominare e spostare una nota referenziata | ID invariato e fonte ancora risolvibile |
| E04 | Modificare una nota nell'editor e dall'esterno | Conflitto esplicito, nessuna perdita silenziosa |
| E05 | Far modificare un file all'agente e ripristinare | Versione precedente disponibile; restore come nuova revisione |
| E06 | Importare PDF testuale, scansione e file corrotto | Stati distinti, nessun falso documento ricercabile |
| E07 | Fare venti domande del corpus, cinque senza evidenza | Report recupero e citazioni; lacune dichiarate, giudizio semantico separato |
| E08 | Confermare una decisione e aprire una nuova chat | Decisione recuperata con provenienza e data |
| E09 | Superare una decisione e rifiutare una proposta | Storia conservata, stato attuale corretto, proposta rifiutata non trattata come fatto |
| E10 | Spegnere il server o terminare Pi a metà operazione | Errore visibile, stato ricostruito, nessuna riesecuzione automatica |
| E11 | Chiudere l'app durante estrazione e tool | Job chiusi/recuperabili, nessun processo posseduto orfano |
| E12 | Ripristinare backup in una directory nuova | Hash/contenuti coerenti, sessioni riprendibili e citazioni funzionanti |

## Misure e criteri

M0 registra la baseline prima di fissare budget prestazionali. Annotare CPU/GPU/RAM, OS, backend Qt, versioni, dimensioni corpus e contesto. Per confronti successivi usare lo stesso scenario e almeno cinque ripetizioni; riportare mediana e intervallo, separando cache fredda/calda.

Misurare PSS per GUI, Pi e worker da `/proc/<pid>/smaps_rollup`; il server LAN va riportato separatamente. Separare tempo di risposta del modello da latenza del client. Misurare crescita delle risorse dopo ripetuti apri/chiudi documento e cambio sessione, non soltanto memoria al primo avvio.

Per la ricerca, i target iniziali sono nella [roadmap M2](../ROADMAP.md): documentare corpus, domande, revisioni attese, hit nei primi cinque risultati e riferimenti non risolvibili. Un link valido non dimostra che la fonte sostenga l'affermazione: controllare anche questo nel campione locale.

## Evidenze di milestone

Per ogni gate conservare un report con: commit applicazione, versioni dei runtime/modello, scenari, esiti, difetti aperti e limiti. Usare soltanto dati sintetici o sanitizzati nella repository pubblica. Report LAN e materiali di lavoro privati rimangono locali; in repo pubblicare solo esiti aggregati non sensibili.
