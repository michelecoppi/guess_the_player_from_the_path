# Stage 1: Compila il bundle frontend (Vite + TypeScript)
FROM node:22-slim AS frontend-builder

WORKDIR /build

# Dipendenze frontend isolate per cache layer ottimale
COPY package.json package-lock.json ./
RUN npm ci

# Configurazione e sorgenti del frontend
COPY tsconfig.json vite.config.ts index.html ./
COPY webapp ./webapp

# Compila il bundle di produzione in webapp/dist/
RUN npm run build

# Stage 2: Runtime Python per il bot e le API
FROM python:3.11-slim

# I font di sistema servono alle immagini generate con Pillow (services/fonts.py): senza un
# TrueType Pillow ripiega sul font bitmap di default, che e' il motivo per cui le card
# sembravano disegnate a terminale. fonts-dejavu-core sono ~1 MB.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Copia solo gli asset compilati del frontend dallo stage di build
COPY --from=frontend-builder /build/webapp/dist ./webapp/dist

# Il processo non ha niente da scrivere sul filesystem: il dataset si legge, le immagini
# si generano in memoria e lo stato sta su Firestore. Girare come root non serve a niente,
# e toglierlo limita cosa puo' fare chi riuscisse a eseguire codice qui dentro.
RUN useradd --create-home --uid 1001 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["python", "bot.py"]
