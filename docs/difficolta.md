# Difficoltà e notorietà: come si assegnano

Questo è il documento di riferimento per due decisioni che nel dataset si prendono a mano
decine di volte e che, se prese "a sensazione", si contraddicono nel giro di poche schede:

1. **quanto è famoso** un calciatore (`popularity`, 1-5);
2. **quanto è difficile** indovinarlo dal suo percorso (`easy` / `medium` / `hard` / `impossible`).

Solo la prima è un dato che scriviamo noi. La seconda è **calcolata** da
[`services/difficulty.py`](../services/difficulty.py) e non va mai scritta a mano: se una
difficoltà sembra sbagliata, quasi sempre è sbagliata la notorietà.

Il motivo per cui questo file esiste: prima di questa taratura, nel dataset Buffon, Casillas,
Pirlo e Batistuta avevano la stessa notorietà di Kluivert, mentre Lampard, Puyol e Fabregas
stavano una tacca sotto. Con una scala non scritta ognuno assegna la propria, e le difficoltà
che ne escono non stanno in piedi: Forlán risultava `impossible`, Del Piero `medium`.

C'è un secondo errore, più insidioso, che la scala scritta serve a prevenire: **assegnare i
valori bassi ai campioni**. Un dataset costruito raccogliendo "nomi che vengono in mente" è
fatto solo di gente famosa; se poi si distribuiscono i valori 1-5 *dentro quel gruppo*, Julio
César diventa un 3 e finisce in `hard`. La scala qui sotto è ancorata a nomi concreti proprio
per impedirlo: la fascia `hard` non è "un campione un po' meno famoso", è **un'altra
categoria di giocatori**.

---

## 1. La scala di notorietà (`popularity`)

La domanda a cui rispondere **non** è "quanto è stato forte" né "quanto ha vinto", ma:

> se scrivo questo nome, **chi lo riconosce?**

Il pubblico di riferimento è il **tifoso italiano medio**, quello che guarda la Serie A e le
coppe ma non segue l'Eredivisie. È una scelta, non una legge di natura: se un giorno il bot
avrà un pubblico diverso, questa è la riga da cambiare — e poi tutta la scala va rivista.

| Valore | Nome | Chi lo riconosce | Esempi dal dataset |
|---|---|---|---|
| **5** | Leggenda universale | Anche chi **non guarda il calcio**: il nome è entrato nella cultura generale | Messi, Cristiano Ronaldo, Ronaldo il Fenomeno, Ronaldinho, Zidane, Beckham, Maldini, Totti, Del Piero, Baggio, Buffon, Cannavaro, Pirlo, Kaká, Henry, Ibrahimović, Mbappé, Haaland |
| **4** | Campione | **Chiunque segua il calcio** lo nomina senza pensarci. Qui stanno tutti i vincitori, le bandiere di club, i nomi da Champions e da Mondiale | Julio César, Cambiasso, Recoba, Adriano, Zico, Stoichkov, Hagi, Okocha, Caniggia, Xavi, Casillas, Nesta, Forlán, De Ligt, Balotelli, Rivaldo |
| **3** | Titolare solido | Buon giocatore di un campionato importante, **mai una stella**. Il tifoso ci arriva ragionando, non a memoria | **Jakub Jankto**, De Roon, Gosens, Ilicic, Torreira, Muriel, Kalinić, Thauvin, Modeste, Max Kruse, Cabaye |
| **2** | Comprimario | Carriera dignitosa fatta di panchine e prestiti; il nome dice qualcosa solo a chi segue quel club | Paletta, Borriello, Ljajić, Ibišević, Nolito, Iborra, Ménez, Franco Vázquez |
| **1** | Da aneddoto | Te lo ricordi solo perché è passato da una squadra grande **senza lasciare traccia** | **Kevin Constant**, Pinilla, Schelotto, Ansaldi, Laxalt, Iturbe, Bebé, Drenthe, Biabiany |

### Le tre ancore

Quando un valore non è ovvio, si confronta con questi tre nomi invece di ragionare in astratto:

- **Julio César è un 4.** Leggenda dell'Inter del triplete: qualunque cosa faccia il suo
  percorso, non può superare `medium`. *Se stai per dare un 3 a un campione, fermati.*
