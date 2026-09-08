# Strategia di validazione

Questo documento distingue le verifiche già automatizzate da quelle che richiedono il desktop/rete target. Un gate viene dichiarato superato soltanto quando esiste un'esecuzione osservata sul commit pertinente; CI sintetica, test offscreen e prove LAN non sono intercambiabili.

## Livelli e prove necessarie

| Livello | Casi rilevanti | Ambiente |
|---|---|---|
| Core/settings | Config malformata, default/migrazioni, Unicode, path, hash/revisioni, rollback, timeout | pytest senza modello |
| RPC | Frame parziali/multipli, UTF-8, LF/CRLF, correlazione, ACK vs completion, timeout, EOF e limiti | Fixture sintetiche e processo di test |
| Controller | Invio/coda/stop, stato incerto, nessun replay, riconciliazione, crash e lifecycle | Test deterministici |
| Modelli/adapter Qt | Ruoli stabili, insert/update/reset, validazione slot e notifiche | Qt event loop |
| QML | Load, binding, segnali, shell, import e warning | `qmllint` + smoke offscreen |
| Process lifecycle | startup, stderr separato, terminate, escalation kill, chiusura applicazione asincrona | QProcess reale sintetico |
| Sandbox | mount RW/RO, symlink, HOME/socket/process visibility, processi figli, shutdown/orfani | CachyOS target + Bubblewrap reale |
| Filesystem prodotto | Import duplicato, rename, conflitto editor/agente, cestino, crash recovery | Directory temporanee isolate + target |
| Grafica reale | Inset, ombre, contrasto, scala, scroll e focus | Desktop KDE/Wayland con GPU target |
| LAN reale | Ornith streaming/tool use, context usage, stop, disconnessione e ripresa | Solo macchina/rete dell'utente |
| Prodotto | Recupero fonti, decisioni, obiezioni, assenza di evidenza e nuova chat | Corpus sintetico + campione privato locale |
| Distribuzione | Installazione pulita/ripetuta, launcher, aggiornamento, rollback, backup/restore | Ambiente target controllato |

Un processo finto verifica gestione del protocollo/process lifecycle, non che Ornith sappia usare strumenti. Offscreen verifica caricamento/binding, non la resa grafica su GPU. Un launch-spec Bubblewrap corretto non dimostra da solo che il namespace reale impedisca accessi esterni.

## Gate automatico corrente

La CI GitHub ospitata usa dati sintetici e nessun runner self-hosted. Su Python 3.12 e 3.13 esegue:

1. installazione delle librerie runtime Qt necessarie al runner e del package con dipendenze test;
2. `python -m compileall -q controllers core ui tests main.py`;
3. `pyside6-qmllint --max-warnings 0 -I ui/qml ui/qml/PiUI/*.qml`;
4. `python -m pytest` con `QT_QPA_PLATFORM=offscreen`.

La suite corrente comprende tra l'altro parser JSONL, settings/migrazioni, gestione `models.json`, bootstrap runtime, AgentClient, controller, Qt models/adapter, QML smoke, un subprocess RPC sintetico, deadline Qt, timeout request/inattività, forced QProcess kill e coordinamento della chiusura applicativa.

Non inserire endpoint LAN, file privati, modelli o credenziali nella CI pubblica.

## Regole per cambi applicativi

1. Eseguire compileall, pytest pertinente e ruff se verrà adottato.
2. Eseguire `qmllint` a zero warning e smoke con engine/adapter/modelli reali per il percorso modificato.
3. Se presenti shader, bake con il `pyside6-qsb` della stessa distribuzione PySide6 e verifica delle varianti; la resa va provata anche su GPU target.
4. Per processi/concorrenza verificare cancellazione, timeout, escalation e chiusura dei processi posseduti; non limitarsi alla scomparsa della finestra.
5. Un timeout di una richiesta con possibili effetti **non autorizza un retry automatico**: l'esito va trattato come incerto e riconciliato.
6. Un watchdog di inattività non deve essere confuso con un hard timeout dell'inferenza: deve restare compatibile con modelli/tool locali lenti.
7. Registrare commit, ambiente, scenario, risultato e limiti. Non sostituire una prova non eseguita con una spunta.

## Gate M0 locale guidato

Il preflight dovrà preparare il seguente percorso, da eseguire sul desktop target quando servirà l'intervento dell'utente:

