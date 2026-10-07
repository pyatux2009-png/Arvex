import time,logging
from typing import Dict,Any,List,Tuple
from app.arbitrage.profitability import calculate_net_profit
from app.arbitrage.scoring import evaluate_risk_level
from app.config import BOOK_MAX_AGE_SECONDS
from app.marketdata.provider import MarketDataProvider
logger=logging.getLogger('MarketScanner')
class MarketScanner(MarketDataProvider):
 def __init__(self,exchanges,max_book_age_seconds=BOOK_MAX_AGE_SECONDS):self.exchanges=exchanges;self.max_book_age_seconds=max_book_age_seconds
 async def get_order_book(self,symbol):
  books={}
  for n,e in self.exchanges.items():
   try:books[n]=await e.get_order_book(symbol)
   except Exception as exc:logger.warning('%s book: %s',n,exc)
  return books
 @staticmethod
 def calculate_vwap_and_depth(side,target_capital_usd):
  if target_capital_usd<=0:return 0.,0.,False
  remaining=target_capital_usd; qty=spent=0.
  for p,q in side:
   p=float(p);q=float(q)
   if p<=0 or q<=0:continue
   take=min(q,remaining/p); qty+=take; spent+=take*p; remaining-=take*p
   if remaining<=1e-9:break
  return (spent/qty if qty else 0.),qty,remaining<=1e-6
 @staticmethod
 def _vwap_for_qty(side,target_qty):
  rem=target_qty;qty=spent=0.
  for p,q in side:
   take=min(float(q),rem);qty+=take;spent+=take*float(p);rem-=take
   if rem<=1e-12:break
  return (spent/qty if qty else 0.),qty,rem<=1e-12
 async def scan_opportunities(self,symbol,target_capital_usd=50.0):
  now=time.time(); books={}
  for n,e in self.exchanges.items():
   try:
    ob=await e.get_order_book(symbol); age=max(0.,now-float(ob.get('timestamp',now)))
    if age<=self.max_book_age_seconds and ob.get('bids') and ob.get('asks'):books[n]=(ob,age)
   except Exception as exc:logger.debug('%s scan: %s',n,exc)
  names=list(books); out=[]
  for buy in names:
   for sell in names:
    if buy==sell:continue
    bb,ba=books[buy][0],books[buy][1]; sb,sa=books[sell][0],books[sell][1]
    buy_vwap,max_buy,_=self.calculate_vwap_and_depth(bb['asks'],target_capital_usd)
    sell_vwap,max_sell,_=self.calculate_vwap_and_depth(sb['bids'],target_capital_usd)
    qty=min(max_buy,max_sell,target_capital_usd/buy_vwap if buy_vwap else 0)
    if qty<=0:continue
    buy_vwap,_,buy_ok=self._vwap_for_qty(bb['asks'],qty);sell_vwap,_,sell_ok=self._vwap_for_qty(sb['bids'],qty)
    m=calculate_net_profit(buy_exchange=buy,sell_exchange=sell,buy_price=buy_vwap,sell_price=sell_vwap,volume=qty)
    risk=evaluate_risk_level(m['net_profit_pct'],max(ba,sa),qty*min(buy_vwap,sell_vwap))
    out.append({'symbol':symbol,'buy_exchange':buy,'sell_exchange':sell,'buy_price':buy_vwap,'sell_price':sell_vwap,'quantity':qty,'position_size':qty*buy_vwap,'liquidity_ok':buy_ok and sell_ok,'book_age':max(ba,sa),'risk_level':risk,**m,'timestamp':now})
  return sorted([x for x in out if x['net_profit_usd']>0],key=lambda x:x['net_profit_usd'],reverse=True)