- **Jakub Jankto è un 3.** Buon centrocampista di Serie A, nazionale ceco, zero copertine:
  è **lui** la materia prima della fascia `hard`.
- **Kevin Constant è un 1.** Terzino passato dal Milan che quasi nessuno rimette in fila:
  è **lui** la materia prima della fascia `impossible`.

### Regole pratiche per non litigare con sé stessi

- **Si giudica il nome, non la carriera.** Rivaldo è un 4 anche se ha finito in Angola;
  Kevin Constant è un 1 anche se ha giocato nel Milan. Quanto è strano il percorso lo misura
  già la formula, non serve scontarlo due volte sulla notorietà.
- **Il 5 è raro e va difeso.** Sono ~20 nomi su 250. Se stai per assegnare un 5 a qualcuno
  che tua zia non saprebbe nominare, è un 4.
- **Il vero collo di bottiglia è il 3, non l'1.** Un dataset costruito "dai nomi che vengono
  in mente" è fatto quasi solo di 4 e 5, e le fasce alte restano vuote: erano famosi tutti,
  anche i "difficili". Cercare apposta il livello Jankto è il lavoro che rende il gioco
  giocabile.
- **L'1 e il 2 non sono un giudizio di valore.** Sono gli unici che possono stare in
  `impossible`: senza di loro quella fascia non esiste e la rotazione giornaliera si inceppa.
- **Nel dubbio fra due valori, scegli il più alto** (più famoso). Sbagliare in su produce una
  sfida un po' facile; sbagliare in giù mette un campione in `hard` e fa sembrare il gioco
  tarato male — è l'errore che si nota.
- **Nessun pregiudizio di epoca.** Zico e Sócrates sono 4 come Cambiasso: chi segue il calcio
  li conosce. Non abbassarli perché sono vecchi né alzarli perché sono "storia".

---

## 2. Come si calcola la difficoltà

```
punteggio = (5 - popularity) × 4.0          ← la notorietà fissa la fascia
          + oscurità_campionati × 3.0        ← 0..3   modificatore
          + paesi_oltre_i_primi_due × 0.5    ← 0..1.5 modificatore
          + squadre_oltre_le_prime_cinque × 0.2  ← 0..1 modificatore
```

Pesi e soglie stanno in [`data/config.json`](../data/config.json)
(`difficulty_weights`, `difficulty_thresholds`) e si cambiano senza toccare il codice.

**La promessa del modello**: la notorietà sceglie la fascia, il percorso può spostarla **al
massimo di una**, mai di due. I modificatori sommano al più 5.5 punti contro i 4 che separano
un gradino di notorietà dall'altro. È questo che impedisce le due patologie di prima:

- un famoso con carriera girovaga non diventa `impossible` (era il caso Forlán);
- uno sconosciuto con carriera lineare non diventa `easy`.

### Soglie

| Punteggio | Fascia | Punti | Significato | Nome tipo |
|---|---|---|---|---|
| < 5 | `easy` | 1 | Lo indovina chiunque giochi | Del Piero |
| < 9 | `medium` | 2 | Serve seguire il calcio | Julio César, Forlán |
| < 13 | `hard` | 3 | Giocatore forte ma **non famosissimo** | Jankto |
| ≥ 13 | `impossible` | 4 | Comprimario che quasi nessuno rimette in fila | Kevin Constant |

### Cosa può capitare a ogni livello di notorietà

| `popularity` | Punteggio possibile | Fasce raggiungibili |
|---|---|---|
| 5 | 0.0 – 5.5 | `easy`, al limite `medium` |
| 4 | 4.0 – 9.5 | `easy` / `medium`, al limite `hard` |
| 3 | 8.0 – 13.5 | `medium` / `hard`, al limite `impossible` |
| 2 | 12.0 – 17.5 | `hard` / `impossible` |
| 1 | 16.0 – 21.5 | `impossible` |

Questa tabella è il modo più rapido per accorgersi di un errore: **se una scheda finisce in
una fascia che la sua notorietà non può raggiungere, la formula è a posto e il dato è
sbagliato.**

