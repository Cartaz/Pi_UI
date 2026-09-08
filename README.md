# Pi_UI

Un ambiente desktop personale per ragionare, decidere e lavorare con la propria conoscenza: **Pi Agent come harness, Ornith 1.5 su server LAN e interfaccia Python/PySide6/QML**.

Il prodotto ruota intorno a **un unico spazio di lavoro persistente**, con più conversazioni. La chat è la prima priorità; accesso, gestione e consultazione dei file vengono subito dopo e fanno parte della prima versione utilizzabile.

## Stato reale

Repository inizializzata con documentazione di progetto. **L'applicazione non è ancora implementata**: non sono presenti launcher, installer, collegamento LAN o test applicativi. Le milestone M0–M5 sono da realizzare; le checklist nella roadmap indicano lavoro futuro.

## Obiettivo

Aprire l'app da un'icona, importare materiali di lavoro, conversarci e ricevere risposte da un partner di ragionamento: proposte collegate agli obiettivi, obiezioni motivate, richiamo alle decisioni precedenti e fonti consultabili accanto alla chat. Nell'uso quotidiano non devono servire CLI o VS Code.

Le conoscenze vivono in file locali leggibili anche senza Pi_UI. La memoria non dipende da una conversazione infinita. L'indice di ricerca è ricostruibile; originali, revisioni e decisioni mantengono provenienza e storia.

## Documentazione

| Documento | Contenuto |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Milestone, attività, dipendenze, criteri di accettazione, rischi e prima sequenza di lavoro |
| [Architettura](docs/ARCHITECTURE.md) | Confini dei moduli, proprietà dello stato, integrazione Pi, persistenza e UI |
| [Decisioni iniziali](docs/DECISIONS.md) | Scelte, alternative e questioni da verificare |
| [Validazione](docs/VALIDATION.md) | Scenari funzionali, test, misure e prove locali con Ornith |
| [Fonti](docs/SOURCES.md) | Documentazione primaria consultata e limiti delle verifiche |
| [AGENTS.md](AGENTS.md) | Contratto per chi sviluppa nella repository |

## Scelte di base

- Python 3.12+, PySide6/Qt 6.11+, QApplication e QQmlApplicationEngine; versioni esatte da fissare e verificare in M0.
- QML nativo, dark neumorphism: superficie `#141414`, accento `#FF6600`, **Noto Sans**, raggi 28/22/16/12 px.
- Pi eseguito localmente in background tramite RPC; inferenza Ornith 1.5 sul server LAN configurato dall'utente.
- Una sola sessione agente attiva nella prima versione; molte conversazioni sullo stesso archivio.
- Test con modello reale esclusivamente nella LAN dell'utente; nessun runner GitHub self-hosted.
- Documenti personali, credenziali e sessioni rimangono fuori dalla repository del software.

Ornith + Pi è una scelta già validata dall'utente nei propri test AIOS-bench; questa repository non contiene quei risultati e non ne dichiara una riproduzione. Il progetto prende ispirazione dall'AI OS di Nate Herk e dal linguaggio visivo di News Aggregator; i riferimenti verificati sono in [Fonti](docs/SOURCES.md).

## Prossimo traguardo

**M0: riprodurre il collegamento Pi–Ornith nella nuova integrazione**, mantenendo la configurazione che funziona già e documentando versioni, protocollo, streaming, stop, salvataggio e chiusura dei processi. Segue M1, che rende realmente utilizzabili chat e file insieme.

## Contribuire

Leggere [AGENTS.md](AGENTS.md), scegliere un'attività della [roadmap](ROADMAP.md) e aggiornarne lo stato solo con evidenze verificabili. I percorsi di codice descritti nell'architettura sono proposti: crearli quando viene implementata la relativa responsabilità.

La licenza del progetto è da scegliere dal proprietario prima della distribuzione. Nessun codice dei progetti di riferimento è copiato in questa inizializzazione.
