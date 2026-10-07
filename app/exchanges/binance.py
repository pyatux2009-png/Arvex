import hashlib, hmac, time, uuid, os, urllib.parse
from typing import Dict, Any, Optional
from app.exchanges.base import BaseExchange
from app.exchanges.http import request_json

class BinanceExchange(BaseExchange):
    REST = "https://api.binance.com"
    WS = "wss://stream.binance.com:9443/ws"
    def __init__(self, api_key=None, api_secret=None, paper_mode=True, testnet=False, market_data_live=False):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.paper_mode = paper_mode
        self.testnet = testnet
        self.market_data_live = market_data_live
        if testnet: self.REST = "https://testnet.binance.vision"
        self.orderbooks={}; self.orders={}
        self.balances={"USDT":10000.0,"BTC":1.0,"ETH":10.0} if paper_mode else {}
    def _signed(self, params):
        p=dict(params); p["timestamp"]=int(time.time()*1000); p.setdefault("recvWindow",5000)
        qs=urllib.parse.urlencode(p)
        p["signature"]=hmac.new(self.api_secret.encode(),qs.encode(),hashlib.sha256).hexdigest(); return p
    async def get_balance(self):
        if self.paper_mode: return dict(self.balances)
        self._require_auth()
        data=await request_json("GET",self.REST+"/api/v3/account",params=self._signed({}),headers={"X-MBX-APIKEY":self.api_key})
        return {x["asset"]:float(x["free"])+float(x["locked"]) for x in data.get("balances",[])}
    async def get_order_book(self,symbol):
        symbol=symbol.upper()
        if symbol in self.orderbooks: return self.orderbooks[symbol]
        if self.paper_mode and not self.market_data_live:
            return self._paper_default_book(symbol)
        data=await request_json("GET",self.REST+"/api/v3/depth",params={"symbol":symbol,"limit":100})
        ob={"symbol":symbol,"bids":[[float(p),float(q)] for p,q in data["bids"]],"asks":[[float(p),float(q)] for p,q in data["asks"]],"timestamp":time.time(),"source":"rest"}
        self.orderbooks[symbol]=ob; return ob
    def _paper_default_book(self,symbol):
        return {"symbol":symbol,"bids":[[99.0,10.0],[98.0,50.0]],"asks":[[100.0,10.0],[101.0,50.0]],"timestamp":time.time(),"source":"paper"}

    def _require_auth(self):
        if not self.api_key or not self.api_secret: raise ValueError("Binance API credentials missing")
    async def create_order(self,symbol,side,amount,price,client_order_id=None):
        if self.paper_mode: return await self._paper_order(symbol,side,amount,price,client_order_id)
        self._require_auth(); cid=client_order_id or f"arb_{uuid.uuid4().hex[:20]}"
        params={"symbol":symbol.upper(),"side":side.upper(),"type":"LIMIT","timeInForce":"IOC","quantity":self._fmt(amount),"price":self._fmt(price),"newClientOrderId":cid}
        data=await request_json("POST",self.REST+"/api/v3/order",params=self._signed(params),headers={"X-MBX-APIKEY":self.api_key})
        return self._normalize_live(data,symbol,side,amount,cid)
    async def get_order_status(self,symbol,order_id=None,client_order_id=None):
        if self.paper_mode:
            if client_order_id in self.orders: return self.orders[client_order_id]
            if order_id in self.orders: return self.orders[order_id]
            return {"order_id":order_id,"client_order_id":client_order_id,"status":"UNKNOWN","filled_amount":0.0,"remaining_amount":0.0,"avg_price":0.0,"timestamp":time.time()}
        self._require_auth(); p={"symbol":symbol.upper()}; p["orderId"]=order_id if order_id else None; p["origClientOrderId"]=client_order_id if not order_id else None; p={k:v for k,v in p.items() if v is not None}
        data=await request_json("GET",self.REST+"/api/v3/order",params=self._signed(p),headers={"X-MBX-APIKEY":self.api_key})
        return self._normalize_live(data,symbol,data.get("side","BUY").lower(),float(data.get("origQty",0)),data.get("clientOrderId"))
    async def cancel_order(self,symbol,order_id=None,client_order_id=None):
        if self.paper_mode:
            key=client_order_id or order_id
            if key in self.orders: self.orders[key]["status"]="CANCELED"; return self.orders[key]
            return {"status":"UNKNOWN","order_id":order_id,"client_order_id":client_order_id}
        self._require_auth(); p={"symbol":symbol.upper()}; p["orderId"]=order_id if order_id else None; p["origClientOrderId"]=client_order_id if not order_id else None; p={k:v for k,v in p.items() if v is not None}
        data=await request_json("DELETE",self.REST+"/api/v3/order",params=self._signed(p),headers={"X-MBX-APIKEY":self.api_key})
        return self._normalize_live(data,symbol,data.get("side","BUY").lower(),float(data.get("origQty",0)),data.get("clientOrderId"))
    async def _paper_order(self,symbol,side,amount,price,client_order_id=None):
        cid=client_order_id or f"binance_paper_{uuid.uuid4().hex[:12]}"; oid=f"paper_{uuid.uuid4().hex[:12]}"
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
        r={"order_id":oid,"client_order_id":cid,"exchange":"binance","symbol":symbol,"side":side,"requested_amount":amount,"filled_amount":filled,"remaining_amount":rem,"avg_price":avg,"status":status,"fee_usd":fee if status!="REJECTED" else 0.0,"timestamp":time.time()}
        self.orders[cid]=r; self.orders[oid]=r; return r

    def _normalize_live(self,d,symbol,side,amount,cid):
        status_map={"NEW":"SUBMITTED","PARTIALLY_FILLED":"PARTIALLY_FILLED","FILLED":"FILLED","CANCELED":"CANCELED","REJECTED":"REJECTED","EXPIRED":"EXPIRED"}
        filled=float(d.get("executedQty",0)); avg=float(d.get("cummulativeQuoteQty",0))/filled if filled else 0
        return {"order_id":str(d.get("orderId")) if d.get("orderId") is not None else None,"client_order_id":d.get("clientOrderId") or cid,"exchange":"binance","symbol":symbol,"side":side,"requested_amount":amount,"filled_amount":filled,"remaining_amount":max(0,amount-filled),"avg_price":avg,"status":status_map.get(d.get("status"),"UNKNOWN"),"timestamp":time.time(),"raw":d}
    @staticmethod
    def _fmt(v): return format(float(v),'.16f').rstrip('0').rstrip('.')
