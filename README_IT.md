# 🎮 Steam Smart Account Switcher & Game Launcher

<div align="center">

[![GitHub Release](https://img.shields.io/github/v/release/NobodySan97/SteamSmartSwitcher?style=flat-square&color=66c0f4)](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest)
[![Download Totali](https://img.shields.io/github/downloads/NobodySan97/SteamSmartSwitcher/total.svg?style=flat-square&logo=github&color=5c7e10)](https://github.com/NobodySan97/SteamSmartSwitcher/releases)
[![Download Ultima Release](https://img.shields.io/github/downloads/NobodySan97/SteamSmartSwitcher/latest/total.svg?style=flat-square&logo=github&color=66c0f4)](https://github.com/NobodySan97/SteamSmartSwitcher/releases/latest)
[![Licenza](https://img.shields.io/badge/Licenza-MIT-blue.svg?style=flat-square)](LICENSE)
[![Piattaforma](https://img.shields.io/badge/Piattaforma-Windows%2010%20%7C%2011-0078D6.svg?style=flat-square&logo=windows)](https://github.com/NobodySan97/SteamSmartSwitcher)

**Lo switcher di account Steam intelligente: crea icone sul Desktop che cambiano account ed avviano il gioco in 1 solo click.**

---

### 🌐 Lingua / Language
[🇬🇧 Read documentation in English](README.md) • **Italiano**

---

> [!WARNING]
> **Progetto in Fase di Sviluppo (Work In Progress) — Non Ancora Testato**  
> Questo software è attualmente in **fase di sviluppo iniziale e non è stato ancora testato a fondo** su differenti sistemi operativi, configurazioni hardware o account Steam multipli. Potrebbero verificarsi bug o comportamenti inattesi. Usalo a tua discrezione e sentiti libero di aprire una Issue per segnalare problemi o suggerimenti!

---

</div>

## 🌟 Caratteristiche Principali

- ⚡ **Switch Automatico con Scorciatoia Desktop**: Fai doppio click sull'icona del gioco sul Desktop: se non sei loggato con l'account giusto, Steam viene riavviato e loggato automaticamente senza chiederti la password, avviando subito la partita.
- 📦 **Tutto in un Singolo File Eseguibile (`.exe`)**: Zero configurazioni esterne. L'app funziona come interfaccia grafica completa se aperta normalmente, o come launcher istantaneo da riga di comando (<15ms) se chiamata dalle scorciatoie.
- 🎨 **Interfaccia Dark Steam con Cover e Avatar Reali**: Riconosce i tuoi account, scarica e mostra gli avatar della community Steam e le copertine ufficiali in formato poster verticale o vista a elenco dettagliata.
- ⭐ **Sistema di Preferiti & Ordinamento Avanzato**: Aggiungi i tuoi giochi preferiti in cima con una stellina (⭐) e ordina all'istante per *Preferiti*, *Nome (A-Z)*, *Ultima sessione* o *Spazio su disco (GB)*.
- 🌈 **5 Temi Grafici Personalizzabili**: Personalizza l'aspetto dell'applicazione scegliendo tra **Steam Dark**, **OLED Pure Black** (nero assoluto a 0-nit per display OLED), **Cyberpunk Neon**, **Midnight Blue** o **Nordic Forest**.
- 🍃 **Consumi Ultra Ridotti (<10 MB RAM & 0.0% CPU)**: Grazie all'ottimizzazione nativa Windows del working set alla riduzione a icona nel tray, l'impatto sui giochi e sulle risorse del PC è praticamente nullo.
- 👑 **Riconoscimento Licenze & 👨‍👩‍👧‍👦 Family Sharing**: Riconosce all'istante se un gioco appartiene al profilo selezionato o se proviene dal Family Sharing di un altro account presente sul PC.
- 🔔 **Integrazione Barra delle Applicazioni (System Tray)**: Minimizza l'app vicino all'orologio di Windows, con menu contestuale con tasto destro per cambiare account o lanciare giochi al volo.
- ⚙️ **Opzioni di Avvio Personalizzate per Account**: Imposta parametri di lancio personalizzati (es. `-novid -high +exec smurf.cfg`) memorizzati per singolo account.
- 🛡️ **Protezione Partite in Corso & Salvataggi Cloud**: Blocca il cambio account accidentale se un gioco Steam è aperto, proteggendo da crash e perdite di dati.
- 🌍 **Supporto Multilingua**: Interfaccia completamente bilingue con supporto per **Italiano** e **Inglese**.
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