1. acquisire senza segreti versione/path di Bubblewrap, Pi, Node, Python/PySide6 e configurazione modello scoperta;
2. verificare che sandboxing sia abilitato e che i path runtime richiesti esistano/eseguibili;
3. avviare Pi dentro Bubblewrap e verificare via RPC modello/sessione realmente selezionati;
4. tentare lettura/scrittura fuori AIOS root e attraverso symlink verso l'esterno: devono fallire;
5. verificare che HOME reale, D-Bus/display, SSH/GPG agent e altre directory personali non siano disponibili;
6. avviare shell/tool child tramite Pi e confermare che ereditino il namespace;
7. confermare connettività Ornith LAN senza dichiarare egress filtering che `--share-net` non fornisce;
8. eseguire tre sessioni consecutive con streaming; stop `clear_queue → abort`; resume sessione;
9. eseguire un ciclo lettura → modifica di un file di prova dentro AIOS root → verifica;
10. simulare server irraggiungibile/process crash e controllare nessun replay automatico;
11. chiudere l'app durante attività e verificare assenza di processi Pi/child posseduti rimasti;
12. salvare un report locale sanitizzato con versioni, esiti e limiti.

Il gate va considerato fallito se una verifica di confinement non può essere osservata direttamente. Nessun fallback unsandboxed può trasformare un fallimento in successo.

## Scenari di accettazione del prodotto

| ID | Preparazione e azione | Esito osservabile |
|---|---|---|
| E01 | Configurare Pi/Ornith e inviare una richiesta dalla GUI | Risposta reale in streaming; ACK distinto dal completamento |
| E02 | Accodare un messaggio durante il turno, poi fermare | Semantica della coda rispettata, testo non perso, nessuna azione inattesa |
| E03 | Lasciare scadere artificialmente l'ACK di un prompt | Stato `uncertain`, nessun resend, nuovi invii bloccati fino a riconciliazione |
| E04 | Lasciare il turno senza eventi oltre il watchdog | Warning visibile, processo non terminato, Stop ancora disponibile |
| E05 | Importare/rinominare/spostare una nota referenziata | ID invariato e fonte ancora risolvibile |
| E06 | Modificare una nota nell'editor e dall'esterno | Conflitto esplicito, nessuna perdita silenziosa |
| E07 | Far modificare un file all'agente e ripristinare | Versione precedente disponibile; restore come nuova revisione |
| E08 | Importare PDF testuale, scansione e file corrotto | Stati distinti, nessun falso documento ricercabile |
| E09 | Fare venti domande del corpus, cinque senza evidenza | Report recupero/citazioni; lacune dichiarate |
| E10 | Confermare una decisione e aprire una nuova chat | Decisione recuperata con provenienza e data |
| E11 | Superare una decisione e rifiutare una proposta | Storia conservata, stato attuale corretto |
| E12 | Spegnere server o terminare Pi a metà operazione | Errore visibile, stato ricostruito, nessuna riesecuzione automatica |
| E13 | Chiudere l'app durante tool/processo attivo | Shutdown/escalation osservabili, nessun processo posseduto orfano |
| E14 | Ripristinare backup in directory nuova | Hash/contenuti coerenti, sessioni e citazioni ripristinate |

## Misure e criteri

M0 registra la baseline prima di fissare budget prestazionali. Annotare CPU/GPU/RAM, OS, backend Qt, versioni, dimensioni corpus e contesto. Per confronti successivi usare lo stesso scenario e almeno cinque ripetizioni; riportare mediana e intervallo, separando cache fredda/calda.

Misurare PSS per GUI, Pi e worker da `/proc/<pid>/smaps_rollup`; il server LAN va riportato separatamente. Separare tempo del modello da overhead client. Misurare crescita delle risorse su operazioni ripetute, non soltanto al primo avvio.

Per la ricerca, i target iniziali sono nella roadmap M2: documentare corpus, domande, revisioni attese, hit nei primi cinque risultati e riferimenti non risolvibili. Un riferimento valido non dimostra che la fonte sostenga l'affermazione: il giudizio semantico resta separato.

## Evidenze di milestone

Per ogni gate conservare un report con commit applicazione, versioni runtime/modello, scenari, esiti, difetti aperti e limiti. Usare soltanto dati sintetici/sanitizzati nella repository pubblica. Report LAN e materiali privati rimangono locali; in repo pubblicare solo esiti aggregati non sensibili.