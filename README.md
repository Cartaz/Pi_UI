# Pi_UI

Un ambiente desktop personale per ragionare, decidere e lavorare con la propria conoscenza: **Pi Agent come harness, Ornith 1.5 su server LAN e interfaccia Python/PySide6/QML**.

Il prodotto ruota intorno a **un unico spazio di lavoro persistente**. La chat è la prima priorità; accesso, gestione e consultazione dei file vengono subito dopo e fanno parte della prima versione utilizzabile.

## Stato reale

**M0 è completata e M1 è attiva.** L'integrazione reale Pi → Bubblewrap → Ornith è stata verificata sul target CachyOS/Wayland: streaming, stop, tool, ripresa sessione, failure/recovery del server, confinement e shutdown sono stati provati senza dichiarare evidenze non osservate. I dettagli restano in [docs/M0_PROGRESS.md](docs/M0_PROGRESS.md).

La GUI QML è operativa. Oggi include la chat Pi, selezione del workspace e del profilo modello, preflight/sandbox gate, albero lazy dei file del workspace, righe compatte con icone e un'anteprima documenti read-only. Le letture dei file avvengono fuori dal thread GUI e usano accesso descriptor-based che rifiuta traversal e symlink. La preview M1 supporta UTF-8/UTF-8 BOM entro 1 MiB; binari, encoding non supportati, file non regolari e file troppo grandi hanno stato esplicito. Il testo sorgente resta canonico in Python; la copia dalla preview rimappa la selezione Qt sul testo originale per non perdere CRLF.

Il lavoro M1 successivo riguarda la gestione documentale vera e propria: importazione, creazione/rinomina/spostamento, editor con salvataggio atomico e conflitti, revisioni/diff e gestione sicura delle scritture agente. Vedi [stato M1](docs/M1_PROGRESS.md) e [roadmap](ROADMAP.md).

## Obiettivo

Aprire l'app da un'icona, importare materiali di lavoro, conversarci e ricevere risposte da un partner di ragionamento: proposte collegate agli obiettivi, obiezioni motivate, richiamo alle decisioni precedenti e fonti consultabili accanto alla chat. Nell'uso quotidiano non devono servire CLI o VS Code.

Le conoscenze vivono in file locali leggibili anche senza Pi_UI. La memoria non dipende da una conversazione infinita. L'indice di ricerca è ricostruibile; originali, revisioni e decisioni mantengono provenienza e storia.

## Documentazione

| Documento | Contenuto |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Milestone, attività, dipendenze e criteri di accettazione |
| [Stato M0](docs/M0_PROGRESS.md) | Evidenze e limiti della milestone Pi–Ornith completata |
| [Stato M1](docs/M1_PROGRESS.md) | Slice GUI/file completati, gate locali e lavoro successivo |
| [Architettura](docs/ARCHITECTURE.md) | Confini dei moduli, proprietà dello stato, integrazione Pi, persistenza e UI |
| [Decisioni iniziali](docs/DECISIONS.md) | Scelte, alternative e questioni da verificare |
| [Validazione](docs/VALIDATION.md) | Scenari funzionali, test, misure e prove locali con Ornith |
| [Fonti](docs/SOURCES.md) | Documentazione primaria consultata e limiti delle verifiche |
| [AGENTS.md](AGENTS.md) | Contratto per chi sviluppa nella repository |

## Scelte di base

- Python 3.12+, PySide6/Qt 6.11+, `QApplication` e `QQmlApplicationEngine`; la CI corrente copre Python 3.12/3.13/3.14 con compileall, pytest, smoke QML e `qmllint` a zero warning.
- QML nativo, dark neumorphism: superficie `#141414`, accento `#FF6600`, **Noto Sans**, raggi 28/22/16/12 px.
- Pi eseguito localmente in background tramite RPC; inferenza Ornith 1.5 sul server LAN configurato dall'utente.
- Una sola sessione agente attiva nella prima versione; l'architettura non deve rendere strutturalmente difficile la futura gestione first-class dei subagents.
- Pi è confinato con Bubblewrap sul target Linux; la sandbox è obbligatoria nel percorso di produzione e non esiste fallback silenzioso al lancio diretto.
- Configurazione/sessioni Pi usate da Pi_UI sono isolate dall'installazione globale; aggiornamenti Pi espliciti e gestiti, non automatici all'avvio.
- Test con modello reale esclusivamente nella LAN dell'utente; nessun runner GitHub self-hosted.
- Documenti personali, credenziali e sessioni rimangono fuori dalla repository del software.

Ornith + Pi è una scelta già validata dall'utente nei propri test AIOS-bench; questa repository non contiene quei risultati e non ne dichiara una riproduzione.

## Prossimo traguardo

Chiudere il gate reale della preview documenti sul desktop target e poi proseguire M1 senza allargare `AgentController`: gestione documenti e scritture devono restare in servizi/controller dedicati, con salvataggi atomici, controllo delle modifiche esterne e versionamento prima di consentire scritture autonome dell'agente.

## Contribuire

Leggere [AGENTS.md](AGENTS.md), scegliere un'attività della [roadmap](ROADMAP.md) e aggiornare lo stato solo con evidenze verificabili. I percorsi di codice descritti nell'architettura vengono creati quando nasce la relativa responsabilità; non si aggiunge scaffold vuoto.

La licenza del progetto è da scegliere dal proprietario prima della distribuzione. Nessun codice dei progetti di riferimento è copiato nella repository.
