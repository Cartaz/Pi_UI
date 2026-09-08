# M0 — Stato di avanzamento

Aggiornamento: 8 settembre 2026.

Questo documento registra evidenze incrementali della milestone M0 senza dichiarare completati i gate che richiedono la configurazione Pi/Ornith reale sulla LAN e la macchina CachyOS target.

## Tranche 1 — Fondazione core

Implementato nel ramo `m0/core-foundation`:

- `core/settings.py`: settings tipizzati, percorsi XDG, validazione, scrittura atomica con `fsync`/`os.replace`, preservazione e recupero da file JSON malformato o non compatibile; endpoint e riferimenti a credenziali restano locali.
- `core/agent/protocol.py`: framing RPC JSONL incrementale, delimitatore LF stretto, CRLF tollerato, UTF-8 spezzato tra chunk, più record per lettura, EOF parziale, record non validi e limite massimo per record.
- `core/agent/transport.py`: contratto `AgentTransport` indipendente da Qt con stato processo esplicito e canale diagnostico distinto dal protocollo.
- `pyproject.toml` e CI GitHub ospitata per compileall/test su Python 3.12/3.13.

## Tranche 2 — Runtime Bubblewrap, stato RPC e QProcess

Implementato nello stesso ramo:

- Settings schema 2 con migrazione esplicita dalla prima configurazione M0; il vecchio default `executable: "pi"` viene migrato al runtime gestito `/opt/pi-agent/bin/pi` senza trattare il file come corrotto.
- Runtime Bubblewrap derivato dalla configurazione già usata dall'utente: AIOS root host montata come `/workspace`, runtime `/opt/pi-agent` e `/usr` read-only, home/tmp temporanei, config/sessioni in `/workspace/.pi-agent`, rete host condivisa per LAN/Internet, nessun fallback sandbox → host automatico.
- Ambiente child allow-list: `HOME`, `PATH`, locale, variabili Pi e soltanto l'eventuale variabile credenziale nominata nei settings. `DISPLAY`, `SSH_AUTH_SOCK` e ambiente desktop non vengono copiati implicitamente. Le credenziali non vengono inserite negli argomenti Bubblewrap/Pi.
- Alias FHS `/bin`, `/sbin`, `/lib`, `/lib64` ricreati come symlink verso `/usr`, necessari quando il root Bubblewrap espone soltanto `/usr` come albero di sistema.
- `core/agent/client.py`: ID richiesta, correlazione risposta, prompt/steer/follow-up, stato turno e stop ordinato `clear_queue → abort`. Una risposta positiva a `prompt` non chiude il turno; `agent_settled` è il segnale di ritorno all'idle.
- `ui/native/agent_process.py`: trasporto PySide6 `QProcess` completamente asincrono, stdout JSONL e stderr diagnostico separati, startup/shutdown timer, `terminate()` con escalation a `kill()`, nessun `waitFor*` nel thread GUI.
- Test del trasporto Qt con un vero subprocess RPC sintetico: stdin/stdout/stderr, correlazione di base e lifecycle vengono attraversati dall'event loop Qt, non simulati sostituendo `QProcess`.

### Verifiche osservate

- CI GitHub ospitata su Python 3.12: compileall e test passati per i cicli completi precedenti all'ultimo affinamento del profilo Bubblewrap.
- CI GitHub ospitata su Python 3.13: compileall e test passati per gli stessi cicli.
- Il test QProcess reale sintetico è incluso in tali cicli verdi.
- L'ultimo affinamento aggiunge soltanto gli alias FHS del sandbox e il relativo test; il gate finale va registrato sul commit head prima del merge.

Queste prove verificano codice Python/PySide6 e protocollo sintetico. **Non provano ancora** che `/opt/pi-agent`, Bubblewrap, Pi, Node, llama.cpp e Ornith funzionino insieme sul computer dell'utente, né che il profilo resista a tutti i tentativi di accesso fuori workspace.

## Contratto Pi verificato upstream

La documentazione ufficiale corrente di Pi conferma i punti su cui si basa questa integrazione:

- RPC per integrazioni non-Node tramite `pi --mode rpc` su stdin/stdout JSONL.
- Framing con LF come unico delimitatore di record; gli ID opzionali correlano comando e risposta.
- La risposta positiva a `prompt` indica accettazione/coda/gestione del comando, non il completamento del turno; gli eventi continuano in modo asincrono.
- `agent_end` può essere seguito da retry, compattazione o continuazioni; `agent_settled` indica che non resta alcuna continuazione automatica.
- Per uno stop interattivo, Pi documenta `clear_queue` prima di `abort`, così i messaggi accodati possono essere recuperati dal client.
- `--session-dir` e `PI_CODING_AGENT_SESSION_DIR` permettono di separare le sessioni.
- `PI_CODING_AGENT_DIR` permette di isolare la configurazione Pi usata dall'app.
- `PI_SKIP_VERSION_CHECK` disabilita il check versione all'avvio; `PI_OFFLINE` disabilita le operazioni di rete di startup documentate.
- Pi supporta estensioni, skill, prompt template, temi e package; queste primitive saranno esposte dalla GUI invece di mantenere un fork di Pi.

Riferimenti primari:

- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md

Questi riferimenti puntano al ramo upstream corrente. M0 deve comunque fissare e testare una versione precisa prima di considerare stabile il contratto applicativo.

## Contratto Bubblewrap verificato

Bubblewrap costruisce un filesystem namespace inizialmente vuoto e rende visibili soltanto i mount dichiarati. Il profilo Pi_UI sfrutta quindi il mount namespace come enforcement del confine filesystem, non come semplice convenzione di path.

Con un root che espone `/usr` senza il root host completo, i normali alias FHS devono essere ricostruiti. La documentazione `mkosi-sandbox` di Arch mostra esplicitamente `/bin → usr/bin`, `/lib → usr/lib`, `/lib64 → usr/lib64` e `/sbin → usr/sbin` nello stesso scenario; Pi_UI replica questa parte nel launch spec.

Riferimenti:

- https://man.archlinux.org/man/bwrap.1.en
- https://man.archlinux.org/man/mkosi-sandbox.1.en

## Politica aggiornamenti e personalizzazione Pi

Pi_UI non incorporerà un fork di Pi come seconda base di codice. Il piano è trattare Pi come runtime gestito e personalizzabile:

1. **Runtime isolato:** configurazione, sessioni e risorse usate da Pi_UI non sovrascrivono l'installazione Pi globale dell'utente.
2. **Nessun auto-update implicito:** all'avvio normale Pi_UI disabilita il check versione upstream. Gli aggiornamenti saranno un'azione visibile della GUI e verranno introdotti solo dopo avere definito verifica compatibilità e rollback.
3. **Impostazioni inferenza:** endpoint LAN, provider/API, model ID, contesto, output e thinking sono proprietà del servizio settings; la GUI modifica queste proprietà, non file Pi in parallelo.
4. **Configurazione Pi derivata:** `models.json` e le altre configurazioni necessarie saranno generate dal runtime manager a partire dallo stato canonico dell'app, dopo aver verificato la baseline locale. Nessun valore Ornith viene inventato dal nome del modello.
5. **Personalizzazioni dalla GUI:** una sezione dedicata mostrerà estensioni, skill, prompt e package disponibili/abilitati. Installazione, rimozione e aggiornamento saranno operazioni esplicite con origine/versione visibili e trust chiaro.
6. **Compatibilità prima dell'aggiornamento:** una nuova versione Pi deve superare test RPC/core e una prova LAN controllata prima di diventare la versione attiva dell'app. La versione precedente deve restare ripristinabile quando il meccanismo di update verrà implementato.

Il ramo corrente implementa isolamento del runtime, controllo degli update check, schema settings e trasporto RPC; non implementa ancora installazione/aggiornamento/rollback di Pi né la GUI di personalizzazione.

## Lavoro M0 ancora aperto

- Inventario reale di versione Pi/package, Node, llama.cpp, model ID, quantizzazione, template, tool/reasoning, context window e parametri usati nella baseline.
- Pin verificato di Pi/Node e conferma della build PySide6 effettivamente usata sulla macchina target.
- Generazione validata della configurazione provider/modello Pi (`models.json`) per il server LAN.
- Timeout di richiesta e inattività sopra il lifecycle del processo; startup/shutdown sono già temporizzati.
- Prove Bubblewrap reali sul desktop target: lettura/scrittura fuori `/workspace`, symlink verso l'esterno, shell/subprocess, HOME reale, socket desktop, processi figli e shutdown.
- Shell QML minimale con connessione, invio, streaming e stop reali; smoke QML e focus/tastiera di base.
- Tre sessioni reali Pi–Ornith, stop, session resume, tool file di prova, errore server e verifica di assenza processi orfani richiesti dal gate M0.

M0 resta quindi **in corso**, non completata.
