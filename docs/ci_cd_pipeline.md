# Ciclo di pubblicazione (CI/CD)

Panoramica di come codice e dati arrivano da un push su `main` al servizio in produzione, e di
tutto quello che è stato messo in piedi per farlo funzionare senza intervento manuale. Per il
dettaglio "come deployare Cloud Run/Cloud Scheduler" vedi [`docs/deploy.md`](deploy.md); questo
documento copre invece l'intera pipeline: qualità del codice, dipendenze, e collegamento tra CI
e deploy.

## Il quadro d'insieme

```
push/merge su main
        │
        ▼
┌─────────────────┐   fallisce   ┌──────────────────────────┐
│  CI (ci.yml)     ├─────────────►  niente deploy, si resta  │
│  test + qualità  │              │  sulla revisione attuale │
└────────┬─────────┘              └──────────────────────────┘
         │ passa
         ▼
┌─────────────────────┐
│  Deploy (deploy.yml) │   trigger: workflow_run su "CI" completato con successo
│  gcloud run deploy   │   auth: Workload Identity Federation (nessuna chiave scaricata)
└──────────┬───────────┘
           ▼
   Cloud Run (produzione)
```

Il punto chiave: **il deploy non ha un trigger proprio**, dipende dall'esito di CI
(`workflow_run` su `main`). Codice che non passa test/lint/type-check non arriva mai in
produzione, senza bisogno di un job "test" duplicato dentro deploy.yml.

## 1. CI — [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

Gira su ogni pull request e su ogni push su `main`. Passi, in ordine (si ferma al primo che
fallisce); il file del workflow resta la fonte esatta:

| Step | Cosa controlla | Comando |
|---|---|---|
| Frontend: dipendenze e type check | la Mini App compila senza errori di tipo | `npm ci`, `npm run typecheck` |
| Frontend: build | il bundle Vite di `/app` si costruisce | `npm run build` |
| Test frontend | test unitari TypeScript, compreso l'allineamento delle stringhe IT/EN/ES | `npm run test:frontend` |
| Audit dipendenze frontend | vulnerabilità npm di livello alto | `npm audit --audit-level=high` |
| Controllo sintassi | i moduli Python compilano | `python -m compileall -q bot.py config.py apps domains services handlers scripts admin_pages admin_ui.py tools` |
| Lint | regole `E`, `F`, `W`, `I` di ruff (`E501` disattivato) | `ruff check .` |
| Type check | annotazioni coerenti in `services/` e `domains/` | `mypy services/ domains/` |
| Sicurezza | pip-audit con eccezioni a scadenza, detect-secrets, npm audit (vedi [security.md](security.md)) | `python -m tools.security` |
| Validazione dataset | i JSON in `data/` sono validi | script inline in `ci.yml` |
| Salute del dataset | id duplicati, alias ambigui, cronologie incoerenti | `python scripts/dataset_report.py --strict` |
| Regressione dataset | metriche di qualità non peggiorano rispetto a `data/dataset_baseline.json` | `python -m scripts.dataset_regression --check` |
| Emulatore Firestore | Java 21 + `gcloud` avviano l'emulatore; se non parte la CI fallisce | `gcloud emulators firestore start` |
| Test + coverage | l'intera suite pytest, transazioni reali sull'emulatore comprese, con soglia minima | `pytest -q --cov=services --cov=domains --cov=handlers --cov-report=term-missing --cov-fail-under=70` |

Configurazione di ruff/mypy in [`pyproject.toml`](../pyproject.toml): niente `__init__.py` nei
package (`services/`, `handlers/`, `domains/`), quindi mypy ha bisogno di `explicit_package_bases = true` e
`mypy_path = "."` per non confondere `services.firebase_service` con `firebase_service`.

**Soglia di coverage**: 70%, contro il 74% reale. È un guardrail contro regressioni, non un
obiettivo: la soglia sta qualche punto sotto il valore corrente perché deve fermare una
regressione vera, non una riga scoperta in più. Restava a 50% mentre la copertura era già
salita di venti punti, e in quello spazio ci si poteva cancellare un modulo di test senza che
la CI dicesse niente. Si alza mano a mano che si aggiungono test, tenendo lo stesso margine.

