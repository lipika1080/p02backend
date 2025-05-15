from pymongo import MongoClient
import os

def get_db():
    mongo_uri = os.getenv("COSMOS_MONGO_URI")
    if not mongo_uri:
        raise ValueError("COSMOS_MONGO_URI environment variable is not set.")
    client = MongoClient(mongo_uri)
    db_name = os.getenv("COSMOS_DBNAME")
    if not db_name:
        raise ValueError("COSMOS_DBNAME environment variable is not set.")
    return client[db_name]