### I tre livelli di campionato

Non tutto ciò che sta fuori dai top 5 è ugualmente oscuro: l'Ajax e il Boca non possono
pesare come una seconda divisione asiatica. Ogni tappa vale:

| Peso | Chi | Dove è definito |
|---|---|---|
| **0.0** | I top 5 europei: Premier League, La Liga, Serie A, Bundesliga, Ligue 1 | `top_leagues` |
| **0.5** | Campionati che il pubblico colloca senza sforzo: Eredivisie, Primeira Liga, Liga Profesional, Brasileirão, MLS, Championship, Süper Lig, Serie B, Scottish Premiership, Liga MX... | `known_leagues` |
| **1.0** | Tutto il resto (J1 League, Chinese Super League, Qatar Stars League, Liga I, Girabola...) | *nessuna lista: è il default* |

L'`oscurità_campionati` è la **media** di questi pesi sulle tappe, non la somma: una carriera
lunga non viene punita solo perché è lunga (a quello pensa già, con molta moderazione, il
termine sulle squadre).

Aggiungere un campionato a `known_leagues` è una decisione editoriale, non tecnica: chiediti
se il tifoso di riferimento, letto il nome del campionato, sa in che paese si gioca.

---

## 3. Casi di riferimento

Sono i tre casi che hanno motivato la revisione, più due controlli agli estremi. Valgono da
test di regressione: se cambi pesi o soglie, questi devono continuare a tornare
(`tests/test_difficulty.py` li verifica).

| Giocatore | `popularity` | Percorso | Punteggio | Fascia | Perché |
|---|---|---|---|---|---|
| **Totti** | 5 | Roma | 0.00 | `easy` | L'estremo basso: punteggio zero. |
| **Del Piero** | 5 | Padova → Juventus → Sydney FC | 1.50 | `easy` | Nome universale; la tappa australiana non basta a spostarlo. *Prima era `medium`.* |
| **De Ligt** | 4 | Ajax → Juventus → Bayern → United | 5.38 | `medium` | Solo top club, l'Ajax non è una tappa oscura. *Prima era `hard`.* |
| **Julio César** | 4 | Flamengo → Chievo → Inter → QPR → Toronto → Benfica | 6.45 | `medium` | **Ancora della scala**: una leggenda del triplete non può stare in `hard`, per quanto giri. *Prima era `hard`.* |
| **Forlán** | 4 | Independiente → United → Villarreal → Atlético → Inter → Internacional → Cerezo Osaka → Peñarol | 7.04 | `medium` | Campione mondiale: 8 squadre in 7 paesi lo alzano di una fascia, non di tre. *Prima era `impossible`.* |
| **Jankto** | 3 | Udinese → Ascoli → Udinese → Sampdoria → Getafe → Sparta Praga → Cagliari | 9.33 | `hard` | **Ancora della scala**: forte, titolare, mai una stella. È questo che deve stare in `hard`. |
| **Kevin Constant** | 1 | Châteauroux → Chievo → Genoa → Milan → Trabzonspor → Bologna → Sion | 18.04 | `impossible` | **Ancora della scala**: è passato dal Milan e quasi nessuno lo rimette in fila. |

---

## 4. Aggiungere un giocatore: checklist

Il percorso previsto è un file in [`data/incoming/`](../data/incoming/) importato con
`python scripts/import_players.py`, che rifiuta le schede incoerenti e tiene i nuovi arrivi a
`verified: false` finché qualcuno non li ha controllati (vedi il README, sezione *Dataset*).

Prima di scrivere la scheda:

1. **Assegna `popularity` con la tabella della sezione 1**, guardando gli esempi, non a
   intuito. Se esiti fra due valori, prendi il più basso.
2. **Non scrivere la difficoltà**: non è un campo del dataset, esce dal calcolo.
3. **Metti tutte le tappe**, anche quelle brevi e imbarazzanti: sono il sale del gioco e
   sono ciò che la formula misura. Le tappe vanno in ordine cronologico (l'import lo
   controlla).