## 2. Deploy — [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)

```yaml
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    ...
```

Passi: checkout dello stesso commit testato (`ref: ${{ github.event.workflow_run.head_sha }}`),
autenticazione GCP via `google-github-actions/auth@v2` (Workload Identity Federation), poi
`gcloud run deploy guess-the-player --source . --project guess-the-player-from-path-bot --region
europe-west1 --max-instances 10 --quiet`. La build dell'immagine ([`Dockerfile`](../Dockerfile))
compila anche il bundle Vite della Mini App in uno stage Node separato.

**Perché WIF e non una chiave di service account**: una chiave scaricata è un segreto di lunga
durata che, se trapela, resta valido finché non lo revochi a mano. WIF fa scambiare a GitHub
Actions un token OIDC di breve durata contro un'identità GCP temporanea, vincolata (tramite
`--attribute-condition`) a questo repository specifico — nessun segreto persistente da
proteggere o far scadere.

Il setup one-shot (pool WIF, provider OIDC, service account `github-deployer`, ruoli IAM, secret
GitHub `WIF_PROVIDER`/`WIF_SERVICE_ACCOUNT`) è documentato con i comandi `gcloud` completi in
[`docs/deploy.md`](deploy.md#deploy-automatico-github-actions) — fatto una volta sola,
il 2026-09-07.

### Permessi IAM del service account `github-deployer`

`gcloud run deploy --source .` non è solo Cloud Run: internamente fa buildare l'immagine da
Cloud Build e la carica su Artifact Registry, quindi il service account deployer ha bisogno di
tutti e tre i pezzi:

| Ruolo | Perché |
|---|---|
| `roles/run.admin` | creare/aggiornare il servizio Cloud Run |
| `roles/iam.serviceAccountUser` | impersonare il service account di runtime del servizio |
| `roles/cloudbuild.builds.editor` | avviare la build dell'immagine |
| `roles/storage.admin` | Cloud Build carica i sorgenti su un bucket temporaneo |
| `roles/artifactregistry.writer` | leggere/scrivere sul repository `cloud-run-source-deploy` dove finisce l'immagine buildata |

### Cosa è andato storto nel primo giro (log del 2026-09-07)

Utile da tenere a mente per il prossimo progetto che parte da zero con questo stesso schema:

1. **CI rossa al primo push**: `Pillow==12.3.0` (appena aggiornato, vedi sotto) è incompatibile
   con `streamlit==1.38.0` (richiede `pillow<11`). Fix: aggiornato streamlit a `1.63.0`
   (`pillow<13`), che a sua volta ha alzato il vincolo minimo di `uvicorn` a `>=0.30.0` —
   aggiornato anche quello, da `0.29.0` a `0.30.6`. **Lezione**: un bump isolato di una
   dipendenza va sempre verificato con `pip install --dry-run` contro l'intero
   `requirements-dev.txt`, non solo contro `requirements.txt`.
2. **Deploy rosso col permesso `artifactregistry.writer` mancante**: il ruolo non era
   nell'elenco iniziale di permessi (aggiunto solo dopo aver letto l'errore
   `PERMISSION_DENIED: artifactregistry.repositories.get` nei log). Aggiornato sia il workflow
   che la lista comandi in `docs/deploy.md`.
3. **Deploy rosso ancora, stesso errore, subito dopo aver concesso il ruolo**: propagazione IAM
   non istantanea. Bastato un `gh run rerun <id> --failed` un minuto dopo, senza nessun altro
   cambiamento — non serve pushare un nuovo commit per far ripartire un job fallito per un
   problema esterno al codice.

Deploy riuscito: revisione `guess-the-player-00006-rp6`, servizio raggiungibile su
`https://guess-the-player-595902172561.europe-west1.run.app`.

### Deploy manuale (fallback)

