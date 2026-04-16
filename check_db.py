import asyncio
import motor.motor_asyncio
from config import MONGO_URI, MONGO_DB

async def run():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]
    docs = await db.residents.find({}).to_list(10)
    print("Found Residents:", docs)

if __name__ == "__main__":
    asyncio.run(run())
