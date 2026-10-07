from app.marketdata.websocket import BinanceOrderBookStream,BybitOrderBookStream
class MarketDataManager:
    def __init__(self,exchanges,symbols):
        self.streams=[]
        if 'binance' in exchanges:self.streams.append(BinanceOrderBookStream(exchanges['binance'],symbols))
        if 'bybit' in exchanges:self.streams.append(BybitOrderBookStream(exchanges['bybit'],symbols))
    async def start(self):
        for s in self.streams: await s.start()
    async def stop(self):
        for s in self.streams: await s.stop()
