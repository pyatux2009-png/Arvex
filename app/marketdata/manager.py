from app.marketdata.websocket import (
    BinanceOrderBookStream,
    BybitOrderBookStream,
    KrakenOrderBookStream,
    OkxOrderBookStream,
)


class MarketDataManager:
    def __init__(self, exchanges, symbols):
        self.streams = []
        if "binance" in exchanges:
            self.streams.append(BinanceOrderBookStream(exchanges["binance"], symbols))
        if "bybit" in exchanges:
            self.streams.append(BybitOrderBookStream(exchanges["bybit"], symbols))
        if "okx" in exchanges:
            self.streams.append(OkxOrderBookStream(exchanges["okx"], symbols))
        if "kraken" in exchanges:
            self.streams.append(KrakenOrderBookStream(exchanges["kraken"], symbols))

    async def start(self):
        for stream in self.streams:
            await stream.start()

    async def stop(self):
        for stream in self.streams:
            await stream.stop()
