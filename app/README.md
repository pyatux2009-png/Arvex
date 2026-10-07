# Crypto Arbitrage Bot

Backend for cross-exchange spot arbitrage (Binance & Bybit) written in Python (FastAPI, WebSockets, SQLite, CCXT-ready).

## Quickstart (Windows/Linux)
1. Install requirements: `pip install -r requirements.txt`
2. Copy `.env.example` to `.env`
3. Run app: `uvicorn app.main:app --reload`