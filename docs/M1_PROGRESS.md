# M1 progress — chat e file

Aggiornamento: 10 settembre 2026.

M1 è la milestone attiva. Questo documento distingue ciò che è già integrato e coperto automaticamente da ciò che richiede ancora verifica sul desktop target o appartiene a slice successive.

## Stato attuale

### Shell/chat già disponibili

- shell desktop PySide6/QML collegata a Pi RPC reale;
- workspace e profilo modello selezionabili dalla GUI;
- connessione/disconnessione, transcript, composer multilinea, invio e stop;
- composer con scorrimento verticale per draft lunghi;
- preflight host e gate Bubblewrap disponibili dalla GUI;
- comportamento Pi/Ornith di base ereditato dalla M0 già verificato sul target reale.

### Knowledge browser

- esploratore workspace lazy basato su `QAbstractListModel` + `ListView` con `reuseItems`;
- scansione delle directory fuori dal thread GUI;
- percorsi confinati con apertura descriptor-based e `O_NOFOLLOW`;
- symlink visibili come leaf ma mai attraversati;
- righe compatte e icone deterministiche per directory/file/symlink/altri tipi;
- refresh esplicito; nessun watcher filesystem ancora introdotto.

Le correzioni UX del tree e dello scrolling composer sono state accettate sul target reale e le issue #28 e #29 risultano chiuse.

### Preview documenti — PR #34

Merge su `main`: `a15e1bd2f705b4eaf431eae36b96a7bd97547f4a`.

Architettura:

- policy filesystem in `core/workspace_access.py` e `core/workspace_document.py`;
- `WorkspaceBrowserController` resta proprietario esclusivamente della proiezione dell'albero;
- `WorkspaceDocumentController` separato possiede selezione/stato transitorio della preview;
- `QtDocumentLoadRunner` esegue le letture fuori dal thread GUI;
- `WorkspaceDocumentAdapter` espone solo valori/azioni di presentazione al QML;
- `AgentController` continua a possedere la radice canonica del workspace e non assorbe logica documentale.

Policy della preview:

- UTF-8 e UTF-8 BOM;
- limite esplicito di 1 MiB;
- rifiuto di symlink, file non regolari, contenuto binary-looking, UTF-8 non valido e file oltre limite;
- apertura dei componenti parent e del file finale con semantica fail-closed contro sostituzioni con symlink;
- lettura massima limitata e `fstat` del descriptor finale;
- Reload esplicito per osservare modifiche esterne.

Rendering/copia:

- il testo sorgente decodificato, inclusi i terminatori originali, resta canonico in Python;
- Qt normalizza CRLF/lone CR nel proprio `TextArea`: la proiezione visuale viene quindi resa esplicita anziché trattata come stato canonico;
- la copia di una selezione rimappa gli offset UTF-16 Qt sul sorgente originale, preservando CRLF/lone CR e caratteri non-BMP;
- nessun Markdown o caricamento di risorse remote nella preview M1 corrente.

Layout:

- su finestra larga sono visibili Knowledge + Conversation + Document;
- sotto la soglia responsive la preview usa un drawer destro, evitando di comprimere i controlli principali oltre il minimo supportato.

## Evidenza automatica corrente

Exact head della PR #34 prima del merge: `221ed06efa379411413a11953606a8bd1451e9b2`.

GitHub Actions run `34475769073` ha completato con successo su Python 3.12, 3.13 e 3.14:

- installazione dipendenze;
- `python -m compileall` sui sorgenti/test;
- `pyside6-qmllint --max-warnings 0`;
- suite pytest completa inclusi smoke QML offscreen.

La suite include casi per Unicode, UTF-8 BOM, file vuoti, CRLF/LF, binari, UTF-8 invalido, limite dimensione, symlink, race sul file finale, cancellation, risultati stale, cambio workspace, reload dopo modifica esterna, thread runner e layout QML responsive. È inoltre coperto il mapping delle selezioni Qt UTF-16 al testo sorgente esatto.

## Gate ancora aperto per #27

La issue #27 resta aperta deliberatamente fino a una verifica sul desktop reale CachyOS/Wayland. La CI offscreen non sostituisce questa prova.

Da verificare sul target:

1. clic su un file UTF-8 reale nell'albero → preview corretta e UI reattiva;
2. Reload dopo modifica esterna → contenuto aggiornato;
3. file non supportato/binario → stato esplicito senza blocchi;
4. selezione e `Ctrl+C` da un file con CRLF/Unicode → testo incollato corretto;
5. finestra larga → tre pannelli utilizzabili senza sovrapposizioni;
6. finestra alla larghezza minima → apertura/chiusura del drawer Document senza overflow o controlli irraggiungibili;
7. scroll di un documento più lungo del viewport;
8. nessuna regressione evidente su chat, Knowledge tree, focus e interazione Wayland.

Solo dopo questa prova #27 può essere chiusa come `completed`.

## Slice successive M1

Non sono ancora implementati e non vanno considerati completati:

- importazione file drag-and-drop/dialogo con deduplica/hash;
- creazione di note/cartelle, rinomina e spostamento;
- editor Markdown/testo e salvataggio atomico;
- recovery bozze e conflitti da modifica esterna;
- cestino/ripristino;
- snapshot, diff e version history;
- coordinamento tra editor e scritture dell'agente;
- ricerca per nome/recenti/preferiti e, in M2, ricerca nel contenuto.

Il prossimo lavoro dopo il gate #27 deve continuare a mantenere i servizi documentali fuori da `AgentController` e introdurre scritture soltanto insieme a proprietà dello stato, atomicità e conflitti espliciti.
