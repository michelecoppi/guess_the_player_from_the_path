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

EXPOSE 8000

CMD ["python", "bot.py"]
