import os
import sys

# I test del negozio firmano una quota di pagamento (services/shop.py), e per firmarla
# serve BOT_TOKEN. Senza questa riga il token arriva dal .env locale, che e' gitignorato:
# i test passano sulla macchina di chi ce l'ha e falliscono in CI, che il .env non ce l'ha.
# E' il tipo di test che da' un verde bugiardo, quindi il valore va fissato qui.
#
# Va prima di qualunque import di config: config.py legge BOT_TOKEN una volta sola,
# all'import, e load_dotenv() non sovrascrive quello che sta gia' nell'ambiente - quindi
# questa riga vince sul .env e la firma e' la stessa ovunque giri la suite.
os.environ.setdefault("BOT_TOKEN", "test-bot-token")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
