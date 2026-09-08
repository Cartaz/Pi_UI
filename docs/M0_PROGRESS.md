# M0 — Stato di avanzamento

Aggiornamento: 8 settembre 2026.

Questo documento registra evidenze incrementali della milestone M0 senza dichiarare completati i gate che richiedono la configurazione Pi/Ornith reale sulla LAN.

## Tranche 1 — Fondazione core

Implementato nel ramo `m0/core-foundation`:

- `core/settings.py`: settings tipizzati, percorsi XDG, validazione, scrittura atomica con `fsync`/`os.replace`, preservazione e recupero da file JSON malformato o non compatibile; endpoint e riferimenti a credenziali restano locali.
- `core/agent/protocol.py`: framing RPC JSONL incrementale, delimitatore LF stretto, CRLF tollerato, UTF-8 spezzato tra chunk, più record per lettura, EOF parziale, record non validi e limite massimo per record.
- `core/agent/transport.py`: contratto `AgentTransport` indipendente da Qt con stato processo esplicito. L'implementazione QProcess non è ancora presente.
- `core/agent/runtime.py`: costruzione argv/env senza shell per `pi --mode rpc`, directory Pi e sessioni isolate da quelle globali dell'utente, `PI_SKIP_VERSION_CHECK` controllato dall'app e supporto opzionale a `PI_OFFLINE`.
- `pyproject.toml` e CI GitHub ospitata per compileall e test core su Python 3.12/3.13.

### Verifiche eseguite fuori da GitHub

Ambiente di verifica disponibile in questa sessione: Python 3.13.5.

- `python3 -m compileall -q core tests`: riuscito.
- `python3 -m pytest -q`: 18 test superati.
- `python3 -m pip install -e . --no-build-isolation` e import del package: riusciti.

Queste prove verificano il core Python introdotto, non PySide6/QML, Pi, Node, llama.cpp, Ornith o la connettività LAN.

## Contratto Pi verificato upstream

La documentazione ufficiale corrente di Pi conferma i punti su cui si basa questa tranche:

- RPC per integrazioni non-Node tramite `pi --mode rpc` su stdin/stdout JSONL.
- Framing con LF come unico delimitatore di record; gli ID opzionali correlano comando e risposta.
- La risposta positiva a `prompt` indica accettazione/coda/gestione del comando, non il completamento del turno; gli eventi continuano in modo asincrono.
- `--session-dir` e `PI_CODING_AGENT_SESSION_DIR` permettono di separare le sessioni.
- `PI_CODING_AGENT_DIR` permette di isolare la configurazione Pi usata dall'app.
- `PI_SKIP_VERSION_CHECK` disabilita il check versione all'avvio; `PI_OFFLINE` disabilita le operazioni di rete di startup documentate.
- Pi supporta estensioni, skill, prompt template, temi e package; `pi config` e i package project-local forniscono la base per una futura gestione grafica delle personalizzazioni.

Riferimenti primari:

- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md
- https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md

Questi riferimenti puntano al ramo upstream corrente. M0 deve comunque fissare e testare una versione precisa prima di considerare stabile il contratto applicativo.

## Politica aggiornamenti e personalizzazione Pi

Pi_UI non incorporerà un fork di Pi come seconda base di codice. Il piano è trattare Pi come runtime gestito e personalizzabile:

1. **Runtime isolato:** configurazione, sessioni e risorse usate da Pi_UI non sovrascrivono l'installazione Pi globale dell'utente.
2. **Nessun auto-update implicito:** all'avvio normale Pi_UI disabilita il check versione upstream. Gli aggiornamenti saranno un'azione visibile della GUI e verranno introdotti solo dopo avere definito verifica compatibilità e rollback.
3. **Impostazioni inferenza:** endpoint LAN, provider/API, model ID, contesto, output e thinking saranno proprietà del servizio settings; la GUI modificherà queste proprietà, non file Pi in parallelo.
4. **Configurazione Pi derivata:** `models.json` e le altre configurazioni necessarie saranno generate dal runtime manager a partire dallo stato canonico dell'app, dopo aver verificato la baseline locale. Nessun valore Ornith viene inventato dal nome del modello.
5. **Personalizzazioni dalla GUI:** una sezione dedicata mostrerà estensioni, skill, prompt e package disponibili/abilitati. Installazione, rimozione e aggiornamento saranno operazioni esplicite con origine/versione visibili e trust chiaro.
6. **Compatibilità prima dell'aggiornamento:** una nuova versione Pi deve superare test RPC/core e una prova LAN controllata prima di diventare la versione attiva dell'app. La versione precedente deve restare ripristinabile quando il meccanismo di update verrà implementato.

La tranche corrente implementa soltanto isolamento del launch spec e controllo degli update check; non implementa ancora installazione/aggiornamento/rollback di Pi né la GUI di personalizzazione.

## Lavoro M0 ancora aperto

- Inventario reale di versione Pi/package, Node, llama.cpp, model ID, quantizzazione, template, tool/reasoning, context window e parametri usati nella baseline.
- Pin verificato di Python/PySide6 e Pi/Node.
- Migrazioni reali dello schema settings quando esisterà una versione precedente da migrare.
- Generazione validata della configurazione provider/modello Pi per il server LAN.
- Implementazione QProcess asincrona in `ui/native`, stdout/stderr separati e shutdown deterministico.
- Correlazione richieste, stato turno, timeout, prompt/steer/follow-up, `clear_queue` + `abort` e gestione degli errori successivi all'accettazione.
- Shell QML minimale con connessione/invio/stop reali.
- Smoke QML e verifiche PySide6.
- Prove reali LAN richieste dal gate M0 e report delle versioni effettive.

M0 resta quindi **in corso**, non completata.
