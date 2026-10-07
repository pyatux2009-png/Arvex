import asyncio,time,logging
logger=logging.getLogger('RecoveryEngine')
class RecoveryEngine:
 def __init__(self,exchanges=None,max_recovery_time_seconds=5.):self.exchanges=exchanges or {};self.max_recovery_time_seconds=max_recovery_time_seconds
 async def handle_exposure(self,position_id,exchange,symbol,amount,side):
  ex=self.exchanges.get(exchange)
  if not ex or amount<=0:return {'position_id':position_id,'status':'UNRESOLVED','filled_amount':0.,'realized_pnl':0.,'reason':'No recovery adapter or invalid amount'}
  close_side='sell' if side.lower()=='buy' else 'buy'; cid=f'recovery_{position_id[:12]}_{uuid4_short()}'
  try:
   ob=await ex.get_order_book(symbol); levels=ob.get('bids' if close_side=='sell' else 'asks',[])
   if not levels:return {'position_id':position_id,'status':'UNRESOLVED','filled_amount':0.,'reason':'No executable recovery liquidity'}
   price=float(levels[0][0]); r=await ex.create_order(symbol,close_side,amount,price,cid); filled=float(r.get('filled_amount',0) or 0); status=r.get('status','UNKNOWN')
   if status in {'SUBMITTED','NEW'}:
    deadline=time.monotonic()+self.max_recovery_time_seconds
    while time.monotonic()<deadline:
     await asyncio.sleep(.15); r=await ex.get_order_status(symbol,r.get('order_id'),r.get('client_order_id',cid)); status=r.get('status','UNKNOWN');filled=float(r.get('filled_amount',filled) or 0)
     if status not in {'SUBMITTED','NEW','UNKNOWN'}:break
   if status=='FILLED' and filled>=amount:return {'position_id':position_id,'status':'RECOVERED','filled_amount':filled,'closing_order':r}
   if filled>0 and status=='PARTIALLY_FILLED':return {'position_id':position_id,'status':'PARTIAL_RECOVERY','filled_amount':filled,'remaining_amount':max(0,amount-filled),'closing_order':r}
   return {'position_id':position_id,'status':'UNRESOLVED' if status=='UNKNOWN' else 'FAILED','filled_amount':filled,'reason':f'Recovery status: {status}','closing_order':r}
  except Exception as exc:
   logger.exception('Recovery failed');return {'position_id':position_id,'status':'UNRESOLVED','filled_amount':0.,'realized_pnl':0.,'reason':str(exc)}
 async def handle_single_leg_exposure(self,position_id='legacy',exchange=None,symbol='',amount=0.,side='buy',success_exchange=None,bought_price=None,exchanges=None):
  if exchanges is not None:self.exchanges=exchanges
  return await self.handle_exposure(position_id,exchange or success_exchange,symbol,amount,side)
def uuid4_short():
 import uuid
 return uuid.uuid4().hex[:8]
