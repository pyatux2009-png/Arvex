import asyncio
import logging
from app.runtime import get_runtime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Main")


async def main():
    runtime = get_runtime()
    logger.info("Crypto Arb Bot starting")
    await runtime.start()
    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