Resta disponibile per un rollback rapido o per testare una build locale senza aspettare la CI:
vedi [`docs/deploy.md`](deploy.md#deploy-manuale-fallbackdebug).

## 2bis. Release check — [`.github/workflows/release-check.yml`](../.github/workflows/release-check.yml)

Terzo workflow, separato da CI e Deploy: parte solo su push di un tag `v*.*.*` e valida che
`VERSION` e `CHANGELOG.md` corrispondano a quel tag (`python -m tools.release check --tag
...`), permessi `contents: read` soltanto. Non riesegue test/lint/build — per policy un tag
si crea solo su un commit la cui CI è già verde (vedi
[release-checklist.md § Exact-commit requirement](release-checklist.md#8-exact-commit-requirement)),
quindi rifarli qui duplicherebbe la CI senza aggiungere informazione. Dettagli completi in
[release-checklist.md § CI release gate](release-checklist.md#9-ci-release-gate--release-checkyml).

## 3. Dependabot — [`.github/dependabot.yml`](../.github/dependabot.yml)

Apre PR automatiche settimanali per aggiornamenti di:
- dipendenze pip (`requirements.txt` e `requirements-dev.txt`, root `/`)
- GitHub Actions usate nei workflow (`actions/checkout`, `google-github-actions/*`, ecc.)

Ogni PR passa dalla stessa CI descritta sopra prima di poter essere mergiata: un aggiornamento
che rompe qualcosa (com'è successo manualmente con Pillow/streamlit qui sopra) si vede subito
come CI rossa sulla PR, invece di scoprirlo al prossimo deploy manuale.

## 4. Pulizia dipendenze collegata

Fatta nella stessa sessione di lavoro, perché toccava gli stessi file:

- **`pytz` → `zoneinfo`** (stdlib da Python 3.9+): un import in meno da mantenere. Aggiunta
  `tzdata` come dipendenza esplicita perché `zoneinfo` da solo non porta il database IANA dei
  fusi orari su Windows e su immagini Docker slim — senza `tzdata` il servizio funzionerebbe in
  CI (Ubuntu ha il database di sistema) ma potrebbe fallire in ambienti senza. Tutti gli usi di
  `pytz.timezone(...).localize(...)` sono diventati `datetime(..., tzinfo=ITALY_TZ)` /
  `naive.replace(tzinfo=ITALY_TZ)` (zoneinfo non ha `.localize()`).
- **Pillow 10.4.0 → 12.3.0**: versione con le patch di sicurezza successive.
- **`except Exception` ristretti** in `services/firebase_service.py` e
  `services/daily_generator.py` a `google.api_core.exceptions.GoogleAPICallError`: prima
  un'eccezione qualunque (anche un bug nel codice sopra la chiamata Firestore) veniva
  silenziata con lo stesso "va bene, continuo senza"; ora solo un vero errore di rete/API verso
  Firestore attiva il fallback.

## Cosa resta aperto

- **Coverage**: la soglia è 70% (vedi sopra); va alzata man mano che crescono i test,
  mantenendo il margine sotto il valore reale.
- **Nessun rollback automatico**: se un deploy va in produzione con un bug non catturato dai
  test, il fallback è il deploy manuale di una revisione precedente (`gcloud run services
  update-traffic` o un nuovo `gcloud run deploy` da un commit precedente) — procedura e
  distinzione code-only/con migrazione in
  [release-checklist.md § Rollback](release-checklist.md#10-rollback). Versioning,
  changelog e checklist di rilascio sono in
  [release-checklist.md](release-checklist.md); backup, restore e la prova periodica del
  ripristino (`restore-verification.yml`) in [backup-recovery.md](backup-recovery.md).
- **`data/incoming/`**: i batch di calciatori in staging (in attesa di
  `scripts/import_players.py`) sono in `.gitignore`, quindi solo locali: se la macchina si
  rompe si perdono. Nessun backup automatico, per scelta (non fanno parte del dataset
  ufficiale finché non sono importati).
