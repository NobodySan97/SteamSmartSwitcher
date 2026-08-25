# 🎮 Steam Smart Account Switcher & Game Launcher

<div align="center">

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python)
![Release](https://img.shields.io/badge/Release-v1.0.0-5c7e10.svg)

**Lo switcher di account Steam intelligente: crea icone sul Desktop che cambiano account ed avviano il gioco in 1 solo click.**

[Caratteristiche](#-caratteristiche-principali) •
[Installazione](#-installazione--download) •
[Come Funziona](#-come-funziona) •
[Compilazione](#-compilazione-da-sorgente) •
[Scorciatoie](#-scorciatoie-da-tastiera)

</div>

---

## 🌟 Caratteristiche Principali

- ⚡ **Switch Automatico con Scorciatoia Desktop**: Fai doppio click sull'icona del gioco sul Desktop: se non sei loggato con l'account giusto, Steam viene riavviato e loggato automaticamente senza chiederti la password, avviando subito la partita.
- 📦 **Tutto in un Singolo File Eseguibile (`.exe`)**: Zero installazioni complesse. L'app funziona come interfaccia grafica completa se aperta normalmente, o come launcher istantaneo da riga di comando se chiamata dalle scorciatoie.
- 🎨 **Interfaccia Dark Steam con Cover e Avatar Reali**: Riconosce i tuoi account, scarica e mostra gli avatar della community Steam e le copertine ufficiali in formato poster verticale o vista a elenco dettagliata.
- 👑 **Riconoscimento Licenze & 👨‍👩‍👧‍👦 Family Sharing**: Riconosce all'istante se un gioco appartiene al profilo selezionato o se proviene dal Family Sharing di un altro account sul PC.
- 🔔 **Integrazione Barra delle Applicazioni (System Tray)**: Minimizza l'app vicino all'orologio di Windows, con menu contestuale con tasto destro per cambiare account o lanciare giochi al volo.
- ⚙️ **Opzioni di Avvio Personalizzate per Account**: Imposta parametri di lancio personalizzati (es. `-novid -high +exec smurf.cfg`) memorizzati per singolo account.
- 🛡️ **Protezione Partite in Corso & Salvataggi Cloud**: Blocca il cambio account accidentale se un gioco Steam è aperto, proteggendo da crash e perdite di dati.
- 🔄 **Sistema di Auto-Update Integrato**: Notifica e scarica gli aggiornamenti direttamente dalle release di GitHub con 1 click.

---

## 📥 Installazione & Download

1. Scarica l'ultima versione di **`SteamSmartSwitcher.exe`** dalla [sezione Releases di GitHub](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest).
2. Salva il file in una cartella a tua scelta (es. `C:\Programmi\SteamSmartLauncher` o nei tuoi Documenti).
3. Avvia `SteamSmartSwitcher.exe`.

> [!TIP]
> Per avviare l'app automaticamente all'accensione del PC, apri le **Impostazioni ⚙️** nell'app e attiva la spunta *"Avvia automaticamente con Windows"*.

---

## 🕹️ Come Funziona

```
                    [ Doppio Click su Scorciatoia Gioco ]
                                      │
                                      ▼
                        [ SteamSmartSwitcher.exe ]
                                      │
                     Hai già l'account giusto loggato?
                                ╱           ╲
                           SÌ  ╱             ╲  NO
                              ╱               ╲
                             ▼                 ▼
                     Avvia il gioco     1. Chiudi Steam in sicurezza
                                        2. Applica Registry & VDF
                                        3. Riavvia Steam con l'account corretto
                                        4. Lancia la partita!
```

---

## ⌨️ Scorciatoie da Tastiera

| Tasto | Azione |
|---|---|
| `Ctrl + F` o `/` | Cerca rapidamente un gioco |
| `Invio (Enter)` | Avvia il gioco selezionato |
| `Esc` | Pulisce la ricerca o riduce a icona |
| `F5` o `Ctrl + R` | Ricarica e scansiona account e libreria |
| `Ctrl + ,` | Apre le Impostazioni |

---

## 🛠️ Compilazione da Sorgente

Se vuoi compilare autonomamente l'eseguibile:

```bash
# 1. Clona il repository
git clone https://github.com/NobodySan97/SteamSmartSwitcher.git
cd SteamSmartSwitcher

# 2. Installa le dipendenze
pip install -r requirements.txt

# 3. Compila in singolo eseguibile standalone
python -m PyInstaller --noconsole --onefile --name="SteamSmartSwitcher" --icon="C:\Program Files (x86)\Steam\Steam.exe" --clean main.py
```

L'eseguibile pronto si troverà nella cartella `dist/SteamSmartSwitcher.exe`.

---

## 📄 Licenza

Distribuito sotto licenza **MIT**. Consulta il file [`LICENSE`](LICENSE) per ulteriori dettagli.
