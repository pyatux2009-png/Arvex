import os
from dataclasses import dataclass

def _float_env(name, default):
    try:return float(os.getenv(name,str(default)))
    except (TypeError,ValueError):return default

def _bool_env(name,default=False):return os.getenv(name,str(default)).strip().lower() in {'1','true','yes','on'}

EXCHANGE_FEES={
 'binance':{'maker':_float_env('BINANCE_MAKER_FEE',0.001),'taker':_float_env('BINANCE_TAKER_FEE',0.001)},
 'bybit':{'maker':_float_env('BYBIT_MAKER_FEE',0.001),'taker':_float_env('BYBIT_TAKER_FEE',0.001)},
}
TRADING_MODE=os.getenv('TRADING_MODE','PAPER').upper(); LIVE_TRADING=TRADING_MODE=='LIVE'
MAX_TRADE_SIZE_USD=_float_env('MAX_TRADE_SIZE_USD',100.0); MAX_DAILY_LOSS_USD=_float_env('MAX_DAILY_LOSS_USD',5.0)
MIN_NET_PROFIT_USD=_float_env('MIN_NET_PROFIT_USD',0.05); MIN_NET_PROFIT_PCT=_float_env('MIN_NET_PROFIT_PCT',0.10)
MAX_SLIPPAGE_PCT=_float_env('MAX_SLIPPAGE_PCT',0.20); BOOK_MAX_AGE_SECONDS=_float_env('BOOK_MAX_AGE_SECONDS',2.0)
OTHER_COSTS_USD=_float_env('OTHER_COSTS_USD',0.0)
DATABASE_URL=os.getenv('DATABASE_URL','sqlite+aiosqlite:///./crypto_arb.db')
SYMBOLS=[s.strip().upper() for s in os.getenv('SYMBOLS','BTCUSDT,ETHUSDT,SOLUSDT').split(',') if s.strip()]
BINANCE_TESTNET=_bool_env('BINANCE_TESTNET'); BYBIT_TESTNET=_bool_env('BYBIT_TESTNET')

@dataclass(frozen=True)
class Settings:
 trading_mode:str=TRADING_MODE; live_trading:bool=LIVE_TRADING; database_url:str=DATABASE_URL
 max_trade_size_usd:float=MAX_TRADE_SIZE_USD; max_daily_loss_usd:float=MAX_DAILY_LOSS_USD
 min_net_profit_usd:float=MIN_NET_PROFIT_USD; min_net_profit_pct:float=MIN_NET_PROFIT_PCT
 max_slippage_pct:float=MAX_SLIPPAGE_PCT; book_max_age_seconds:float=BOOK_MAX_AGE_SECONDS; other_costs_usd:float=OTHER_COSTS_USD
 symbols:tuple=tuple(SYMBOLS)
 binance_testnet:bool=BINANCE_TESTNET
 bybit_testnet:bool=BYBIT_TESTNET
 @property
 def max_daily_loss(self):return self.max_daily_loss_usd
 @property
 def max_position_usd(self):return self.max_trade_size_usd
settings=Settings()
