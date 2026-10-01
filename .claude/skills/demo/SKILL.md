---
name: demo
description: Mostra una modifica della Mini App di guess_the_player_from_the_path nell'anteprima locale (scripts/preview_webapp.py, utente finto in memoria, niente Telegram né Firestore) a partire da un worktree - build, configurazione in .claude/launch.json con porta libera, avvio nel browser dell'app e screenshot. Usala quando l'utente chiede una demo, un'anteprima o di "farmi vedere" una modifica alla Mini App.
argument-hint: "[percorso worktree o numero issue]"
---

# Demo della Mini App

L'anteprima serve il bundle Vite vero (`webapp/dist/`) con le funzioni vere di `services/webapp_api.py`, ma
sopra un dizionario in memoria al posto di Firestore. Dettagli e utente finto: docstring di
`scripts/preview_webapp.py` e `docs/local-development.md`.

## 1. Quale codice

Usa il worktree indicato (`.worktrees/issue-<n>` o `.claude/worktrees/<nome>`); se non è indicato, quello in
cui stai lavorando. Mai il checkout principale per mostrare lavoro di un branch.

## 2. Build

Nel worktree (con `node_modules` come junction verso quello della root, vedi `inizia-issue`):

```bash
npm run build
```

L'anteprima mostra `webapp/dist`: senza una build nuova vedresti la versione vecchia.

## 3. Configurazione in `.claude/launch.json` (checkout principale)

Aggiungi una voce, con una porta non usata dalle altre voci (le esistenti partono da 8888):

```json
{
  "name": "<cosa mostra> #<n> (worktree)",
  "runtimeExecutable": "python",
  "runtimeArgs": ["<percorso assoluto del worktree, con />/scripts/preview_webapp.py"],
  "env": { "PREVIEW_PORT": "<porta>" },
  "port": <porta>
}
```

Se una voce per lo stesso worktree esiste già, riusala.

## 4. Avvio e verifica

1. `preview_start` con il `name` della voce, poi apri `http://localhost:<porta>/app`.
2. Imposta il viewport mobile (`resize_window` preset `mobile`): la Mini App si usa da telefono.
3. Porta la pagina nello stato da mostrare. Scorciatoie dell'anteprima: nella Daily la risposta `perdo`
   (`lose`/`pierdo`) chiude la partita persa senza cinque errori; le altre sono nella funzione
   `preview_guess` dello script.
4. Controlla la console (`read_console_messages`, solo errori) e fai gli screenshot dei momenti chiave. Se
   serve, prova anche il tema scuro (`colorScheme: "dark"`).
5. Alla fine riporta il viewport a `desktop`.

## 5. Dopo il merge

La voce in `launch.json` punta al worktree: quando questo viene rimosso (skill `pulisci-worktree`), va tolta
anche la voce.
