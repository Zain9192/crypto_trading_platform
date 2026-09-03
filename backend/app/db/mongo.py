from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import get_settings


@lru_cache
def get_mongo_client() -> MongoClient:
    settings = get_settings()
    return MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)


def get_mongo_database() -> Database:
    settings = get_settings()
    return get_mongo_client()[settings.mongo_db]
