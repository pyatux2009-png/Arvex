import asyncio,time,uuid,logging
logger=logging.getLogger('OrderManager')
TERMINAL={'FILLED','PARTIALLY_FILLED','CANCELED','REJECTED','EXPIRED','UNKNOWN'}
class OrderManager:
 def __init__(self,exchanges):self.exchanges=exchanges;self.active_orders={}
 async def create_order(self,exchange_name,symbol,side,amount,price,client_order_id=None):
  ex=self.exchanges.get(exchange_name);cid=client_order_id or f'cid_{uuid.uuid4().hex[:16]}'
  if cid in self.active_orders:return self.active_orders[cid]
  if not ex:return {'order_id':None,'client_order_id':cid,'status':'REJECTED','filled_amount':0.,'remaining_amount':amount,'avg_price':0.,'reason':'Exchange adapter not found'}
  try:r=await ex.create_order(symbol,side,amount,price,cid)
  except Exception as exc:return {'order_id':None,'client_order_id':cid,'status':'UNKNOWN','filled_amount':0.,'remaining_amount':amount,'avg_price':0.,'reason':str(exc)}
  filled=float(r.get('filled_amount',0) or 0); rec={**r,'exchange':exchange_name,'client_order_id':r.get('client_order_id',cid),'requested_amount':amount,'filled_amount':filled,'remaining_amount':max(0.,amount-filled),'timestamp':r.get('timestamp',time.time())}
  self.active_orders[cid]=rec;return rec
 async def check_order_status_with_timeout(self,exchange_name,symbol,order_id,client_order_id,timeout_seconds=3.):
  ex=self.exchanges.get(exchange_name)
  if not ex:return {'order_id':order_id,'client_order_id':client_order_id,'status':'UNKNOWN','filled_amount':0.,'reason':'Exchange adapter not found'}
  deadline=time.monotonic()+timeout_seconds; last=None
  while time.monotonic()<deadline:
   try:
    last=await ex.get_order_status(symbol,order_id,client_order_id); st=last.get('status','UNKNOWN')
    if st in TERMINAL and st!='UNKNOWN':return last
   except Exception as exc:logger.warning('status check %s: %s',exchange_name,exc)
   await asyncio.sleep(.15)
  return {**(last or {}),'order_id':order_id,'client_order_id':client_order_id,'status':'UNKNOWN','timestamp':time.time(),'reason':'Timeout waiting for exchange confirmation'}
