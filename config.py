from dotenv import load_dotenv
import os

load_dotenv()  # charge automatiquement .env

API_KEY = os.getenv("API_KEY")
ACCOUNT_ID = os.getenv("ACCOUNT_ID")

TOKEN = os.getenv("TOKEN")
TELEGRAM_USER = os.getenv("TELEGRAM_USER")

APP_URL = os.getenv("APP_URL")
PORT = os.getenv("PORT")

RISK_FACTOR = float(os.getenv("RISK_FACTOR", 0.01))
