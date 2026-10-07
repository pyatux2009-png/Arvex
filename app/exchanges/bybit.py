import hashlib,hmac,json,time,uuid,os
from typing import Dict,Any,Optional
from app.exchanges.base import BaseExchange
from app.exchanges.http import request_json

class BybitExchange(BaseExchange):
    REST="https://api.bybit.com"
    def __init__(self,api_key=None,api_secret=None,paper_mode=True,testnet=False,market_data_live=False):
        self.api_key=api_key or os.getenv("BYBIT_API_KEY"); self.api_secret=api_secret or os.getenv("BYBIT_API_SECRET"); self.paper_mode=paper_mode; self.testnet=testnet; self.market_data_live=market_data_live
        if testnet:self.REST="https://api-testnet.bybit.com"
        self.orderbooks={}; self.orders={}; self.balances={"USDT":10000.0,"BTC":1.0,"ETH":10.0} if paper_mode else {}
    def _paper_default_book(self,symbol):
        return {"symbol":symbol,"bids":[[99.0,10.0],[98.0,50.0]],"asks":[[100.0,10.0],[101.0,50.0]],"timestamp":time.time(),"source":"paper"}

    def _headers(self,method,path,params=None,body=None):
        ts=str(int(time.time()*1000)); recv="5000"; payload=json.dumps(body,separators=(",",":"),ensure_ascii=False) if body else ""
        if method=="GET": query="&".join(f"{k}={v}" for k,v in sorted((params or {}).items())); sign=ts+self.api_key+recv+query
        else: sign=ts+self.api_key+recv+payload
        sig=hmac.new(self.api_secret.encode(),sign.encode(),hashlib.sha256).hexdigest()
        return {"X-BAPI-API-KEY":self.api_key,"X-BAPI-SIGN":sig,"X-BAPI-SIGN-TYPE":"2","X-BAPI-TIMESTAMP":ts,"X-BAPI-RECV-WINDOW":recv,"Content-Type":"application/json"}
    def _require(self):
        if not self.api_key or not self.api_secret: raise ValueError("Bybit API credentials missing")
    async def get_balance(self):
        if self.paper_mode:return dict(self.balances)
        self._require(); p={"accountType":"UNIFIED"}; d=await request_json("GET",self.REST+"/v5/account/wallet-balance",params=p,headers=self._headers("GET","/v5/account/wallet-balance",p)); self._ok(d); out={}
        for c in d["result"]["list"][0].get("coin",[]): out[c["coin"]]=float(c.get("walletBalance",0)); return out
    async def get_order_book(self,symbol):
        symbol=symbol.upper()
        if symbol in self.orderbooks:return self.orderbooks[symbol]
        if self.paper_mode and not self.market_data_live:
            return self._paper_default_book(symbol)
        d=await request_json("GET",self.REST+"/v5/market/orderbook",params={"category":"spot","symbol":symbol,"limit":50}); self._ok(d); r=d["result"]
        ob={"symbol":symbol,"bids":[[float(x[0]),float(x[1])] for x in r["b"]],"asks":[[float(x[0]),float(x[1])] for x in r["a"]],"timestamp":time.time(),"source":"rest"}; self.orderbooks[symbol]=ob; return ob
    async def create_order(self,symbol,side,amount,price,client_order_id=None):
        if self.paper_mode:return await self._paper_order(symbol,side,amount,price,client_order_id)
        self._require(); cid=client_order_id or f"arb_{uuid.uuid4().hex[:20]}"; body={"category":"spot","symbol":symbol.upper(),"side":side.capitalize(),"orderType":"Limit","qty":self._fmt(amount),"price":self._fmt(price),"timeInForce":"IOC","orderLinkId":cid}
        d=await request_json("POST",self.REST+"/v5/order/create",data=json.dumps(body,separators=(",",":")),headers=self._headers("POST","/v5/order/create",body=body)); self._ok(d); oid=d["result"].get("orderId"); return {"order_id":oid,"client_order_id":cid,"exchange":"bybit","symbol":symbol,"side":side,"requested_amount":amount,"filled_amount":0.0,"remaining_amount":amount,"avg_price":0.0,"status":"SUBMITTED","timestamp":time.time(),"raw":d}
    async def get_order_status(self,symbol,order_id=None,client_order_id=None):
        if self.paper_mode:
            if client_order_id in self.orders:return self.orders[client_order_id]
            if order_id in self.orders:return self.orders[order_id]
            return {"order_id":order_id,"client_order_id":client_order_id,"status":"UNKNOWN","filled_amount":0.0,"remaining_amount":0.0,"avg_price":0.0,"timestamp":time.time()}
        self._require(); p={"category":"spot","symbol":symbol.upper()};
        if order_id:p["orderId"]=order_id
        elif client_order_id:p["orderLinkId"]=client_order_id
        d=await request_json("GET",self.REST+"/v5/order/realtime",params=p,headers=self._headers("GET","/v5/order/realtime",p)); self._ok(d); lst=d["result"].get("list",[])
        if not lst:return {"order_id":order_id,"client_order_id":client_order_id,"status":"UNKNOWN","filled_amount":0.0,"remaining_amount":0.0,"avg_price":0.0,"timestamp":time.time()}
        x=lst[0]; return self._normalize(x,symbol)
    async def cancel_order(self,symbol,order_id=None,client_order_id=None):
        if self.paper_mode:
            key=client_order_id or order_id
            if key in self.orders:self.orders[key]["status"]="CANCELED"; return self.orders[key]
            return {"status":"UNKNOWN","order_id":order_id,"client_order_id":client_order_id}
        self._require(); body={"category":"spot","symbol":symbol.upper()}; body["orderId"]=order_id if order_id else None; body["orderLinkId"]=client_order_id if not order_id else None; body={k:v for k,v in body.items() if v is not None}
        d=await request_json("POST",self.REST+"/v5/order/cancel",data=json.dumps(body,separators=(",",":")),headers=self._headers("POST","/v5/order/cancel",body=body)); self._ok(d); return {"status":"CANCELED","order_id":d["result"].get("orderId"),"client_order_id":client_order_id,"timestamp":time.time()}
    async def _paper_order(self,symbol,side,amount,price,client_order_id=None):
        cid=client_order_id or f"bybit_paper_{uuid.uuid4().hex[:12]}"; oid=f"paper_{uuid.uuid4().hex[:12]}"
        ob=await self.get_order_book(symbol); side=side.lower(); limit=float(price); rem=float(amount); filled=0.0; notional=0.0
        levels=ob["asks"] if side=="buy" else ob["bids"]
        for p,q in levels:
            p=float(p); q=float(q)
            if side=="buy" and p>limit: break
            if side=="sell" and p<limit: break
            take=min(rem,q)
            if take<=0: continue
            filled+=take; notional+=take*p; rem-=take
            if rem<=1e-12: break
        status="REJECTED" if filled<=0 else ("FILLED" if rem<=1e-12 else "PARTIALLY_FILLED"); avg=notional/filled if filled else 0.0
        fee_rate=0.001; fee=notional*fee_rate; base=symbol.upper().replace("USDT","") if symbol.upper().endswith("USDT") else symbol.upper(); quote="USDT" if symbol.upper().endswith("USDT") else None
        if status!="REJECTED" and quote:
            if side=="buy":
                required=notional+fee
                if self.balances.get(quote,0.0)+1e-9<required: status="REJECTED"; filled=0.0; rem=float(amount); notional=0.0; avg=0.0; fee=0.0
                else: self.balances[quote]-=required; self.balances[base]=self.balances.get(base,0.0)+filled
            else:
                if self.balances.get(base,0.0)+1e-9<filled: status="REJECTED"; filled=0.0; rem=float(amount); notional=0.0; avg=0.0; fee=0.0
                else: self.balances[base]-=filled; self.balances[quote]=self.balances.get(quote,0.0)+notional-fee
        r={"order_id":oid,"client_order_id":cid,"exchange":"bybit","symbol":symbol,"side":side,"requested_amount":amount,"filled_amount":filled,"remaining_amount":rem,"avg_price":avg,"status":status,"fee_usd":fee if status!="REJECTED" else 0.0,"timestamp":time.time()}
        self.orders[cid]=r; self.orders[oid]=r; return r

    def _normalize(self,x,symbol):
        mp={"New":"SUBMITTED","PartiallyFilled":"PARTIALLY_FILLED","Filled":"FILLED","Cancelled":"CANCELED","Rejected":"REJECTED","Deactivated":"EXPIRED"}; filled=float(x.get("cumExecQty",0)); avg=float(x.get("avgPrice",0) or 0); qty=float(x.get("qty",0)); return {"order_id":x.get("orderId"),"client_order_id":x.get("orderLinkId"),"exchange":"bybit","symbol":symbol,"side":x.get("side","" ).lower(),"requested_amount":qty,"filled_amount":filled,"remaining_amount":max(0,qty-filled),"avg_price":avg,"status":mp.get(x.get("orderStatus"),"UNKNOWN"),"timestamp":time.time(),"raw":x}
    @staticmethod
    def _ok(d):
        if d.get("retCode",0)!=0: raise RuntimeError(f"Bybit error {d.get('retCode')}: {d.get('retMsg')}")
    @staticmethod
    def _fmt(v):return format(float(v),'.16f').rstrip('0').rstrip('.')
