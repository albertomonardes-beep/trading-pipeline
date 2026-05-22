from pymongo import MongoClient
import os

MONGODB_URI = os.environ.get("MONGODB_URI")
DB_NAME = "trading"

def get_db():
    client = MongoClient(MONGODB_URI)
    return client[DB_NAME]

def setup_collections():
    db = get_db()

    if "tickers" not in db.list_collection_names():
        db.create_collection("tickers")
        db.tickers.create_index("ticker", unique=True)
        print("Coleccion 'tickers' creada")

    if "market_data" not in db.list_collection_names():
        db.create_collection("market_data")
        db.market_data.create_index("ticker", unique=True)
        print("Coleccion 'market_data' creada")

    if "weekly_snapshot" not in db.list_collection_names():
        db.create_collection("weekly_snapshot")
        db.weekly_snapshot.create_index("ticker", unique=True)
        print("Coleccion 'weekly_snapshot' creada")

    print("Base de datos lista")

if __name__ == "__main__":
    setup_collections()
