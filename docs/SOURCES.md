# Fonti e basi della pianificazione

Consultate l'8 settembre 2026. Le pagine sui branch principali possono cambiare: M0 deve confrontarle con la versione Pi effettivamente fissata. Gli SHA sotto sono **blob SHA dei documenti consultati**, non versioni di release.

## Fonti primarie verificate

| Fonte | Cosa supporta nel piano | Riferimento verificato |
|---|---|---|
| [Pi — RPC Mode](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md) | Integrazione headless, JSONL, comandi/eventi, code, sessioni e protocollo UI estensioni | Blob `d81c23bbf33917d1d319aa7bb460f05639cfb515` |
| [Pi — Custom Models](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md) | Provider personalizzati, API compatibili, model ID, contesto e opzioni compatibilità | Blob `3cf2ad3ea4d35a5b69e11000f2b0202723ab9360` |
| [Pi — Extensions](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md) | Moduli TypeScript, strumenti personalizzati, eventi e interazioni UI | Blob `6cf99171e9d69d871d79749cc3ad22b91abaa4ee` |
| [Pi — Usage](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/usage.md) | File di contesto, sessioni, prompt e project trust, incluso RPC | Blob `88ada91ba9bb8b2630fa75b8f97373a3c395577d` |
| [Pi — llama.cpp](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/llama-cpp.md) | Supporto router nella documentazione attuale; distinto dalla configurazione single-model dell'utente da verificare | Blob `bffa13f423aebaddf228145ddb954db4c4800c19` |
| [Qt for Python — QProcess](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QProcess.html) | Processo figlio, segnali, canali standard e gestione asincrona | Documentazione ufficiale Qt consultata |
| [Qt — RectangularShadow](https://doc.qt.io/qt-6/qml-qtquick-effects-rectangularshadow.html) | Effetto QML nativo per ombre rettangolari e relativo caching | Documentazione Qt 6.11.2 visualizzata |
| [News Aggregator — Theme.qml](https://github.com/Cartaz/News_Aggregator/blob/main/ui/qml/Theme.qml) | Superficie, accento, testi, raggi e font del riferimento visivo | Blob `9a7e16d829d600e4ccffff640374304e4b8db61f` |
| [Nate Herk — AIS-OS AGENTS.md](https://github.com/nateherkai/AIS-OS/blob/main/AGENTS.md) | Ispirazione di prodotto: partner di ragionamento, contesto, riferimenti e registro decisioni | Blob `6695adfb0048ab0a89d36d0d6ccc81dad4b15626` |

## Requisiti dell'utente e scelte progettuali

Il contratto Cartaz QML fornito dall'utente stabilisce architettura, token visivi, Noto Sans, installazione e verifiche. La conversazione stabilisce uno spazio di lavoro, priorità chat/file, uso AI OS e Ornith 1.5 con Pi già scelto dopo AIOS-bench. Questi sono requisiti, non conclusioni ricavate dai benchmark pubblici.

La ripartizione M0–M5, FTS5 come candidato, snapshot/hash, modello dei documenti, strumenti di conoscenza e criteri quantitativi sono **proposte di Pi_UI**. Le fonti dimostrano la disponibilità dei meccanismi upstream citati, non l'esistenza di queste funzioni in Pi_UI.

## Limiti della verifica iniziale

- La repository Pi_UI risultava vuota prima dell'inizializzazione; nessun comportamento applicativo esistente da preservare.
- Non è stato eseguito Ornith, raggiunto il server LAN o riprodotto AIOS-bench in questo ambiente.
- Package/versione Pi, build llama.cpp, ID modello e configurazione effettiva dell'utente restano da rilevare in M0.
- News Aggregator usa Cantarell con fallback Noto Sans; Pi_UI adotta Noto Sans secondo il contratto esplicito attuale. Non è stato svolto un audit completo di News Aggregator.
- Non sono state copiate implementazioni o risorse di terzi; l'eventuale riuso futuro richiede verifica delle relative licenze.
