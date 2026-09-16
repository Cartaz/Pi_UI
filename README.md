# Pi_UI

Un ambiente desktop personale per ragionare, decidere e lavorare con la propria conoscenza: **Pi Agent come harness, Ornith 1.5 su server LAN e interfaccia Python/PySide6/QML**.

Il prodotto ruota intorno a **un unico spazio di lavoro persistente**. La chat è la prima priorità; accesso, gestione e consultazione dei file vengono subito dopo e fanno parte della prima versione utilizzabile.

## Stato reale

**M0 è stata completata sulla precedente policy di mount; M1 resta attiva.** L'integrazione Pi → Bubblewrap → Ornith è stata verificata sul target CachyOS/Wayland il 9–10 settembre 2026: streaming, stop, tool, ripresa sessione, failure/recovery del server, confinement e shutdown. Sono prove storiche, non un test della nuova policy di sicurezza introdotta dall'audit del 16 settembre. Vedi [M0](docs/M0_PROGRESS.md) e [remediation audit](docs/AUDIT_REMEDIATION.md).

**Hardening temporaneo in verifica:** Bubblewrap è obbligatorio senza percorso diretto alternativo. In assenza di snapshot pre-scrittura, il processo Pi vede il workspace dei documenti in **sola lettura**; soltanto `.pi-agent` rimane scrivibile per sessioni e configurazione. Le modifiche autonome dei documenti via tool, provate in M0, sono ora intenzionalmente bloccate: non verranno ripristinate finché revisioni, conflitti e recovery non saranno verificati. Il nuovo gate sul desktop reale è ancora necessario prima di dichiarare accettata questa modifica.

La GUI QML è operativa. Include chat Pi, scelta di workspace e modello, preflight/sandbox gate, browser lazy dei file, righe compatte con icone e preview documentale read-only. Le letture avvengono fuori dal thread GUI, con accesso descriptor-based che rifiuta traversal e symlink. Preview UTF-8/UTF-8 BOM fino a 1 MiB; binari, encoding non supportati, file non regolari e dimensioni eccessive hanno uno stato esplicito. Il testo sorgente rimane canonico in Python e la copia della selezione preserva CRLF. Il gate grafico reale della preview resta aperto: [issue #27](https://github.com/Cartaz/Pi_UI/issues/27).

Per completare M1 servono ancora importazione e operazioni sui documenti, editor con salvataggio atomico e conflitti, versioni/diff e gestione sicura delle scritture dell'agente. Vedi [stato M1](docs/M1_PROGRESS.md) e [roadmap](ROADMAP.md).

## Obiettivo

Aprire l'app da un'icona, importare materiali di lavoro, conversarci e ricevere risposte da un partner di ragionamento: proposte collegate agli obiettivi, obiezioni motivate, richiamo alle decisioni precedenti e fonti consultabili accanto alla chat. Nell'uso quotidiano non devono servire CLI o VS Code.

Le conoscenze vivono in file locali leggibili anche senza Pi_UI. La memoria non dipende da una conversazione infinita. L'indice di ricerca è ricostruibile; originali, revisioni e decisioni mantengono provenienza e storia quando tali funzioni saranno implementate.

## Documentazione

| Documento | Contenuto |
|---|---|
| [ROADMAP.md](ROADMAP.md) | Milestone, attività, dipendenze e criteri di accettazione |
| [Stato M0](docs/M0_PROGRESS.md) | Evidenze storiche e limiti della milestone Pi–Ornith completata |
| [Stato M1](docs/M1_PROGRESS.md) | Slice GUI/file completati, gate locali e lavoro successivo |
| [Remediation audit](docs/AUDIT_REMEDIATION.md) | Correzioni, regressioni intenzionali e test target ancora obbligatori |
| [Architettura](docs/ARCHITECTURE.md) | Contratti e direzione architetturale; alcune sezioni descrivono ancora moduli futuri |
| [Decisioni](docs/DECISIONS.md) | Scelte, alternative, ADR-020 per la policy temporanea read-only |
| [Validazione](docs/VALIDATION.md) | Scenari funzionali, test, misure e prove locali con Ornith |
| [Fonti](docs/SOURCES.md) | Documentazione primaria consultata e limiti delle verifiche |
| [AGENTS.md](AGENTS.md) | Contratto per chi sviluppa nella repository |

## Scelte di base

- Python 3.12+, PySide6/Qt 6.11+, `QApplication` e `QQmlApplicationEngine`; CI con Python 3.12/3.13/3.14, compileall, pytest, smoke QML e qmllint a zero warning.
- QML nativo, dark neumorphism: superficie `#141414`, accento `#FF6600`, Noto Sans, raggi 28/22/16/12 px.
- Pi locale via RPC; inferenza Ornith 1.5 sul server LAN configurato dall'utente.
- Una sessione agente attiva nella prima versione; la futura gestione first-class dei subagents non va resa strutturalmente difficile.
- Bubblewrap è obbligatorio nel percorso di produzione: no fallback a Pi diretto. Per i documenti vale la policy read-only temporanea descritta sopra.
- Configurazione/sessioni Pi_UI isolate dall'installazione globale; aggiornamenti espliciti, non automatici all'avvio.
- Test con modello reale soltanto nella LAN dell'utente; nessun runner GitHub self-hosted.
- Documenti personali, credenziali e sessioni restano fuori dalla repository del software.

Ornith + Pi è una scelta orientata dai test AIOS-bench dell'utente; la repository non contiene quei risultati e non ne dichiara una riproduzione.

## Prossimo traguardo

Prima chiudere i gate della nuova sandbox e della preview sul desktop target, poi completare M1 senza allargare `AgentController`: file e scritture in servizi/controller dedicati, salvataggi atomici, controllo delle modifiche esterne e snapshot pre-scrittura prima di riabilitare modifiche autonome dei documenti.

## Contribuire

Leggere [AGENTS.md](AGENTS.md) e [AUDIT_REMEDIATION.md](docs/AUDIT_REMEDIATION.md), scegliere un'attività della [roadmap](ROADMAP.md) e aggiornare lo stato solo con evidenze verificabili. I percorsi futuri vengono creati quando nasce la relativa responsabilità, senza scaffold vuoti.

La licenza va scelta dal proprietario prima della distribuzione. Nessun codice dei progetti di riferimento è copiato nella repository.
