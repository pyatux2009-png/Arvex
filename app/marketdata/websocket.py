import asyncio
import json
import time
import logging
import websockets

logger = logging.getLogger("MarketDataWS")

class OrderBookStream:
    def __init__(self, exchange, symbols):
        self.exchange=exchange; self.symbols=[s.upper() for s in symbols]; self.task=None; self.running=False
    async def start(self):
        if self.running:return
        self.running=True; self.task=asyncio.create_task(self._run())
    async def stop(self):
        self.running=False
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass
            self.task=None
    async def _run(self):
        while self.running:
            try: await self._connect()
            except asyncio.CancelledError: break
            except Exception as exc: logger.warning("%s websocket: %s",self.exchange.__class__.__name__,exc); await asyncio.sleep(2)

class BinanceOrderBookStream(OrderBookStream):
    async def _connect(self):
        streams='/'.join(f"{s.lower()}@depth20@100ms" for s in self.symbols); url=f"wss://stream.binance.com:9443/stream?streams={streams}"
        async with websockets.connect(url,ping_interval=20,ping_timeout=20) as ws:
            async for raw in ws:
                if not self.running: break
                d=json.loads(raw).get('data',{})
                sym=d.get('s')
                if not sym: continue
                self.exchange.orderbooks[sym]={"symbol":sym,"bids":[[float(p),float(q)] for p,q in d.get('b',[]) if float(q)>0],"asks":[[float(p),float(q)] for p,q in d.get('a',[]) if float(q)>0],"timestamp":time.time(),"source":"websocket"}

class BybitOrderBookStream(OrderBookStream):
    def __init__(self,exchange,symbols):
        super().__init__(exchange,symbols); self.books={}
    @staticmethod
    def _apply(levels,updates,reverse=False):
        book={float(p):float(q) for p,q in levels}
        for p,q in updates:
            price=float(p); qty=float(q)
            if qty<=0: book.pop(price,None)
            else: book[price]=qty
        return [[p,q] for p,q in sorted(book.items(),key=lambda x:x[0],reverse=reverse)[:50]]
    async def _connect(self):
        self.books.clear()
        async with websockets.connect("wss://stream.bybit.com/v5/public/spot",ping_interval=20,ping_timeout=20) as ws:
            await ws.send(json.dumps({"op":"subscribe","args":[f"orderbook.50.{s}" for s in self.symbols]}))
            async for raw in ws:
                if not self.running: break
                msg=json.loads(raw); topic=msg.get('topic',''); d=msg.get('data',{})
                if not d or not topic: continue
                sym=topic.rsplit('.',1)[-1].upper()
                if sym not in self.symbols: continue
                if msg.get('type')=='snapshot':
                    bids=[[float(x[0]),float(x[1])] for x in d.get('b',[])]; asks=[[float(x[0]),float(x[1])] for x in d.get('a',[])]
                else:
                    old=self.books.get(sym,{"bids":[],"asks":[]}); bids=self._apply(old['bids'],d.get('b',[]),True); asks=self._apply(old['asks'],d.get('a',[]),False)
                self.books[sym]={"bids":bids,"asks":asks}
                self.exchange.orderbooks[sym]={"symbol":sym,"bids":bids,"asks":asks,"timestamp":time.time(),"source":"websocket"}
