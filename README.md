# Guess the Player from the Path

Bot Telegram che ogni giorno propone il percorso professionale (misterioso) di un calciatore
da indovinare, con classifiche, statistiche personali, eventi tematici a tempo e trofei.

> **Licenza:** PolyForm Noncommercial 1.0.0 — libero per studio, hobby e uso personale,
> **vietato qualsiasi uso commerciale**. Vedi [Licenza e uso](#licenza-e-uso).

## Come si gioca

### Transizione alla mini app Telegram

Con `PUBLIC_BASE_URL` configurato, `/start`, `/menu` e `/help` invitano ad aprire
la mini app nelle chat private. `/app` registra anche chi arriva per la prima volta
e mostra il pulsante per giocare; all'avvio il bot configura inoltre il pulsante
fisso **Play** di Telegram. Le notifiche giornaliere degli utenti che le hanno
attivate includono lo stesso accesso diretto. I testi sono disponibili in IT/ES/EN.

Il centro **Gioca** della mini app include allenamento, eventi e duelli tra amici,
con interfaccia responsive e testi IT/ES/EN. Profilo e progressi sono condivisi tra
chat e mini app; i round nei gruppi restano accessibili dal bot. Senza URL
configurato, gli inviti alla mini app non compaiono.
Le modifiche diventano operative al deploy e al successivo avvio del servizio.

### Allenamento, amici ed eventi nella mini app

- **Allenamento:** cinque tentativi, confronto dopo un errore, soluzione a fine
  partita o su richiesta e pulsante per il prossimo percorso. La sessione della
  mini app si riprende riaprendo Allenamento, senza cambiare quella aperta in chat.
  I calciatori vengono dal pool riservato o da giornate passate; non si guadagnano
  punti, ma gli indovinati contribuiscono ai traguardi di allenamento.
- **Sfida un amico:** cinque percorsi identici, tre tentativi per percorso e due
  posti. Vince chi indovina più percorsi; a parità contano meno tentativi (un
  percorso perso ne conta tre). La partita è asincrona, senza punti nella
  classifica generale. Il pulsante Aggiorna recupera i progressi dell'avversario;
  il confronto dei punteggi appare quando entrambi hanno finito. Il centro Gioca
  riprende l'ultimo duello; un invito permette di riaprire anche quello precedente.
  Gli inviti durano sette giorni e richiedono `BOT_USERNAME` e `PUBLIC_BASE_URL`.
  Il link `/start duel_<codice>` registra anche un nuovo utente e gli presenta
  il pulsante per aprire la partita nella mini app. Nessun messaggio è inviato
  automaticamente agli amici.
- **Eventi settimanali:** il centro mostra gli eventi attivi secondo il calendario
  esistente, con descrizioni tradotte, scadenza, sfida e classifica. Supporta i tipi
  `path`, `transfer_guess`, `career` e `father_son`; tentativi, punti e bonus sono
  condivisi con il bot. Non modifica la programmazione degli eventi.

L'endpoint `/app/api/arena` richiede la stessa firma Telegram degli altri endpoint.
Le mosse di allenamento e duello controllano una revisione in transazione; gli
eventi verificano giornata e numero di tentativi. Le soluzioni dei duelli si
mostrano nel riepilogo solo dopo che entrambi hanno finito; gli alias accettati
non vengono inviati al client. I duelli sono salvati in
`app_duels`; `/forgetme DELETE` elimina anche i duelli a cui l'utente partecipa.
La scadenza viene applicata dall'applicazione; per rimuovere automaticamente i
documenti scaduti si può configurare il TTL Firestore sul campo `expires_at`.

L'anteprima `python scripts/preview_webapp.py` include le nuove modalità con
partite dimostrative in memoria. Non invia inviti reali né usa Firestore.

Ogni giorno il bot pubblica il percorso di carriera di un calciatore, senza il nome. In chat
privata **basta scrivere il nome**: non serve nessun comando (`/guess <nome>` continua a
funzionare). Tre tentativi al giorno, i punti dipendono dalla difficolta', chi indovina per
primo prende un punto in piu'. Dopo un tentativo sbagliato si puo' chiedere un **indizio**, che
costa un punto. Chi non ci arriva scopre chi era a mezzanotte, o con `/solution` a giornata
chiusa.

Si gioca in due posti, con le stesse identiche regole: la **chat del bot** e la **mini app**
(`webapp/index.html`), che aggiunge il completamento automatico sui nomi e il calendario delle
giornate passate. Le regole stanno in un modulo solo (`services/game.py`), quindi non esistono
due versioni del punteggio da tenere allineate.

| Comando | Cosa fa |
|---|---|
| `/start` | registrazione e menu; apre anche i link d'invito alle leghe |
| `/menu` | la tastiera con tutto quello che si puo' fare |
| `/show` | la sfida di oggi |
| `/solution` (`/soluzione`) | chi era il calciatore di una giornata gia' chiusa |
| `/guess <risposta>` | il modo classico di rispondere |
| `/stats` | punti, striscia, trofei |
| `/top` | classifica generale e mensile |
| `/events` | centro eventi |
| `/archive` (`/archivio`) | rigioca le sfide dei giorni scorsi |
| `/training` (`/allenamento`) | sfide a raffica, senza punti |
| `/round` (`/sfida`) | **in un gruppo**: apre un round per tutti |
| `/standings` (`/classifica`) | **in un gruppo**: la classifica di quel gruppo |
| `/today` (`/oggi`) | esci dall'archivio, dall'allenamento o da un evento |
| `/league` (`/lega`) | le tue leghe private |
| `/league_create <nome>`, `/league_join <codice>`, `/league_leave <codice>` | crea, entra, esci |
| `/forgetme` | cancella definitivamente account e dati di gioco, con conferma |
| `/paysupport <messaggio>` | apre una richiesta di assistenza per un acquisto |
| `/shop` (`/negozio`) | skin, cornici, titoli e distintivi con le Stelle di Telegram |
| `/legend` (`/legenda`) | come si legge l'immagine del percorso |
| `/notify`, `/language` | notifiche e lingua |

Il menu "/" di Telegram (`set_my_commands`) viene impostato all'avvio nelle tre lingue: le
**descrizioni** sono tradotte, i **nomi dei comandi** no — sono in inglese per tutti. Un bot
trilingue con tre serie di comandi diversi obbligherebbe a scrivere ogni messaggio in tre
versioni ("torna a oggi con /oggi" per un italiano, "con /today" per un inglese), e chi cambia
lingua si ritroverebbe i comandi che ha imparato a non funzionare più. Gli alias italiani della
prima versione (`/archivio`, `/oggi`, `/lega`, `/lega_crea`, `/allenamento`, `/sfida`,
`/classifica`, `/legenda`) restano registrati e funzionanti: semplicemente non sono più quelli
che il bot suggerisce.

### Risposte tollerate, ma non regalate

Il confronto passa da `services/matching.py`: accenti, maiuscole, punteggiatura e apostrofi
non contano ("Mbappe" = "Mbappé", "N'Golo" = "Ngolo"), e un refuso vicino alla risposta viene
accettato invece di bruciare un tentativo. La soglia e' alta e c'e' un limite sulla differenza
di lunghezza, perche' il caso da non sbagliare mai e' accettare *ronaldinho* per *ronaldo*:
i test lo verificano su una lista di coppie insidiose. Non viene mai suggerito il nome giusto
("intendevi X?"): sarebbe rivelare la soluzione.

Un messaggio che non ha la forma di un nome (un link, una frase lunga) non consuma tentativi:
il bot risponde con una riga di spiegazione.

### Cosa lascia un tentativo sbagliato

Prima non lasciava niente ("sbagliato, te ne restano due"): su una giornata difficile
l'unica strategia possibile era sparare nomi. Adesso, se il calciatore scritto e' nel
dataset, `services/guess_feedback.py` lo confronta con la soluzione e risponde come Wordle:

```
❌ Risposta sbagliata, riprova! Tentativi rimasti: 2.

🔎 Rispetto a Alessandro Del Piero:
🌍 Nazionalità: diversa
🎽 Ruolo: stesso
⬇️ Più giovane: nato dopo il 1974

                        [ 💡 Indizio (-1 punto) ]
```

Il confronto e' **relativo al nome scritto dall'utente**, e questo decide due cose. La
prima: non c'e' niente da tradurre (chi ha scritto "Del Piero" sa gia' di che nazionalita'
e ruolo sia), quindi il blocco funziona uguale nelle tre lingue senza tradurre 53 paesi. La
seconda: le squadre **non** si confrontano mai. Sono gia' tutte nell'immagine — dirle
sarebbe ripetere quello che si vede — e le informazioni che l'immagine non da' sono
esattamente nazionalita', ruolo ed eta'.

Il nome tentato viene risolto sul dataset con la stessa tolleranza ai refusi delle risposte,
e il blocco riporta in testa la scheda che il bot ha capito: e' l'unico modo che ha l'utente
di accorgersi che "Ronaldo" e' stato inteso come un altro Ronaldo. Se il nome non e' nel
dataset — o se la sfida e' cosi' vecchia da non avere `player_id` — il confronto non c'e' e
il messaggio resta quello di prima. Chi volesse usarlo come oracolo ("questo calciatore e'
nel dataset?") ha tre tentativi al giorno per farlo, che e' un prezzo abbastanza alto da
rendere la cosa inutile.

Lo stesso confronto vale nell'archivio, nell'allenamento, nei round di gruppo e negli eventi in
cui si indovina un calciatore (`path` e `transfer_guess`): recuperare una sfida passata non deve
essere piu' difficile del gioco vero. Negli eventi `career` e `father_son` non c'e', perche' li'
non si risponde con un calciatore ma con delle squadre o con una coppia padre/figlio.

### Indizi, e perche' costano

Il confronto qui sopra e' **relativo**: dice "stessa nazionalita'" rispetto al nome scritto, e
quindi non serve a chi non ha idee. L'indizio (`services/hints.py`) e' **assoluto** — dice la
nazionalita' e basta — ed e' per questo che costa un punto. Tre regole tengono in piedi
l'equilibrio:

1. si sbloccano **dopo un tentativo sbagliato**. Senza, sarebbero il modo piu' comodo per farsi
   dire nazionalita' e ruolo di ogni sfida senza mai giocarla, e toglierebbero valore a chi la
   prende al primo colpo;
2. costano **1 punto l'uno con il pavimento a 1**: chi indovina dopo due indizi su una sfida
   "easy" (che ne vale 1) prende comunque il suo punto. Non si va mai sotto;
3. sono **due**, e sono nazionalita' e ruolo. La scala e' un dato (`HINT_LADDER`), quindi
   allungarla e' una riga — ma vuol dire anche rendere piu' facile ogni sfida difficile, che e'
   una scelta di gioco e non un dettaglio tecnico.

Gli indizi si pagano **solo se si indovina**: su una sfida persa non c'era niente da togliere.
E si vedono nella card condivisa (una 💡 per indizio): due "1/3" identici non sono la stessa
partita se uno dei due si e' fatto aiutare.

### Chi era? (`/solution`)

Prima la risposta della sfida del giorno si scopriva in un modo solo: il messaggio di
mezzanotte, che pero' arriva **solo a chi ha le notifiche attive**. Chi non le aveva, e aveva
finito i tre tentativi, non lo sapeva mai — a meno di riaprire quel giorno in archivio e
sbagliare di nuovo tre volte. Tre tentativi buttati e nessuna risposta e' il modo piu' rapido
per smettere di giocare.

`/solution` mostra la soluzione di **qualsiasi giornata gia' chiusa** (senza argomenti: ieri),
con il percorso, la difficolta' e la percentuale di chi l'ha indovinata. La giornata di oggi non
si rivela mai: sarebbe incollabile in un gruppo dieci minuti dopo la mezzanotte. Per lo stesso
motivo, dopo l'ultimo tentativo sbagliato il bot non dice il nome ma offre un bottone
"🔔 Avvisami a mezzanotte", che e' il modo in cui quella frase diventa vera per chi le notifiche
non le ha.

La percentuale (`services/daily_stats.py`) e' l'unico numero del gioco che parla della **sfida**
invece che del giocatore: "3/3" da solo non dice se la giornata era dura, "l'ha indovinato il
12%" si'. Compare a giornata chiusa e mai prima — durante la giornata direbbe a chi non ha
ancora giocato quanto e' facile la sfida di oggi — e per la stessa ragione non finisce nella
card da condividere. I contatori stanno sul documento della sfida (`players_count`,
`solved_count`): due `Increment`, nessuna lettura.

### Striscia, condivisione, archivio

- **Striscia** (`services/streak.py`): giorni consecutivi indovinati, con un bonus a soglie
  (3, 7, 30 giorni) e un tetto basso di proposito — deve premiare la costanza, non diventare
  il modo principale di fare punti. Si calcola nella stessa transazione che assegna i punti.
- **Card del risultato** (`services/share.py`): i quadratini stile Wordle (🟥🟩⬜ 2/3) con il
  numero della sfida, da incollare in un gruppo senza rivelare la risposta. Il bottone e' un
  link a `t.me/share/url`, quindi non serve la inline mode del bot. C'e' anche per chi **non**
  ci e' arrivato (🟥🟥🟥 X/3): la giornata persa e' meta' di quello che si incolla in un
  gruppo, ed e' l'unica riga che non puo' spoilerare niente. Le sfide recuperate
  dall'archivio si condividono marcate come tali, cosi' in un gruppo dove quella di oggi e'
  ancora aperta non sembrano il risultato di oggi.
- **Archivio** (`handlers/archive_handler.py`): rigiocare i giorni passati **senza punti**.
  Aprire un giorno mette l'utente in "modalita' archivio" (`archive_day` sul suo documento,
  non in memoria: su Cloud Run l'istanza puo' sparire fra un messaggio e l'altro), e da li' le
  risposte valgono per quella sfida finche' non la risolve o non fa `/today`. A tentativi finiti
  la risposta si puo' dire: quella giornata e' gia' passata.

### Allenamento e partite di gruppo

Due modalità con lo stesso motore (`services/practice_content.py`) e la stessa regola: si
gioca solo su materiale che **non può spoilerare la sfida del giorno**, e non si tocca la
classifica generale.

Il problema da risolvere è questo: pescare un giocatore qualsiasi dal dataset mostrerebbe il
percorso di carriera di qualcuno che non è ancora uscito, e chi lo ha visto — il giorno in cui
esce — lo riconosce in due secondi e si prende pure il bonus del primo. È un danno diretto
alla classifica. Le due sorgenti ammesse lo evitano in due modi diversi:

1. **il pool riservato** — i calciatori con `"practice_only": true` in `data/players.json`
   (152 sui 608 di oggi, bilanciati fra le quattro fasce di difficoltà) **non escono mai** come
   sfida del giorno né dentro un evento. Allenarsi su di loro non dà nessun vantaggio, per
   costruzione. È materiale disponibile subito e non costa **nessuna lettura**: le schede sono
   nel file, dentro il container. `python scripts/reserve_practice_players.py` è ciò che ha
   assegnato la fetta, e la scelta sta nel dataset — non calcolata a runtime, perché se la
   regola cambiasse un giocatore passerebbe da una parte all'altra e lo spoiler tornerebbe.
   Per lo stesso motivo `scripts/import_players.py` non perde il flag reimportando una scheda.
   I nomi da copertina (`popularity` 5) non si riservano mai: sono quelli che fanno venire
   voglia di rispondere a chi apre il bot la prima volta, e toglierli per sempre dalla sfida
   del giorno costerebbe piu' di quanto renda averli in allenamento;
2. **le sfide già passate** — pubbliche per costruzione: l'archivio le mostra, il broadcast di
   mezzanotte dice la risposta di ieri. Entrano una volta su quattro
   (`practice_past_challenge_ratio` in `data/config.json`), perché sono le partite vere e
   ritrovarne una ha un sapore diverso da un esercizio.

Anche la seconda sorgente costa **una lettura**: l'id del documento *è* la data, quindi si
estrae una data a caso e si legge quel documento. Scaricare l'elenco dei giorni passati per
sceglierne uno costerebbe fino a trecento letture a partita. Se il giorno estratto è vuoto (il
bot non c'era ancora, o la pulizia ha tolto quel documento) si riprova, e dopo qualche
tentativo a vuoto si ripiega su una query sola sui giorni recenti.

Le due sorgenti escono dal servizio con la stessa forma, chiave compresa (`pool:maldini`,
`day:2026-09-07`): chi le usa non sa da dove vengono, e la chiave è quello che si salva sul
documento utente o sul round per riprendere la partita dopo che l'istanza Cloud Run è sparita.

**Allenamento** (`/training`, `handlers/training_handler.py`): chi installa il bot oggi
gioca *una* partita e poi aspetta ventiquattro ore, ed è il minuto in cui si decide se
restare. Qui invece si preme un bottone e arriva un'altra sfida, per sempre. Nessun punto, il
confronto dopo ogni errore, cinque tentativi e poi la risposta — che si può anche chiedere
subito con "👀 Rivela", visto che quella giornata è passata. I tentativi sono cinque e non
infiniti anche per una ragione meno ovvia: un campo che accetta nomi all'infinito e risponde
"stessa nazionalità, ruolo diverso" sarebbe un modo comodo per sondare il dataset.

**Partita di gruppo** (`/round`, `handlers/group_handler.py`): un round alla volta nel
gruppo, vince chi risponde per primo, punti per difficoltà come nel gioco vero. **Non** è la
sfida di oggi ripubblicata — la risposta comparirebbe in chiaro davanti a chi non ha ancora
giocato, bruciando la giornata anche a chi non stava guardando. Le altre tre conseguenze della stessa scelta:

- **i punti restano nel gruppo** (`group_rounds/{chat}/players/{utente}`, `/standings`) e non
  toccano né la classifica generale né quella del mese: un gruppo creato con un account
  secondario non sposta niente di quello che conta;
- **si risponde con `/guess`**, non a messaggio libero: leggere i messaggi liberi di un gruppo
  vorrebbe dire spegnere la privacy mode in BotFather, cioè ricevere *tutti* i messaggi di
  *tutti* i gruppi in cui il bot è dentro. I comandi arrivano lo stesso;
- **non serve essersi registrati**: in gruppo non c'è niente da salvare sull'utente, e
  chiedere `/start` prima di poter rispondere toglierebbe alla modalità l'unica cosa che la
  rende utile.

Tre tentativi a testa per round, contati su un documento per giocatore (come i partecipanti a
un evento, e per lo stesso motivo: in un gruppo che risponde a raffica una mappa sola dentro
il round sarebbe un punto di contesa in scrittura). Si azzerano da soli quando comincia un
round nuovo, perché il documento porta il numero del round a cui si riferisce — lo stesso
meccanismo dei contatori giornalieri con `last_played_day`. Il round lo vince una persona
sola anche se in due rispondono nello stesso istante: è la stessa transazione del bonus del
primo.

### Leghe private

Una classifica fra amici (`handlers/league_handler.py`): `/league_create` genera un codice di sei
caratteri senza `0/O` e `1/I` (si detta a voce) e un link d'invito `t.me/<bot>?start=lega_CODICE`
che iscrive chi lo apre. I punti di una lega stanno sul documento del membro e vengono sommati
quando l'utente indovina — la classifica e' quindi una query ordinata invece di una lettura per
ogni iscritto — e contano solo **da quando si entra**, cosi' entrare in una lega vecchia non
condanna a restare ultimi.

### Negozio (Stelle di Telegram)

`/shop` e la quinta scheda della mini app vendono **solo cose da guardare**, pagate in
[Stelle di Telegram](https://core.telegram.org/bots/payments-stars): temi che ricolorano tutta
la mini app, cornici per l'avatar, titoli sotto il nome, distintivi accanto al nome in
classifica e i simboli della card che si incolla nei gruppi.

La regola sta sopra il catalogo e non si negozia: **niente di quello che si compra cambia la
partita.** Nessun punto, nessun tentativo in piu', nessun indizio scontato. Non e' prudenza: un
vantaggio comprabile trasformerebbe la classifica nella vetrina di chi ha speso, e il gioco
smetterebbe di essere lo stesso per chi non spende — che sono quasi tutti. C'e' un test che
lo verifica sul catalogo (`test_nothing_on_sale_touches_the_game`), perche' e' il tipo di
regola che si perde per strada un oggetto alla volta.

Il catalogo e' **contenuto**, non codice: sta in `data/shop.json` come i calciatori e gli
eventi, quindi prezzi, nomi e colori si ritoccano senza toccare un `.py`. Cinque tipi di
oggetto (uno per "slot": se ne indossa uno per tipo), piu' i pacchetti; ogni tipo ha il suo
oggetto gratuito, che e' anche il modo di tornare indietro a com'era prima.

| Tipo | Dove si vede | Prezzi |
|---|---|---|
| Temi | colori di tutta la mini app | 15 – 30 ⭐ |
| Cornici | il cerchio intorno all'avatar | 15 – 25 ⭐ |
| Titoli | una riga sotto il nome | 15 – 25 ⭐ |
| Distintivi | accanto al nome, **anche nella classifica in chat** | 10 – 25 ⭐ |
| Quadratini | i simboli della card condivisa (🟩🟥⬜ → 💚❤️🤍) | 10 – 20 ⭐ |
| Numeri | il numero di maglia prima del nome, **anche in classifica** | 10 – 15 ⭐ |
| Festeggiamenti | cosa succede sullo schermo quando indovini | non in vendita |
| Figurine | la finitura della card del risultato come immagine | 55 – 75 ⭐ |
| Pacchetti | piu' cose insieme | 30 – 220 ⭐ |

I primi cinque sono i **fondamentali** (`CORE_KINDS`) e una collezione li riempie tutti; i tre
in fondo sono arrivati dopo e una collezione puo' averli o no. Non e' pigrizia: un numero di
maglia o un festeggiamento non stanno addosso a ogni mondo, e inventarne uno per ogni set
vorrebbe dire riempire il catalogo di roba senza intenzione.

**Tre modi di avere una cosa senza comprarla**, e sono diversi apposta:

| | Come si ottiene | Si puo' perdere? |
|---|---|---|
| Traguardo (`achievement`) | un contatore che arriva a una soglia | **no**, si scrive e resta |
| Premio di completamento (`completes`) | possedere tutti i pezzi di una collezione | sì: un rimborso rompe la collezione |
| Podio (`trophy`) | arrivare fra i primi in un evento o nel mese | no, i trofei non si tolgono |

La differenza fra i primi due non e' un dettaglio. Un traguardo e' **un fatto avvenuto** e
per questo si scrive sul documento utente; un premio di completamento **e'** la collezione
completa, quindi se un pezzo torna indietro il premio se ne va con lui — che e' esattamente
quello che deve succedere. Gli otto festeggiamenti sono tutti premi di completamento: non si
comprano a nessun prezzo, e sono la ragione per arrivare dall'80% al 100% di una collezione.

**La rarita'** (`rarity_of`) non e' un dato in piu' da tenere allineato: si ricava dal prezzo,
quindi non puo' mentire. Un oggetto puo' dichiararla quando la fascia del prezzo racconta
un'altra cosa — una figurina che esiste solo dentro una collezione costa zero da sola, e
"gratuita" e' il contrario di quello che vuol dire.

**L'oggetto di benvenuto** costa una stella e si compra solo come **primo** acquisto
(`first_purchase_only`): il salto che conta non e' fra due prezzi, e' fra zero e il primo
pagamento. Dopo, un oggetto a una stella sarebbe solo un oggetto svenduto.

**La vetrina della settimana** sono tre oggetti di tre tipi diversi che cambiano ogni lunedi'.
Si ricavano dalla settimana ISO con un hash (`weekly_showcase`): non c'e' niente da scrivere,
niente da far girare a mezzanotte e quindi niente che possa restare indietro. E' la stessa
per tutti — una vetrina personalizzata sarebbe solo un altro ordinamento del catalogo, mentre
il senso e' che due persone nello stesso gruppo vedano la stessa cosa nello stesso momento.

**Le collezioni** (`"featured": true`) sono la forma che funziona meglio: cinque pezzi, uno
per slot, che raccontano la stessa cosa — *Notti europee*, *Domenica '90*, *Calcio di
strada*, *Cinegiornale 1966*, *Giorno di mercato*, *Notte di neve*, *Novembre in provincia*,
*Notte sudamericana*. Si vende un mondo, non un colore, e i pezzi restano comprabili singoli
per chi ne vuole solo uno. Su ogni collezione girano tre test: che riempia tutti e cinque gli
slot, che costi meno della somma, e che il testo del tema **si legga** sul suo sfondo (4.5:1,
`text` e `muted` contro `bg`, `bg2` e `card`) — un tema bello e illeggibile e' un tema rotto.

Sui set ispirati a un club: **niente stemmi, niente nomi, niente accostamenti dichiarati.**
Si descrivono i colori, non la squadra. La somiglianza la fa chi guarda, e il set resta
nostro.

Un pacchetto deve dare una ragione per esistere, e le ragioni ammesse sono due: costa meno
della somma dei pezzi, oppure contiene qualcosa che da solo non si vende (il Pacchetto
Sostenitore). Anche questo e' un test.

**I traguardi** sono cosmetici a `price: 0` con un blocco `achievement`: non si comprano, si
raggiungono giocando (il primo distintivo alla prima risposta giusta, l'ultimo a cento
calciatori). Servono a far vedere che gli slot esistono a chi il negozio non lo ha mai aperto.

**La tua formazione** è la sezione inviti, accessibile da Statistiche. Il link personale
`/start ref_<id>_<firma>` viene firmato dal server e associato solo durante la prima
registrazione: un solo invitante, nessun auto-invito o cambio successivo. Dopo **5 daily
concluse in giorni distinti**, anche non consecutivi, l'amico è qualificato. Contano le
vittorie e le sconfitte a tentativi esauriti; non contano aperture, partite abbandonate,
archivio, allenamento, duelli o eventi. Bot e mini app passano dallo stesso storico daily.

I premi permanenti sono la cornice L'intesa (3 amici), la card Lavagna del mister (5),
tema Il tuo undici con cornice e card coordinate (10). Hanno il contatore
`referral_qualified` e non sono acquistabili. La card tattica compare nel profilo e ha
una finitura dedicata sulle immagini dei risultati condivisi; le animazioni rispettano
la preferenza di movimento ridotto, si fermano quando il campo esce dallo schermo e nelle
miniature dei premi non partono affatto.

`services/referrals.py` conserva un documento per invitato nella collezione `referrals`,
con invitante, invitato, nome, timestamp di associazione, giornate conteggiate e timestamp
di qualificazione. La chiave è un hash stabile dell'id dell'invitato. La transazione
legge lo storico come prova e salva insieme qualificazione, contatore dell'invitante e
cosmetici guadagnati: tentativi ripetuti o simultanei non duplicano il premio. Lo storico
è salvato prima dell'accredito; in caso di errore la sezione inviti riconcilia gli amici
della pagina con le ultime cinque daily concluse. La lista privata usa pagine da 20 e
il pulsante per aggiornare, senza interrogazioni continue. Non espone id degli amici.
`/forgetme` rimuove i dati personali anche dal registro degli inviti, mantenendo solo la
chiave pseudonima con stato `deleted` contro il riutilizzo dello stesso account.

Non serve migrare i vecchi account: il contatore mancante vale zero. Servono le normali
configurazioni `BOT_TOKEN` e `BOT_USERNAME`; il link usa il bot per registrare l'invito
prima di aprire la mini app. Una rotazione del token invalida i vecchi link, senza
modificare associazioni già registrate. Per provare i premi in locale:
`python scripts/preview_webapp.py`, poi `/app?referrals=2` o `/app?referrals=10`.
I dati dell'anteprima sono esclusivamente in memoria.

Il punto delicato è che un traguardo **si ricava da un contatore**, e finché resta solo un
calcolo è anche reversibile: basta alzare un obiettivo in `data/shop.json` — una modifica a un
file di dati, che non passa da una riga di codice — e chi stava sotto la soglia nuova si
ritrova senza un distintivo che aveva già guadagnato. Per questo si scrivono, una volta sola,
nella stessa scrittura che muove il contatore che li fa scattare (`register_correct_guess` li
mette nella transazione che ha già letto il documento, quindi non costano nemmeno una lettura;
archivio e allenamento passano da `_bump_counters`). `owned_ids` continua comunque a calcolarli:
è la rete per chi ha preso un traguardo prima che li scrivessimo e non ha ancora rigiocato.

Un obiettivo può appoggiarsi solo a un contatore che una di quelle scritture raccoglie
(`HARVESTED_FIELDS`): appeso a un campo che nessuno raccoglie resterebbe per sempre un calcolo.
Anche questo è un test.

**Come funziona un pagamento**, nell'ordine — sta tutto in `handlers/shop_handler.py`:

1. si manda una fattura con `currency="XTR"` e `provider_token=""`: le Stelle non passano da un
   fornitore di pagamento esterno, quindi il token non c'e' proprio. In chat e' `send_invoice`,
   nella mini app e' `create_invoice_link` aperto con `openInvoice`;
2. Telegram chiede il permesso di incassare (`PreCheckoutQuery`) e vuole una risposta **entro
   dieci secondi**: e' l'ultimo momento in cui si puo' dire di no, ed e' li' che si controlla
   che l'oggetto esista e che l'utente non ce l'abbia gia' — incassare senza consegnare niente
   sarebbe una fregatura da rimborsare a mano;
3. a incasso avvenuto arriva un messaggio con `successful_payment`: qui si consegna e non si
   rifiuta piu' niente, perche' le Stelle sono gia' state prese.

Il punto 3 puo' arrivare **due volte** (Telegram rispedisce l'update se il webhook non risponde
in tempo), quindi la consegna e' idempotente sull'id della transazione: l'acquisto si scrive in
`purchases/{telegram_payment_charge_id}`, e la seconda consegna trova la riga gia' li' e non fa
niente.

**La pagina non consegna mai niente.** Il client manda solo l'id di quello che vuole comprare —
mai un prezzo, che lo dice il catalogo — e aspetta che il bot riceva il pagamento da Telegram.
Se la consegna la scrivesse la mini app, basterebbero gli strumenti di sviluppo per regalarsi
la collezione completa.

**Termini e privacy**: i due documenti che Telegram mostra a chi sta per pagare sono serviti
dallo stesso servizio del bot, come la mini app — `webapp/terms.html` e `webapp/privacy.html`
su `/terms` e `/privacy`, nelle tre lingue con un selettore in pagina (`?lang=it|es|en` apre
direttamente quella giusta, ed e' cosi' che li apre il bottone dentro `/shop`). Vanno
**incollati in BotFather** (`/mybots` → Bot Settings): Telegram li considera obbligatori per
la vendita di beni digitali. Il token del fornitore di pagamento invece no: per le Stelle non
esiste, si manda vuoto.

L'informativa descrive quello che il codice fa davvero — i campi sono quelli di
`USER_FIELD_DEFAULTS` e della collection `purchases`, la region e' quella del deploy, i 365
giorni sono la retention dell'artifact di backup — quindi **se cambia il codice va cambiata
anche lei**: un'informativa che descrive un trattamento diverso da quello vero e' peggio che
non averla. `tests/test_legal_pages.py` controlla che le tre lingue restino allineate (stesse
sezioni, stessa data), non che siano vere: quello resta un lavoro da fare a mano.

**Rimborsi**: `/admin_refund <charge_id>` chiama `refundStarPayment` e, solo se Telegram
accetta, ritira i cosmetici — ma **solo quelli che nessun altro acquisto ancora valido aveva
gia' dato**: chi aveva comprato il tema Neon da solo e poi il Pacchetto Neon, e si fa
rimborsare il pacchetto, il tema l'aveva pagato e resta suo.

### La figurina del risultato

La riga di quadratini si incolla; una figurina si guarda. `render_share_card`
(`services/path_image.py`) disegna il risultato come PNG verticale 860×1075 — il formato che
Telegram mostra piu' grande in una bolla senza tagliarlo — e la finitura e' un cosmetico
(`kind: card`): piatta, notturna, olografica, di pellicola.

Nel disegno **non entrano emoji**: il font non ha quei glifi e li stamperebbe come quadratini
vuoti (`services/fonts.py`). I tentativi sono forme disegnate, ed e' anche il motivo per cui
la card puo' avere una finitura — un'emoji non si puo' rendere olografica.

Tre cose che non cambiano:

- **la card non dice mai chi era il calciatore.** Stessa regola della riga di testo: la si
  incolla in un gruppo dove qualcuno non ha ancora giocato. C'e' un test che controlla il
  contratto della funzione, cioe' che non esista nemmeno un parametro dove un nome possa
  entrare;
- **la riga di testo resta.** La figurina si aggiunge, non sostituisce: chi ha le immagini
  spente continua a vedere il suo risultato, e una riga si incolla dove un'immagine non si
  puo' mettere;
- **si chiede, non arriva da sola.** In chat e' un bottone sotto il risultato, nella mini app
  e' "Vedi la figurina". Mandarla ad ogni risposta giusta vorrebbe dire un PNG per ogni
  partita di ogni utente, per far vedere un cosmetico a chi ce l'ha.

Le parole (titolo, trofeo appeso, serie, indizi) arrivano gia' tradotte da `services/share.py`:
il disegno non traduce niente.

### Trofei da appendere al profilo

I trofei si vincono sul podio di un evento o della classifica del mese, e stavano dentro una
lista dietro un bottone di `/stats`. Ora sono anche **targhe da indossare**: se ne scelgono
fino a tre (`services/trophies.py`) e vanno sul profilo, accanto al titolo comprato in
negozio e sul profilo pubblico.

Non passano da `services/shop.py`, pur finendo nello stesso posto. Un cosmetico si compra e
sta in un catalogo fisso, uguale per tutti; un trofeo si vince, e il suo catalogo e' diverso
per ogni utente — e' la sua bacheca. Farlo entrare nel negozio avrebbe voluto dire un
catalogo per utente, cioe' rompere la cosa su cui `get_item` e `owned_ids` sono costruiti.
Sono due mondi separati che si incontrano solo alla fine, quando la pagina disegna.

La scelta sta in `cosmetics.pinned` e non accanto a `trophies`: `trophies` lo scrive chi
assegna un podio, `pinned` lo scrive l'utente. Chi non ha mai scelto vede comunque le sue tre
targhe migliori (posizione prima, anno dopo) — altrimenti la cosa esiste solo per chi la
scopre. Dal profilo pubblico si vedono **solo** le targhe appese, mai la bacheca intera.

**La bacheca** e' una schermata sua e non una card in mezzo alle statistiche. Con quattro
trofei una fila di targhe funziona; con quaranta diventa un muro in cui il primo posto vinto
due anni fa sta in mezzo a dieci terzi posti. Quindi: il conto per medaglia in alto, i filtri
(posizione, evento o mese) che tolgono il grosso, e i trofei raggruppati **per anno** — che e'
il modo in cui uno se li ricorda. Da li' si sceglie quali tre appendere.

**Come si legge un codice.** Un trofeo di evento e' `{posizione}_{id del template}_{giorno}`,
e l'id di un template contiene trattini bassi suoi (`2_un_amore_una_maglia_20260907`): si
legge la posizione davanti e il giorno in fondo, e in mezzo c'e' l'id qualunque cosa
contenga. Contare i pezzi — che e' quello che si faceva prima — sbagliava su quasi tutti i
trofei veri, e `/stats` finiva per stampare il codice grezzo. Il nome leggibile e tradotto
arriva da `data/event_templates.json`, che e' l'unico posto dove quel nome esiste in tre
lingue.

### Mini app Telegram

`webapp/index.html` e' una pagina sola servita dallo stesso servizio FastAPI su `/app`, con
cinque schede: **Gioca**, **Archivio**, **Statistiche**, **Leghe**, **Negozio**. Non e' piu'
una vetrina:
ci si gioca davvero, con le stesse regole della chat.

Cosa aggiunge rispetto al bot, e perche':

- **completamento automatico sui nomi** (`POST /app/api/players`): e' il salto di qualita' piu'
  grande. Spariscono il "l'ho scritto giusto?" e il tentativo bruciato su un calciatore che il
  bot non conosce. Non regala niente: sono **tutte** le schede del dataset, comprese quelle
  riservate all'allenamento, quindi trovare un nome nell'elenco non dice che sia la risposta;
- **percorso in HTML invece che come PNG**: le righe si adattano allo schermo e, soprattutto, il
  paese arriva tradotto invece che cotto dentro l'immagine;
- **calendario delle giornate passate** con quattro stati distinti — presa, persa, recuperata in
  archivio, mai giocata — e la possibilita' di rigiocare quelle aperte;
- **istogramma dei tentativi** ("di solito la prendo al secondo"): i contatori stanno in
  `solved_in` sul documento utente, scritti quando si indovina, quindi non costa nessuna lettura;
- **gestione delle leghe**: creare, entrare, uscire, classifica completa e invito con il
  selettore di chat nativo di Telegram;
- **integrazione con l'app**: tema di Telegram (`--tg-theme-*`), `MainButton` di sistema al posto
  di un bottone in pagina, e vibrazione su risposta giusta o sbagliata;
- **[negozio](#negozio-stelle-di-telegram)**: il tema comprato arriva col profilo e non dietro
  la scheda del negozio, cosi' la prima schermata e' gia' del colore giusto invece di
  cambiare colore mezzo secondo dopo.

Due vincoli che non si toccano:

1. **chi sia l'utente lo stabilisce solo la firma di `initData`** (`services/webapp_auth.py`,
   HMAC-SHA256 con il token del bot piu' controllo sull'eta' dei dati). Il client non manda mai
   un id: adesso che la mini app gioca davvero, potrebbe giocare al posto di un altro;
2. **dal server non esce mai la risposta**. `services/webapp_api.py` non serializza mai il
   documento della sfida per intero: ogni card elenca i campi uno per uno, e `correct_answers` e
   `player_id` non sono fra quelli. Gli indizi arrivano solo dopo essere stati pagati. C'e' un
   test apposta (`test_the_answer_never_reaches_the_page`), perche' e' il tipo di errore che
   guardando lo schermo non si nota.

Il bottone "Apri l'app" compare solo se `PUBLIC_BASE_URL` e' configurata; senza, il bot funziona
esattamente come prima.

| Endpoint | Cosa fa |
|---|---|
| `POST /app/api/me` | profilo, sfida di oggi, classifica, leghe, istogramma |
| `POST /app/api/profile/search` | cerca per nome i profili pubblici, con risultati limitati |
| `POST /app/api/players` | i nomi per il completamento automatico |
| `POST /app/api/guess` | un tentativo (oggi, o una giornata passata con `day`) |
| `POST /app/api/hint` | un indizio, allo stesso prezzo della chat |
| `POST /app/api/calendar` | il calendario, o una singola giornata da rigiocare |
| `POST /app/api/league` | crea / entra / esci |
| `POST /app/api/shop` | la vetrina: la stessa che disegna `/shop` in chat |
| `POST /app/api/shop/buy` | il link della fattura in Stelle da aprire con `openInvoice` |
| `POST /app/api/shop/equip` | indossa un oggetto gia' posseduto |
| `GET /terms`, `GET /privacy` | i due documenti legali (pagine statiche, tre lingue) |

## Stack

- **Bot**: [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) su webhook, servito da **FastAPI** (`bot.py`)
- **Dati di gioco**: **Firebase Firestore** (`users`, `daily_path`, `events` con la sotto-collection `participants`, `seasons`). Le date sul database sono ISO `YYYY-MM-DD`; agli utenti si mostrano come `gg/mm/aa`
- **Scheduler**: **Cloud Scheduler** chiama `POST /internal/daily-job` a mezzanotte italiana (nessun processo interno da tenere sveglio)
- **Immagini**: percorso, banner evento, palmarès e avatar sono generati a runtime con **Pillow** (`services/path_image.py`), con un font TrueType di sistema (`fonts-dejavu-core` nel Dockerfile). Nessuna immagine ospitata fuori dal progetto
- **Dataset calciatori**: JSON locale versionato in `data/players.json`
- **Mini app**: pagina statica servita da FastAPI su `/app`, autenticata con la firma `initData` di Telegram

## Architettura dell'automazione

```
data/players.json          -> pool di calciatori curato (carriera, nazionalità, popolarità, verified)
data/event_templates.json  -> regole configurabili per generare gli eventi a rotazione
data/config.json           -> parametri di gioco (difficoltà, buffer giorni, anti-ripetizione, ecc.)
docs/difficolta.md         -> come si assegnano notorietà e difficoltà (da leggere prima di ampliare il dataset)

services/dates.py            -> un solo posto in cui si decide come si scrive una data (ISO sul db, gg/mm/aa a schermo)
services/firebase_service.py -> tutti gli accessi a Firestore (transazioni comprese)
services/daily_challenge.py  -> sfida del giorno, con cache in memoria della sola parte immutabile
services/player_pool.py      -> carica e valida il dataset, filtra per le regole di un evento
services/difficulty.py       -> calcola la difficoltà di un percorso (facile/normale/difficile/esperto)
services/dataset_health.py   -> salute del pool: autonomia, difficoltà scoperte, eventi senza candidati
services/path_image.py       -> disegna le immagini (Pillow): percorso, banner evento, palmarès, avatar
services/fonts.py            -> trova un TrueType di sistema per le immagini (fallback compreso)
services/matching.py         -> confronto tollerante fra risposta scritta e risposte accettate
services/guess_feedback.py   -> confronto fra il calciatore tentato e la soluzione (nazionalità, ruolo, età)
services/past_challenges.py  -> sceglie una sfida già passata, a una lettura invece che con una query
services/practice_content.py -> il materiale di allenamento e gruppo: pool riservato + sfide passate, una forma sola
services/streak.py           -> regole della striscia di giorni consecutivi
services/share.py            -> card del risultato in quadratini e link di condivisione
services/webapp_auth.py      -> verifica la firma dei dati che manda la mini app Telegram
services/webapp_api.py       -> i dati che la mini app mostra, in una risposta sola
services/daily_generator.py  -> sceglie il calciatore del giorno (con anti-ripetizione) e genera N giorni in anticipo
services/event_generator.py  -> sceglie un template evento a rotazione e lo riempie con giocatori validi
services/manual_event_service.py -> eventi creati a mano dalla chat (coppie padre/figlio)
services/content_admin.py    -> dettaglio e correzione di sfide/eventi gia' programmati (usato dalla dashboard locale)
services/dataset_editor.py   -> modifiche al dataset e alla taratura della difficolta' (usato dalla dashboard locale)

scripts/generate_content.py  -> entrypoint per generare il buffer a mano (debug/backfill)
scripts/import_players.py    -> importa nuovi calciatori nel dataset con validazione e anti-duplicati
scripts/reserve_practice_players.py -> riserva all'allenamento una fetta del dataset, bilanciata per difficoltà
scripts/dataset_report.py    -> report sullo stato del dataset (usato anche dalla CI)
scripts/migrate_firestore.py -> migrazione una tantum dei dati esistenti al modello nuovo
scripts/backup_firestore.py  -> export JSON del database, sotto-collezioni comprese (usato dal workflow settimanale)
scripts/backfill_users.py    -> completa i documenti utente a cui mancano i campi aggiunti dopo la loro registrazione
scripts/cleanup_daily_paths.py -> cancella le sfide oltre l'anno e i documenti pre-migrazione
scripts/preview_webapp.py    -> la mini app in locale, senza Telegram e senza Firestore (per guardare i cosmetici)
handlers/daily_job.py        -> job di mezzanotte chiamato da Cloud Scheduler: broadcast, reset, e generazione
handlers/guess_handler.py    -> tentativi sulla sfida del giorno (comando e messaggio libero)
handlers/archive_handler.py  -> sfide passate rigiocate senza punti
handlers/training_handler.py -> allenamento: sfide passate a raffica, in privato
handlers/group_handler.py    -> partite di gruppo: un round alla volta, punti solo dentro il gruppo
handlers/league_handler.py   -> leghe private, codici d'invito, classifiche
handlers/keyboards.py        -> tastiera del menu e menu comandi di Telegram
handlers/legend_handler.py   -> la legenda dell'immagine (bottone sotto la sfida e /legend)
handlers/menu_handler.py     -> i bottoni del menu, collegati agli handler dei comandi
handlers/admin_handler.py    -> tutti i comandi Telegram /admin_* (al posto di una dashboard web)
webapp/index.html            -> la mini app Telegram (servita da FastAPI su /app)
admin_ui.py                  -> dashboard locale Streamlit: stato dettagliato e modifiche ai dati
```

### Come viene scelto il calciatore del giorno

1. Ogni notte (23:15 UTC) **Cloud Scheduler** chiama `POST /internal/daily-job` sul servizio
   Cloud Run, che scrive direttamente su Firestore i prossimi `buffer_days_ahead` giorni
   mancanti (default 3), invia il broadcast agli utenti iscritti, assegna i trofei degli eventi
   conclusi e - il primo del mese - chiude la stagione mensile. **Non azzera nessun contatore**:
   i tentativi giornalieri si azzerano da soli (vedi [Database](#database)).
2. Il calciatore viene scelto **escludendo** quelli usati negli ultimi `history_days_no_repeat`
   giorni (default 60), tra i soli giocatori con `verified: true` e un percorso di almeno
   `min_teams_in_career` squadre (default 2) — niente percorsi banali o dati incompleti.
3. La difficoltà ruota secondo `difficulty_rotation` in `data/config.json`; se per quella
   difficoltà non ci sono candidati liberi, si prova la difficoltà più vicina.
4. La scelta è **deterministica per data** (seed = data): se la generazione va rieseguita per
   errore, il giocatore scelto per un giorno già passato resta lo stesso.
5. Se anche Cloud Scheduler non dovesse partire, `/show` e `/guess` generano la sfida del
   giorno al primo utilizzo (fallback "esecuzione alla prima richiesta").

### Come vengono generati gli eventi tematici

- Ogni "tipo" di evento è descritto come **template** in `data/event_templates.json`: nome,
  descrizione, tipo di gameplay (`path`/`career`/`transfer_guess`/`father_son`), regole di
  filtro sul pool di giocatori (es. minimo 6 squadre, solo big-5, solo nazionalità sudamericane),
  durata e punti giornalieri.
- **Nome e descrizione sono tradotti** (`name_i18n`, `description_i18n`): erano gli ultimi testi
  che restavano in italiano per tutti, perché sono contenuto e non passavano da
  `services/i18n.py` — quindi nemmeno dal test che tiene allineate le tre lingue. Ora c'è un
  test apposta ([`tests/test_event_translations.py`](tests/test_event_translations.py)) che
  fallisce se un template nuovo arriva senza traduzioni. `name` e `description` restano il
  testo italiano: sono il ripiego per gli eventi generati prima, ed è quello che legge
  l'amministrazione. Le traduzioni vengono **copiate sul documento dell'evento** al momento
  della generazione, come il nome: un evento già partito resta quello che era anche se il
  template cambia sotto.
- `services/event_generator.py` sceglie un template **non usato di recente** (vedi
  `event_history_no_repeat_templates`), rispetta un intervallo minimo tra un evento e l'altro
  (`event_min_gap_days`) e — se il template lo richiede — solo nel weekend (`weekend_only`).
- Un template può essere marcato `manual_only: true` (es. "Coppie leggendarie" padre/figlio, che
  richiede una foto e non una carriera): non verrà mai generato in automatico, si crea dalla
  chat con `/admin_fs_add` + `/admin_event_create` (vedi
  [Eventi "coppie padre/figlio"](#eventi-coppie-padrefiglio-manuali)).
- Per il tipo `career` (indovina le squadre di un giocatore noto) **non** viene mai salvata
  un'immagine del percorso nei dati giornalieri, per non rivelare la risposta.

### Difficoltà

**Come si assegnano notorietà e difficoltà è definito in
[`docs/difficolta.md`](docs/difficolta.md)**: è il riferimento da leggere prima di aggiungere
un giocatore o di ritarare i pesi, e contiene la scala `popularity` 1-5 con gli esempi.

In breve: la difficoltà è calcolata in `services/difficulty.py` e non è un campo del dataset.
La **notorietà** (`popularity` 1-5) fissa la fascia a passi di 4 punti; il percorso (quota di
tappe fuori dai campionati noti, paesi, squadre) pesa come modificatore per un massimo di 5.5
punti, cioè **può spostare un giocatore di una fascia, mai di due**. È il vincolo che evita i
due errori tipici: il campione girovago che risulta "impossibile" e lo sconosciuto con
carriera lineare che risulta "facile".

I campionati valgono su tre livelli — `top_leagues` (i top 5), `known_leagues` (Eredivisie,
Primeira Liga, Brasileirão, MLS...) e tutto il resto — così l'Ajax non pesa come una seconda
divisione asiatica. Pesi, soglie e liste sono in `data/config.json` e si ritarano senza
toccare il codice: `python scripts/dataset_report.py` mostra come si distribuisce il dataset
fra le quattro fasce, e `explain_difficulty(player)` scompone il punteggio di una singola
scheda. I punti assegnati per difficoltà sono invariati rispetto al gioco esistente (1/2/3/4).

Quando una fascia non convince, la sezione *Dataset* della
[dashboard locale](#dashboard-locale-streamlit) fa le stesse cose senza aprire il file:
elenca tutte le schede con il punteggio già scomposto in "da notorietà" e "dal percorso",
permette di correggere notorietà e campionato di una tappa, e mostra **chi cambia fascia
prima** di salvare. La logica sta in `services/dataset_editor.py`, che scrive
`data/players.json` con una copia di sicurezza in `backup/` e rifiuta le modifiche che
renderebbero il dataset incoerente.

## Comandi amministrativi

Riservati agli ID Telegram elencati in `ADMIN_TELEGRAM_IDS` (env var, separati da virgola).
Non c'è (e non serve) una dashboard **web** esposta pubblicamente: si amministra dalla chat,
oppure dalla [dashboard locale](#dashboard-locale-streamlit) quando serve vedere i dettagli o
correggere qualcosa a mano.

| Comando | Cosa fa |
|---|---|
| `/admin_help` | elenco dei comandi amministrativi |
| `/admin_status` | evento attivo, stato del dataset, sfide già in buffer |
| `/admin_stats` | utenti registrati, con notifiche attive, che hanno indovinato oggi |
| `/admin_pool` | salute del dataset: autonomia senza ripetizioni, difficoltà, eventi senza candidati |
| `/admin_review` | giocatori esclusi dalla selezione automatica e il motivo |
| `/admin_next [n]` | le prossime sfide già generate (**contiene le soluzioni**) |
| `/admin_events [n]` | ultimi eventi generati, con periodo e numero di partecipanti |
| `/admin_regen` | forza subito la generazione del buffer di sfide/eventi mancanti |
| `/admin_block <id>` | sospende un giocatore dalla selezione automatica (es. dato sbagliato segnalato) |
| `/admin_unblock <id>` | riammette un giocatore sospeso |
| `/admin_blocked` | elenco dei giocatori sospesi |
| `/admin_fs_add <risposte>` | salva una coppia padre/figlio (in didascalia a una foto) |
| `/admin_fs_list` | coppie padre/figlio salvate |
| `/admin_fs_del <id>` | elimina una coppia padre/figlio |
| `/admin_event_create <template> [gg/mm/aa] [giorni]` | crea a mano un evento |
| `/admin_refund <charge_id>` | rimborsa un acquisto in Stelle e ritira i cosmetici consegnati |

`/admin_block` scrive su Firestore (`admin_settings/dataset_overrides`), quindi ha effetto
**subito**, senza redeploy: utile quando un utente segnala una carriera sbagliata. Le sfide
già presenti nel buffer non cambiano, si controllano con `/admin_next`.

## Anteprima locale della mini app

```bash
python scripts/preview_webapp.py     # poi http://localhost:8888/app
```

Serve a **guardare** i cosmetici prima di venderli: un tema, una cornice o una collezione si
giudicano addosso a una pagina vera, non su un francobollo nella scheda del negozio e ancor
meno su sei stringhe esadecimali dentro `data/shop.json`.

E' la pagina vera (`webapp/index.html`) servita dalle funzioni vere (`services/webapp_api.py`,
`services/shop.py`, `services/trophies.py`): sotto, al posto di Firestore, c'e' un dizionario
in memoria. L'utente finto ha gia' **tutto** il catalogo e cinque trofei, cosi' ogni oggetto
si indossa con un click e ogni traguardo e' sbloccato; il negozio funziona ma "Compra"
consegna subito, senza fattura, perche' non c'e' niente da pagare.

Non tocca il database, non chiede credenziali e non serve Telegram: il finto `initData` lo
inietta il server nella pagina servita, quindi `webapp/index.html` resta il file di
produzione e non una sua variante. Si chiude e non resta niente.

Due comode: `POST /app/api/preview/wear {"bundle": "pacchetto_neve"}` indossa un'intera
collezione in un colpo, e `POST /app/api/preview/reset` rimette l'utente finto com'era.

## Dashboard locale (Streamlit)

```bash
pip install -r requirements-dev.txt
streamlit run admin_ui.py
```

Gira **sul proprio PC** con le stesse credenziali del bot (`.env` + `firebase-key.json`) e
non viene mai esposta: non ha login perché non è raggiungibile da fuori. Usa gli stessi
servizi dei comandi Telegram — nessuna logica duplicata — e in più permette le correzioni che
in chat sarebbero scomode. **Scrive sul database di produzione.**

| Sezione | Cosa mostra | Cosa permette di modificare |
|---|---|---|
| Stato generale | sfida di oggi con la soluzione, giorni coperti dal buffer, evento in corso, salute del dataset, utenti | genera subito sfide/eventi mancanti |
| Sfide giornaliere | ogni giorno della finestra scelta **buchi compresi**: numero della sfida, soluzione, difficoltà e punti, tappe di carriera, origine (auto/manuale), stato del bonus del primo, anteprima dell'immagine inviata agli utenti | sostituisci il giocatore, rigenera con le regole automatiche, correggi le risposte accettate, cambia la difficoltà, riapri/chiudi il bonus, elimina o programma una sfida in una data qualsiasi |
| Eventi | stato (programmato/in corso/concluso), giorno corrente su totale, giorno per giorno con risposte, punti e bonus, elenco dei giorni **senza contenuto**, classifica dei partecipanti | attiva/disattiva, sposta le date (rimappa anche i contenuti e il giorno dei trofei), correggi le risposte di un giorno, riapri/chiudi il bonus di giornata, elimina, crea un evento manuale |
| Utenti | classifiche, ricerca per id o per nome, scheda completa con striscia, trofei, leghe e archivio | punti totali e del mese, striscia, lingua, notifiche, azzeramento dei tentativi di oggi |
| Leghe | leghe private con numero di membri e classifica interna | — |
| Dataset | quattro schede: salute del pool, **elenco completo** dei giocatori con difficoltà e punteggio scomposto, scheda singola con le tappe e il peso di ogni campionato, taratura della formula | notorietà (`popularity`), *verificato*, *solo allenamento*, campionato di una tappa; pesi e soglie della difficoltà, con anteprima di chi cambia fascia |
| Giocatori sospesi | chi è escluso dalla selezione automatica | sospendi / riammetti |
| Coppie padre/figlio | coppie salvate e in quali eventi sono state usate | aggiungi (foto via bot) / elimina |

Le regole del gioco valgono anche qui, e stanno in `services/content_admin.py`, non
nell'interfaccia: la sfida di oggi non si elimina (è in gioco), un evento in corso si
disattiva invece di essere cancellato, sostituire il giocatore di una giornata già vinta non
rimette in palio il bonus del primo, e spostare un evento sposta insieme date, contenuti e
giorno dei trofei. Le letture stanno dietro una cache di 45 secondi (le letture Firestore si
pagano); ogni modifica la svuota.

## Eventi "coppie padre/figlio" (manuali)

Questo evento non si può generare dal dataset dei percorsi: serve una foto, e un dataset di
immagini di coppie padre/figlio non esiste. Resta quindi **manuale**, ma si crea interamente
da Telegram, senza scrivere documenti a mano su Firestore:

1. manda al bot la foto della coppia con didascalia
   `/admin_fs_add Maldini, Paolo e Cesare Maldini` (le risposte accettate separate da
   virgola). La foto **non viene ospitata da nessuna parte**: si salva il `file_id` di
   Telegram, che il bot può rimandare come immagine. In alternativa si può rispondere con lo
   stesso comando a una foto già inviata;
2. ripeti per tutte le coppie che vuoi (`/admin_fs_list` le elenca, `/admin_fs_del <id>` ne
   toglie una);
3. quando ce ne sono abbastanza: `/admin_event_create coppie_leggendarie [gg/mm/aa]`.
   L'evento dura **un giorno per coppia** (mai due volte la stessa coppia nello stesso
   evento) e le coppie già usate non vengono ripescate negli eventi successivi.

Lo stesso comando serve anche a **forzare a mano un evento automatico**, quando si vuole
decidere quando parte invece di aspettare la rotazione:
`/admin_event_create giramondo 01/12/26`.

## Ampliare il dataset dei calciatori

Il dataset è pensato per crescere nel tempo: oggi contiene **608 calciatori**, tutti
verificati. 456 alimentano il gioco vero — 456 giorni di sfide senza mai ripetere nessuno,
contro i 60 giorni della finestra anti-ripetizione — e 152 sono riservati all'allenamento e ai
round di gruppo, dove non possono spoilerare niente.

Questi numeri invecchiano da soli a ogni import, ed è già successo che restassero indietro:
`python scripts/dataset_report.py` li stampa aggiornati, ed è la fonte da guardare quando
quelli scritti qui e quelli veri non coincidono.

### Il flusso di import

Per **aggiungere** calciatori non si modifica `data/players.json` a mano: si prepara un file
di batch e lo si importa. Per **correggere** una scheda già dentro (notorietà sbagliata,
campionato scritto male) c'è la sezione *Dataset* della
[dashboard locale](#dashboard-locale-streamlit), che scrive lo stesso file con gli stessi
controlli.

```bash
# 1. prepara il batch (stesso schema di data/players.json, vedi gli esempi in data/incoming/)
# 2. prova senza scrivere
python scripts/import_players.py data/incoming/nuovo_batch.json --dry-run
# 3. importa davvero
python scripts/import_players.py data/incoming/nuovo_batch.json
# 4. controlla come sta il pool dopo l'aggiunta
python scripts/dataset_report.py
```

Lo script fa quello che a mano si dimentica sempre: normalizza id e alias, salta i giocatori
già presenti (`--update` per aggiornarli), rifiuta chi ha dati incoerenti spiegando il
motivo, e soprattutto intercetta gli **alias ambigui** — la stessa risposta valida per due
calciatori diversi, il bug più fastidioso per chi gioca, perché scrive la risposta giusta e
il bot gliela rifiuta. I nuovi arrivi restano `"verified": false` (e quindi fuori dalla
selezione automatica) finché qualcuno non ha controllato le date: `--verified` salta questo
passaggio, `/admin_review` elenca chi è in attesa di revisione.

Per **rivedere davvero** le schede in attesa serve vederne la carriera, non solo il nome:

```bash
python scripts/dataset_report.py --pending   # schede da approvare, tappa per tappa
```

Quando le date tornano, si approva reimportando lo stesso batch:

```bash
python scripts/import_players.py data/incoming/<batch>.json --update --verified
```

### Schema di una scheda

```json
{
  "id": "maldini",
  "full_name": "Paolo Maldini",
  "aliases": ["maldini", "paolo maldini"],
  "nationality": "Italia",
  "position": "Difensore",
  "birth_year": 1968,
  "popularity": 5,
  "verified": true,
  "one_club_career": true,
  "career": [
    {"team": "Milan", "country": "Italia", "league": "Serie A", "start_year": 1985, "end_year": 2009,
     "apps": 647, "goals": 29}
  ]
}
```

Ogni tappa ha tre campi facoltativi: `loan` (prestito), `apps` (presenze) e `goals` (gol).
Presenze e gol sono quelli di **campionato**, come li conta Wikipedia: alla Juventus Del
Piero risulta con ~478 presenze, non con le ~700 di tutte le competizioni.

`practice_only: true` toglie un calciatore dal gioco quotidiano e lo mette fra il materiale
di allenamento (vedi [Allenamento e partite di gruppo](#allenamento-e-partite-di-gruppo)). Non
si mette a mano: lo assegna `scripts/reserve_practice_players.py`, che tiene la fetta
bilanciata fra le fasce di difficoltà. Una volta riservato, un giocatore resta riservato — è
la ragione per cui il flag sopravvive a un reimport.

`one_club_career: true` serve a distinguere una **bandiera** (Totti, Maldini, Puyol: una sola
squadra e i dati sono completi) da una **scheda incompleta**: senza questo flag un percorso
di una squadra sola viene scartato come dato mancante. È anche ciò che rende possibile
l'evento "Un amore, una maglia".

`popularity` è l'unico campo che decide la difficoltà, quindi è anche l'unico che si può
sbagliare in modo silenzioso: **la scala con gli esempi è in
[`docs/difficolta.md`](docs/difficolta.md)**, che contiene anche la checklist da seguire
prima di scrivere una scheda nuova. La difficoltà, invece, non è un campo: è calcolata.

### Cosa si vede nell'immagine

Il percorso è disegnato da `services/path_image.py` **senza una parola**, perché ogni
informazione ha un segno e non un'etichetta:

| Informazione | Come appare |
|---|---|
| Prestito | barretta laterale **tratteggiata** e freccia `→` davanti agli anni |
| Tappa ancora in corso | `2016 – …` |
| Presenze e gol | `33 (22)`, la convenzione di Wikipedia; per i portieri le sole presenze |
| Durata della tappa | barra proporzionale, mostrata solo quando mancano presenze e gol |
| Campionato e paese | `Eredivisie · Olanda` sotto il nome della squadra |

L'unica eccezione al "senza una parola" e' l'ultima riga: **campionato e paese**. Il campionato
e' un nome proprio e non si traduce ("Premier League" e' Premier League ovunque), ma il paese nel
dataset e' scritto in italiano — e per un po' un inglese si e' letto "La Liga · Spagna". Adesso
`services/content_i18n.py` traduce paese e ruolo (86 paesi, 4 ruoli) e `render_career_path_image`
prende un parametro `lang`: la card si genera una volta per lingua, il che non costa niente
perche' si genera comunque al volo. Il dataset resta in italiano, che e' la lingua in cui lo si
scrive; a tenere allineata la tabella pensa `validate_dataset`, che segnala come problema di
integrita' ogni paese o ruolo che non sa tradurre.

Che questi segni vogliano dire qualcosa, pero', bisogna dirlo: sotto ogni sfida (e sotto
ogni sfida d'archivio) c'e' il bottone **"Come si legge"**, e c'e' il comando `/legend`
(`handlers/legend_handler.py`). Prima la notazione non era scritta da nessuna parte, nemmeno
in `/help`: chi apriva la sfida stava indovinando anche quella.

Il layout si adatta al numero di tappe: fino a 12 righe larghe, da 13 in su righe compatte.
Una carriera da 20 tappe sta in 900×1952 px — sopra le ~2000 px Telegram rimpicciolisce
l'immagine al punto da renderla illeggibile in chat, ed è il motivo per cui esiste la
soglia.

### Controlli automatici

`validate_dataset()` gira nei test e in CI (`python scripts/dataset_report.py --strict`) e
blocca la pipeline se il dataset ha: id duplicati, alias condivisi fra due giocatori, tappe
non in ordine cronologico, anni di fine precedenti all'inizio, esordi incompatibili con
l'anno di nascita, popolarità fuori dalla scala 1-5.

### Quando ampliarlo

`/admin_pool` (o `python scripts/dataset_report.py`) risponde alla domanda "il pool basta
ancora?": quanti giorni si va avanti senza ripetizioni, quante fasce di difficoltà sono
scoperte e quali eventi tematici hanno meno candidati dei giorni che durano. È il momento di
aggiungere calciatori quando compare un avviso: i giocatori selezionabili sono meno di 1,5
volte la finestra anti-ripetizione, oppure una fascia di difficoltà è quasi vuota.

## Database

Il modello dati Firestore è documentato in
[`docs/firebase_review.md`](docs/firebase_review.md), insieme al perché di ogni scelta.
In breve:

- `users/{telegram_id}` — l'id Telegram **è** l'id del documento: letture dirette, creazione
  atomica (niente utenti duplicati), transazioni possibili.
- **Nessun reset notturno dei contatori**: ogni documento porta `last_played_day`, quindi i
  tentativi di ieri valgono zero oggi senza che nessuno li abbia azzerati. Il costo del reset
  passa da "una scrittura per utente ogni notte" a zero.
- Il **bonus al primo che indovina** si assegna in transazione: due risposte simultanee non
  possono più prenderlo entrambe.
- I **partecipanti a un evento** sono documenti separati
  (`events/{code}/participants/{telegram_id}`), non una mappa dentro l'evento: niente limite
  di 1 MB e niente contesa in scrittura.
- Le **classifiche** si leggono con `order_by(...).limit(10)` più un `count()` per la
  posizione personale, invece di scaricare tutti gli utenti.
- `group_rounds/{chat_id}` — il round in corso di un gruppo, con la sotto-collection
  `players` (un documento per partecipante: punti del gruppo, round vinti, tentativi del
  round corrente). Sul round si copiano risposte accettate, difficoltà e `player_id`, così
  ogni tentativo costa **una** lettura invece di due; il percorso di carriera no, si
  ridisegna al momento.
- `users/{id}/history/{giorno}` — com'è andata **quella** giornata a **quell'** utente
  (`solved`, `attempts`, `hints`). Serve al calendario della mini app, che deve poter dire
  "questa l'hai presa al secondo, questa l'hai persa, questa non l'hai giocata": dai contatori
  sul documento utente non si ricava, perché quelli portano un giorno solo
  (`last_played_day`) e il giorno dopo sono sovrascritti. Si scrive **una volta sola** per
  giornata, quando la giornata si chiude per quell'utente, non a ogni tentativo.
- `daily_path/{giorno}` porta anche `players_count` e `solved_count`, cioè quanti hanno provato
  e quanti hanno indovinato: sono due `Increment` (nessuna lettura) e restano scritti dove sta
  la sfida, quindi valgono anche a distanza di mesi. Contarli a posteriori interrogando gli
  utenti funzionerebbe **solo per oggi**, che è esattamente il giorno di cui non serve saperlo.
- `purchases/{telegram_payment_charge_id}` — il registro degli acquisti in Stelle. L'id del
  documento **è** l'id della transazione Telegram, e questo fa due cose in una: rende la
  consegna idempotente (l'update rispedito trova la riga già scritta) e permette di rimborsare,
  perché `refundStarPayment` vuole esattamente quell'id. Cercarlo dentro i documenti utente
  vorrebbe dire scorrerli tutti. È fra le collection del backup (`scripts/backup_firestore.py`).
- Sul documento utente, `cosmetics` — `owned` (quello che ha comprato), `earned` (i traguardi
  che ha raggiunto giocando) ed `equipped` (quello che ha addosso, uno per slot). Gli oggetti
  **gratuiti non ci stanno**: sono gratuiti per definizione, e scriverli vorrebbe dire ripassare
  su ogni utente registrato ogni volta che se ne aggiunge uno. I traguardi invece ci stanno, e
  stanno in un elenco loro: da `owned` si ritira quando si rimborsa un acquisto, e da un
  traguardo non c'è niente da ritirare. Un oggetto indossato ma non più posseduto (succede dopo
  un rimborso) torna al valore di partenza invece di far disegnare un tema che non esiste.
- Sul documento utente: `daily_hints` (indizi chiesti oggi, si azzera da solo come i tentativi),
  `solved_in` (quante volte ha risolto in 1, 2, 3 tentativi: l'istogramma della mini app) e
  `event_key` (la sessione su un evento, come `archive_day` e `training_key`).

### Utenti registrati prima che un campo esistesse

I campi del documento utente si sono aggiunti col tempo (la lingua, la striscia, i contatori
di archivio e allenamento). Chi si era registrato prima restava senza, perche' `save_user()`
sul documento gia' esistente non scriveva niente: `/start` rispondeva nella lingua di
ripiego mentre i bottoni del menu uscivano in quella del client, e la lingua rilevata non
veniva salvata nemmeno allora.

Adesso `/start` completa il documento di chi lo esegue (`missing_user_fields()`), aggiungendo
**solo** i campi assenti: nessun valore gia' scritto viene toccato. Per non aspettare che
tutti rifacciano /start c'e' lo script, che si puo' lanciare a bot acceso ed e' idempotente:

```bash
python scripts/backfill_users.py --dry-run   # elenca chi verrebbe completato, campo per campo
python scripts/backfill_users.py             # scrive
```

La lingua e' l'unico campo che lo script **non** assegna: quale sia lo sa solo il client
Telegram, quindi la scrive `/start`. Chi resta senza continua a essere servito nella lingua
del suo client, come prima.

### Migrazione dei dati esistenti

A bot fermo:

```bash
python scripts/migrate_firestore.py --dry-run   # mostra cosa farebbe
python scripts/migrate_firestore.py             # esegue, con export JSON preliminare
firebase deploy --only firestore:rules,firestore:indexes
```

Lo script è idempotente: esporta prima tutto in JSON, poi sposta gli utenti sul nuovo id
(fondendo gli eventuali duplicati), converte le date in ISO e trasforma la classifica degli
eventi in sotto-collection.

[`firestore.rules`](firestore.rules) nega ogni accesso dai client (il bot usa solo l'Admin
SDK, che le ignora) e [`firestore.indexes.json`](firestore.indexes.json) contiene i due
indici compositi necessari.

### Backup e pulizia

L'export gestito di Firestore richiede il piano Blaze e un bucket; il database qui è piccolo
(utenti, un documento per giorno di gioco, qualche evento), quindi il backup è un JSON alla
settimana, archiviato come artifact di GitHub Actions
([`.github/workflows/backup.yml`](.github/workflows/backup.yml), lunedì alle 03:30 UTC, o a
mano con *Run workflow*). Si autentica con la stessa Workload Identity Federation del deploy:
nessuna chiave di servizio nei secret.

```bash
python scripts/backup_firestore.py            # copia in backup/, sotto-collezioni comprese
```

L'export segue le **sotto-collezioni** (`participants`, `members`, `archive`): sono metà dei
dati del gioco, e un backup che si ferma al primo livello sarebbe un backup finto.

`daily_path` cresce di 365 documenti l'anno e non si guarda indietro — l'archivio mostra dieci
giorni, l'anti-ripetizione sessanta, il numero della sfida è calcolato dalla data:

```bash
python scripts/cleanup_daily_paths.py --dry-run       # cosa cancellerebbe
python scripts/cleanup_daily_paths.py                 # sfide oltre l'anno
python scripts/cleanup_daily_paths.py --drop-legacy   # anche i documenti pre-migrazione
```

Lo script distingue due cose: le sfide **vecchie** (oltre la finestra da conservare, un anno
di default) e i documenti **inservibili** — id non in ISO, oppure senza percorso di carriera
o senza risposte accettate. Sono quelli che nell'archivio danno "sfida non più disponibile", e
si cancellano solo chiedendolo esplicitamente. La sfida di oggi e i giorni futuri già generati
non si toccano mai, e prima di cancellare viene scritto un JSON con tutto quello che sta per
sparire.

## Test

```bash
pip install -r requirements-dev.txt
pytest -q
```

I test coprono: selezione deterministica e anti-ripetizione del giocatore del giorno,
integrità del dataset (id duplicati, alias ambigui, cronologia delle carriere, bandiere),
import di nuovi calciatori, calcolo difficoltà, generazione eventi (rotazione, cooldown,
weekend-only, nessuna fuga di risposta per gli eventi "career"), creazione manuale
dell'evento padre/figlio, generazione dell'immagine del percorso, cambio di giorno/fuso
orario, permessi di **tutti** i comandi admin, e - dopo la revisione del database - il
flusso completo di `/guess` e `/events` (tentativi, bonus del primo assegnato una volta
sola, limiti giornalieri), il reset "pigro" dei contatori, il reset mensile, il broadcast di
mezzanotte, le classifiche e le trasformazioni della migrazione Firestore.

Sulle funzioni aggiunte dopo: tolleranza ai refusi (con la lista di coppie che **non** devono
essere confuse), messaggi liberi trattati come tentativo, confronto dopo un tentativo sbagliato
(compresi i casi in cui **non** deve uscire: nome fuori dal dataset, sfida senza `player_id`),
striscia e relativo bonus, quadratini della card condivisibile — vinta e persa —, backup con
le sotto-collezioni e regole di cancellazione dei `daily_path`, scelta di una sfida passata
(mai dal futuro, mai un documento senza percorso, e il ripiego quando le date estratte sono
vuote), allenamento (nessun punto, risposta svelata all'ultimo tentativo) e round di gruppo
(un solo vincitore, punti che non entrano nella classifica generale, nome con HTML dentro),
flusso completo dell'archivio (nessun punto, la giornata di oggi non
viene toccata, la risposta rivelata solo a tentativi finiti), leghe private (codici, limiti,
classifica, link d'invito che iscrive da `/start`), firma `initData` della mini app (dato
manomesso, token sbagliato, dati scaduti) e allineamento delle tre lingue: se una chiave o un
segnaposto manca in una traduzione, la CI se ne accorge — sia per i messaggi del bot
(`tests/test_i18n_keys.py`) sia per le stringhe della mini app, che stanno in
`webapp/strings.js` proprio perché `node --test` possa caricarle e confrontarle
(`tests/client.test.cjs`).

### Le transazioni, su un Firestore vero

Il resto della suite gira su finti in memoria, ed è giusto così: è veloce e non dipende da
niente. Ma un finto fa succedere quello che gli abbiamo detto di far succedere, quindi non si
accorgerebbe di una transazione scritta male — non c'è nessuna concorrenza da gestire.
`tests/test_firestore_transactions.py` gira invece contro l'emulatore, sui tre punti in cui
una doppia esecuzione **costa qualcosa**: il bonus al primo che indovina (punti dal nulla), la
consegna di un acquisto in Stelle (due righe nel registro da cui si rimborsa, per una stella
sola incassata) e la ricevuta di un update (un tentativo consumato due volte).

```bash
gcloud components install cloud-firestore-emulator     # una volta sola; richiede una JRE
gcloud emulators firestore start --host-port=127.0.0.1:8571
FIRESTORE_EMULATOR_HOST=127.0.0.1:8571 pytest -q
```

Senza `FIRESTORE_EMULATOR_HOST` quei test si saltano, così `pytest -q` resta verde su una
macchina che l'emulatore non ce l'ha. **In CI invece falliscono**, perché un test che si salta
da solo per un servizio mancante è comodo in locale ed è un verde bugiardo dove nessuno lo
guarda.

Una nota che serve a chi li leggerà: sull'emulatore due transazioni che partono nello stesso
millisecondo sullo stesso documento si annullano a vicenda finché il client rinuncia
(`Failed to commit transaction in 5 attempts`). Non è contesa da smaltire — alzare il limite a
50 tentativi non cambia niente, mentre bastano 150 ms di sfasamento perché vada sempre a buon
fine — ed è l'emulatore che non ha la messa in fila delle transazioni del servizio vero. Non è
neanche lo scenario di produzione: Telegram rispedisce un update dopo secondi e Cloud Tasks
riprova dopo un backoff. Per questo i test verificano **l'invariante** (non più di uno vince, e
il database non contiene mai più di quello che è stato vinto) e non pretendono che i perdenti
ricevano una risposta pulita.

## Deploy

Il bot gira su **Cloud Run** (container, deploy automatico da GitHub Actions dopo i test — vedi
[`docs/deploy.md`](docs/deploy.md)) e la generazione giornaliera dei contenuti è affidata a
**Cloud Scheduler**, che chiama un endpoint interno del servizio invece di dipendere da un
processo sempre acceso. Il ciclo completo test → deploy, con le scelte di qualità del codice e
gestione delle dipendenze, è documentato in [`docs/ci_cd_pipeline.md`](docs/ci_cd_pipeline.md).

| Componente | Dove | Perché |
|---|---|---|
| Bot (webhook) | **Cloud Run** | Container da [`Dockerfile`](Dockerfile), scala a zero quando inattivo, HTTPS incluso |
| Generazione giornaliera/eventi | **Cloud Scheduler** → `POST /internal/daily-job` | Non dipende dal fatto che l'istanza Cloud Run sia già sveglia; Cloud Run la avvia al bisogno |
| Database | **Firebase Firestore** | Già in uso, nessuna migrazione necessaria |

### 1. Cloud Run (bot)

Deploy automatico da GitHub Actions ad ogni push su `main` che supera la CI (setup di Workload
Identity Federation, comandi manuali di fallback e variabili d'ambiente del servizio: vedi
[`docs/deploy.md`](docs/deploy.md)).

Se cambia l'URL del servizio va aggiornato `WEBHOOK_URL` e il bot deve rieseguire `set_webhook`
(avviene automaticamente all'avvio, vedi `bot.py`).

Due variabili d'ambiente in piu' (facoltative, vedi [`.env.example`](.env.example)) accendono le
funzioni che hanno bisogno di sapere dove sta il bot:

| Variabile | Serve a | Se manca |
|---|---|---|
| `PUBLIC_BASE_URL` | mini app Telegram (`/app`) | il bottone "Apri l'app" non compare |
| `BOT_USERNAME` | link di condivisione del risultato e inviti alle leghe | i bottoni di condivisione/invito non compaiono, il resto funziona |

### 2. Cloud Scheduler (generazione contenuti)

Un job di Cloud Scheduler chiama ogni notte l'endpoint interno con l'header di autorizzazione:

```bash
gcloud scheduler jobs create http daily-generation \
  --schedule="15 23 * * *" \
  --uri="https://guess-the-player-595902172561.europe-west1.run.app/internal/daily-job" \
  --http-method=POST \
  --headers="x-cron-secret=<GENERATION_SECRET>" \
  --time-zone="UTC"
```

L'orario (23:15 UTC) è poco dopo mezzanotte a Roma sia in ora solare che legale. L'endpoint
(`bot.py`, `@app.post("/internal/daily-job")`) verifica l'header `x-cron-secret` contro
`GENERATION_SECRET` e rifiuta le chiamate non autorizzate con `403`.

### 3. Dominio personalizzato

Cloud Run supporta domini personalizzati e certificati gestiti gratuitamente tramite
"Custom Domains"; non necessario per il funzionamento del bot.

## Limiti noti / cosa resta da fare

- **Dataset**: 608 calciatori, tutti verificati; 456 selezionabili per la sfida del giorno
  (456 giorni senza ripetizioni) e 152 riservati all'allenamento. Il pool va comunque
  ampliato periodicamente: il segnale è l'avviso di `/admin_pool`, non il calendario.
- **Classificazione dei campionati**: `top_leagues` e `known_leagues` (`data/config.json`)
  si confrontano per stringa esatta, e quello che non è in nessuna delle due pesa come
  campionato sconosciuto nel calcolo della difficoltà. Per la coda lunga è il ripiego
  giusto, ma sopra le 20 tappe è una decisione che non ha preso nessuno: `/admin_pool` ora
  elenca quei campionati (oggi Chinese Super League, J1 League, Qatar Stars League, Serbian
  SuperLiga, Serie C, Indian Super League, UAE Pro League, Liga I, Cypriot First Division).
  La soglia è `unclassified_league_warning_min`.
- **Eventi "coppie padre/figlio"**: restano manuali per scelta, perché non esiste un dataset
  di immagini di coppie. La creazione però non richiede più di scrivere documenti su
  Firestore a mano: si fa da Telegram con `/admin_fs_add` + `/admin_event_create`.
- **Interfaccia di amministrazione**: oltre ai comandi Telegram `/admin_*`, c'è una
  [dashboard locale](#dashboard-locale-streamlit) (`streamlit run admin_ui.py`) che riusa gli
  stessi servizi e permette di correggere sfide ed eventi già programmati; va lanciata sulla
  propria macchina con le credenziali del bot, non è esposta pubblicamente. Non ha
  autenticazione propria: chi ha accesso al PC e al `firebase-key.json` ha accesso al
  database, quindi non va aperta su una macchina condivisa.
- **Font delle immagini**: sul container arrivano da `fonts-dejavu-core` (Dockerfile). Se il
  pacchetto sparisce, Pillow ripiega sul font bitmap di default: le immagini escono comunque,
  ma brutte. `services/fonts.py` accetta anche un font messo in `assets/fonts/` o indicato con
  `FONT_REGULAR_PATH` / `FONT_BOLD_PATH`.
- **Leghe private**: la classifica di una lega somma i punti fatti da quando si è entrati, e i
  limiti (50 membri, 5 leghe a testa) sono costanti in `handlers/league_handler.py`. Chi lascia
  una lega perde i punti accumulati lì dentro: rientrando riparte da zero.
- **Rimborsi delle Stelle**: passano da un comando amministrativo (`/admin_refund`), non da un
  bottone dell'utente. Chi ha cambiato idea lo scrive in chat e un amministratore esegue il
  comando: è il compromesso scelto per non costruire un flusso di rimborso automatico prima di
  sapere se qualcuno lo userà mai. La riga in `purchases` c'è comunque dal primo acquisto,
  quindi il rimborso è sempre possibile.
- **Cosmetici nelle leghe**: il distintivo si vede nella classifica generale (in chat e nella
  mini app) ma non in quella di una lega, perché i punti di una lega stanno sul documento del
  membro e mostrarlo lì vorrebbe dire denormalizzare il distintivo su ogni iscritto, e
  riscriverlo a ogni cambio.
- **Cloud Run scale-to-zero**: il servizio può andare a zero istanze se inattivo; la prima
  richiesta dopo un periodo di inattività (webhook Telegram o chiamata di Cloud Scheduler) ha
  qualche secondo di latenza in più per il cold start.
- **Database**: gli interventi della revisione sono stati applicati al codice, ma la
  **migrazione dei dati esistenti va eseguita a mano** (`scripts/migrate_firestore.py`) e le
  regole/indici vanno deployati. Backup ricorrente e pulizia dello storico invece ci sono
  ora, vedi [Backup e pulizia](#backup-e-pulizia).
- **Materiale per allenamento e gruppo**: il grosso è il pool riservato (152 calciatori, fissi
  finché non se ne riservano altri); le sfide passate sono la parte che cresce, e oggi ce n'è
  **una sola**. I 111 documenti scritti dalla versione precedente del bot (dal 26/04/25 al
  14/08/25) non erano utilizzabili — hanno le risposte ma non il percorso di carriera, solo un
  `image_url` su un hosting esterno — e sono stati rimossi con
  `scripts/cleanup_daily_paths.py`: comparivano anche nell'archivio, come giornate che si
  aprivano senza immagine e senza modo di giocarle. Il pool riservato si allarga rieseguendo
  `scripts/reserve_practice_players.py --ratio`, al prezzo di altrettanti giorni di autonomia
  del gioco quotidiano.
- **Confronto dopo un tentativo sbagliato**: vale sulla sfida del giorno, sull'archivio,
  sull'allenamento, sui round di gruppo e sugli eventi in cui si indovina un calciatore
  (`path` e `transfer_guess`). Resta fuori dagli eventi `career` (si risponde con delle squadre)
  e `father_son` (la coppia non è una scheda del dataset, quindi non c'è niente da confrontare).
  Per gli eventi vale solo su quelli generati **da adesso in poi**: il confronto ha bisogno di
  `player_id` nei dati del giorno, e gli eventi già in calendario non ce l'hanno — continuano a
  funzionare, semplicemente senza confronto.
- **Indizi**: solo sulla sfida del giorno. Nell'archivio e nell'allenamento non ci sono perché
  lì non ci sono punti da spendere, e la risposta si rivela comunque a tentativi finiti.
- **Traduzione dei contenuti**: `services/content_i18n.py` copre paesi e ruoli, cioè quello che
  finisce sotto gli occhi dell'utente. I **nomi dei campionati** restano in lingua originale
  perché sono nomi propri. Il dataset ne conteneva qualcuno italianizzato
  (`Super League Grecia`, `Premier League Ucraina`, `Primera Division Cile`): sono stati
  riportati al nome originale, perché l'effetto collaterale era reale — `top_leagues` e
  `known_leagues` in `data/config.json` si confrontano per stringa esatta, e la Super League
  greca era scritta in due modi di cui uno solo classificato, quindi un quarto delle tappe
  greche pesava come campionato sconosciuto. Adesso lo impedisce `validate_dataset()`, che
  rifiuta sia un nome di campionato che contiene il paese in italiano sia due grafie che si
  normalizzano allo stesso modo (`Segunda Division` / `Segunda División`).
- **Coerenza di club e paese**: la stessa `validate_dataset()` rifiuta un club che compare
  con due paesi diversi — era il caso di San Lorenzo e Vélez Sarsfield, argentini ma marcati
  `Spagna` in sette tappe, e il paese si vede nel percorso mostrato a chi gioca. I casi
  legittimi (club omonimi in due paesi, paesi che hanno cambiato nome) si dichiarano in
  `multi_country_clubs` di `data/config.json`: sono decisioni, non eccezioni silenziose.

## Licenza e uso

Il codice di questo repository è distribuito con licenza
**[PolyForm Noncommercial 1.0.0](LICENSE)**. In sintesi, e senza sostituire il testo della
licenza, che è l'unico che conta:

**Si può**, gratis e senza chiedere niente a nessuno:

- leggere, clonare, studiare il codice e usarlo come esempio;
- eseguirlo per conto proprio — su una macchina personale, per prova, per curiosità, per
  imparare;
- modificarlo, forkarlo e ridistribuirlo, anche modificato;
- usarlo a scopo di ricerca, didattica e progetti amatoriali; lo stesso vale per scuole,
  università, enti di ricerca pubblici e organizzazioni senza scopo di lucro.

**Non si può**, senza un accordo scritto con l'autore:

- usarlo per **qualsiasi scopo commerciale**: pubblicare un bot o una mini app derivata da
  questo codice con pubblicità, abbonamenti, acquisti in-app, Telegram Stars, sponsorizzazioni
  o qualunque altra forma di monetizzazione, diretta o indiretta;
- usarlo all'interno di un'azienda o di un'attività professionale;
- rivenderlo, concederlo in sublicenza o offrirlo come servizio a pagamento.

Chi ridistribuisce il codice, anche modificato, deve consegnare a chi lo riceve una copia
della licenza (o il suo URL) e la riga `Required Notice:` che si trova in [LICENSE](LICENSE) e
in [NOTICE](NOTICE).

**Uso commerciale.** L'autore resta unico titolare del copyright e può concedere condizioni
diverse: per un impiego commerciale si può chiedere una licenza separata aprendo una issue sul
repository.

### Cosa la licenza non copre

- **Le regole del gioco e l'idea.** "Indovina il calciatore dal percorso di carriera" è
  un'idea, e le idee non sono coperte dal diritto d'autore. Questa licenza vale sul codice
  scritto qui, non impedisce a nessuno di realizzare da zero un gioco che funziona allo stesso
  modo.
- **I dati dei calciatori.** Presenze, gol e squadre sono fatti, e i fatti non sono
  proteggibili. Le carriere in `data/players.json` sono in parte ricavate da **Wikipedia** e
  restano quindi disponibili con licenza **CC BY-SA 4.0**: chi le riusa deve attribuirle e
  ridistribuirle alle stesse condizioni. Il dettaglio sta in [NOTICE](NOTICE).
- **Le dipendenze.** Le librerie in `requirements.txt` hanno ciascuna la propria licenza.
- **Marchi e contenuti di terzi.** Nomi di squadre, campionati e competizioni citati nel
  dataset appartengono ai rispettivi titolari e sono usati a scopo puramente descrittivo.

### Note operative

Il repository **non contiene credenziali**: `.env` e `firebase-key.json` sono esclusi da
`.gitignore` e non sono mai stati committati. Chi clona ottiene il codice, non l'istanza in
produzione: per farlo girare servono un proprio bot Telegram e un proprio progetto Firebase,
come descritto in [docs/deploy.md](docs/deploy.md).