4. **Usa i nomi di campionato già presenti nel dataset**, altrimenti la tappa finisce d'ufficio
   nel livello "oscuro" per un errore di battitura. `python scripts/dataset_report.py` elenca
   quelli in uso (la dashboard, sezione 5, li propone in una tendina).
5. **Controlla dove è finito**: se la fascia non ti convince, guarda la scomposizione del
   punteggio (sezione 5) prima di cambiare i pesi globali.

### Il vero lavoro: cercare i nomi giusti

`easy` e `medium` si riempiono da sole, perché i nomi che vengono in mente sono famosi per
definizione. `hard` e `impossible` **non si riempiono mai per caso**: vanno cercate apposta.

Il modo sbagliato di popolare le fasce alte è prendere un campione con una carriera strana
(Forlán, Rivaldo, Okocha) — resta un campione, e la formula lo riporta giù. Il modo giusto è
partire dal campionato e scendere di livello:

> *"Chi giocava in Serie A nel 2018 che era forte ma di cui nessuno parlava?"* → Jankto.
> *"Chi è passato dal Milan senza che me ne ricordi?"* → Kevin Constant.

E poi ripetere la stessa domanda per Premier, Liga, Bundesliga e Ligue 1. Un buon batch nuovo
è fatto **in maggioranza di `popularity` 1-3**; se dopo averlo scritto è pieno di 4, hai
raccolto altri nomi famosi.

---

## 5. Quando una difficoltà sembra sbagliata

Il modo più rapido è la sezione **Dataset** della dashboard locale
(`streamlit run admin_ui.py`, vedi il README): fa esattamente il percorso descritto qui sotto,
senza aprire il file.

| Scheda | A cosa serve |
|---|---|
| *Elenco e modifiche* | tutte le schede con fascia, punteggio e le due colonne **da notorietà** / **dal percorso**: si ordina per punteggio e si vede subito chi è finito nel posto sbagliato. La notorietà si corregge nella tabella, e prima di salvare la dashboard dice **chi cambia fascia** |
| *Scheda singola* | la scomposizione in quattro addendi di un giocatore e le sue tappe con il **peso di ogni campionato** (0.0 / 0.5 / 1.0): è così che si becca il nome scritto in un modo che non è in lista |
| *Taratura difficoltà* | pesi e soglie con l'anteprima della **ridistribuzione sull'intero dataset**, che è l'unico modo onesto di toccarli |

Le modifiche finiscono in `data/players.json` (o `data/config.json` per la taratura) passando
da `services/dataset_editor.py`, che tiene una copia di sicurezza in `backup/` e rifiuta le
modifiche che renderebbero il dataset incoerente. Da riga di comando l'equivalente della
prima colonna è:

`explain_difficulty(player)` scompone il punteggio nei suoi quattro addendi e dice subito se
a pesare è la notorietà o il percorso:

```python
from services.player_pool import get_player_by_id
from services.difficulty import explain_difficulty

explain_difficulty(get_player_by_id("forlan"))
# {'score': 7.04, 'difficulty': 'medium',
#  'components': {'popularity': 4.0, 'minor_leagues': 1.125,
#                 'extra_countries': 1.5, 'extra_teams': 0.6}, ...}
```

Nell'ordine, le tre cause possibili:

1. **`popularity` sbagliata** — il caso di gran lunga più frequente. Si corregge la scheda.
2. **Tappe mancanti o campionato scritto male** — un nome di campionato fuori lista pesa
   1.0 invece di 0.5. Si corregge la scheda.
3. **Taratura da rivedere** — solo se il problema si ripete su molte schede diverse. Allora
   si toccano `difficulty_weights` / `difficulty_thresholds` in `data/config.json` e si
   ricontrolla la distribuzione con `python scripts/dataset_report.py` (o si guarda
   l'anteprima nella scheda *Taratura difficoltà* della dashboard, che la calcola prima di
   salvare).

**Non risolvere un caso singolo spostando le soglie**: si sistema un giocatore e se ne
rompono venti. Le soglie si toccano solo guardando la distribuzione dell'intero dataset, che
deve restare grosso modo bilanciata sulle quattro fasce — la rotazione giornaliera le pesca a
turno e una fascia quasi vuota si traduce in ripetizioni per gli utenti.
