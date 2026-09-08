# Pi_UI

Un ambiente desktop personale per ragionare, decidere e lavorare con la propria conoscenza: **Pi Agent come harness, Ornith 1.5 su server LAN e interfaccia Python/PySide6/QML**.

Il prodotto ruota intorno a **un unico spazio di lavoro persistente**, con più conversazioni. La chat è la prima priorità; accesso, gestione e consultazione dei file vengono subito dopo e fanno parte della prima versione utilizzabile.

## Stato reale

M0 è **in corso**. La repository contiene ora la fondazione del runtime: settings tipizzati/atomici con migrazione di schema, framing JSONL Pi RPC, correlazione delle richieste, stato del turno, stop `clear_queue → abort`, launch spec Bubblewrap e trasporto PySide6 `QProcess` asincrono con stdout/stderr separati e shutdown temporizzato.

Su Linux il percorso previsto è GUI → QProcess → Bubblewrap → Pi. La sandbox monta l'AIOS root come unico albero dati personale read-write, usa il runtime Pi read-only e non eredita automaticamente HOME reale, DISPLAY, SSH agent o altri socket desktop. La rete host resta condivisa perché Pi deve raggiungere Ornith in LAN e, quando necessario, Internet.

**La GUI QML non è ancora implementata** e non è ancora stata eseguita dalla repository una prova reale Bubblewrap + Pi + Ornith sulla macchina target. Nessuna parte di M0 che richiede quella baseline locale viene dichiarata completata senza verifica. Vedi [stato M0](docs/M0_PROGRESS.md).

## Obiettivo

Aprire l'app da un'icona, importare materiali di lavoro, conversarci e ricevere risposte da un partner di ragionamento: proposte collegate agli obiettivi, obiezioni motivate, richiamo alle decisioni precedenti e fonti consultabili accanto alla chat. Nell'uso quotidiano non devono servire CLI o VS Code.

Le conoscenze vivono in file locali leggibili anche senza Pi_UI. La memoria non dipende da una conversazione infinita. L'indice di ricerca è ricostruibile; originali, revisioni e decisioni mantengono provenienza e storia.

## Documentazione

| Documento | Contenuto |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Milestone, attività, dipendenze, criteri di accettazione, rischi e prima sequenza di lavoro |
| [Stato M0](docs/M0_PROGRESS.md) | Evidenze del lavoro corrente, verifiche eseguite e parti ancora aperte |
| [Architettura](docs/ARCHITECTURE.md) | Confini dei moduli, proprietà dello stato, integrazione Pi, persistenza e UI |
| [Decisioni iniziali](docs/DECISIONS.md) | Scelte, alternative e questioni da verificare |
| [Validazione](docs/VALIDATION.md) | Scenari funzionali, test, misure e prove locali con Ornith |
| [Fonti](docs/SOURCES.md) | Documentazione primaria consultata e limiti delle verifiche |
| [AGENTS.md](AGENTS.md) | Contratto per chi sviluppa nella repository |

## Scelte di base

- Python 3.12+, PySide6/Qt 6.11+, QApplication e QQmlApplicationEngine; il ramo M0 testa attualmente Python 3.12/3.13 e PySide6 6.11+ in CI.
- QML nativo, dark neumorphism: superficie `#141414`, accento `#FF6600`, **Noto Sans**, raggi 28/22/16/12 px.
- Pi eseguito localmente in background tramite RPC; inferenza Ornith 1.5 sul server LAN configurato dall'utente.
- Una sola sessione agente attiva nella prima versione; molte conversazioni sullo stesso archivio.
- Pi è confinato con Bubblewrap sul target Linux; la sandbox è obbligatoria nel percorso di produzione e un lancio diretto resta soltanto una modalità esplicita per test/diagnostica, mai un fallback silenzioso.
- Configurazione/sessioni Pi usate da Pi_UI sono isolate dall'installazione globale; aggiornamenti Pi espliciti e gestiti dall'app, non automatici all'avvio.
- Test con modello reale esclusivamente nella LAN dell'utente; nessun runner GitHub self-hosted.
- Documenti personali, credenziali e sessioni rimangono fuori dalla repository del software.

Ornith + Pi è una scelta già validata dall'utente nei propri test AIOS-bench; questa repository non contiene quei risultati e non ne dichiara una riproduzione. Il progetto prende ispirazione dall'AI OS di Nate Herk e dal linguaggio visivo di News Aggregator; i riferimenti verificati sono in [Fonti](docs/SOURCES.md).

## Prossimo traguardo

Completare la parte restante di **M0**: fissare la baseline locale effettiva, generare la configurazione Pi derivata per il server LAN, verificare il confinement Bubblewrap sulla macchina target, aggiungere i timeout di richiesta/inattività e collegare una shell QML minima a invio/streaming/stop reali. Solo dopo le prove Pi–Ornith si passa alla GUI M1 estesa per chat e file.

## Contribuire

Leggere [AGENTS.md](AGENTS.md), scegliere un'attività della [roadmap](ROADMAP.md) e aggiornare lo stato solo con evidenze verificabili. I percorsi di codice descritti nell'architettura vengono creati quando nasce la relativa responsabilità; non si aggiunge scaffold vuoto.

La licenza del progetto è da scegliere dal proprietario prima della distribuzione. Nessun codice dei progetti di riferimento è copiato nella repository.
