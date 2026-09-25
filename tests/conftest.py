"""Test setup. Tests ALWAYS use a local, throwaway database, never the Atlas URI from .env."""

import os

import pytest
from pymongo import AsyncMongoClient, MongoClient

TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "mongodb://localhost:27017")
TEST_DB_NAME = "dental_app_test"

if "mongodb.net" in TEST_MONGODB_URI or TEST_MONGODB_URI.startswith("mongodb+srv"):
    raise RuntimeError("Refusing to run tests against a cloud database. Use the local Mongo.")

# Environment variables win over .env, so the app under test also uses the test database.
# Set before any app module is imported by the test files.
os.environ["MONGODB_URI"] = TEST_MONGODB_URI
os.environ["MONGODB_DB_NAME"] = TEST_DB_NAME


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Each test starts with fresh rate-limit counters."""
    from app.core.rate_limit import reset_rate_limits

    reset_rate_limits()


@pytest.fixture
def client():
    """HTTP client for the real app, on a clean test database."""
    from fastapi.testclient import TestClient

    from app.main import app

    with MongoClient(TEST_MONGODB_URI, serverSelectionTimeoutMS=3000) as mongo:
        mongo.drop_database(TEST_DB_NAME)
        with TestClient(app) as test_client:
            yield test_client
        mongo.drop_database(TEST_DB_NAME)


@pytest.fixture
async def db():
    """A clean test database for each test."""
    client = AsyncMongoClient(TEST_MONGODB_URI, serverSelectionTimeoutMS=3000, tz_aware=True)
    await client.drop_database(TEST_DB_NAME)
    yield client[TEST_DB_NAME]
    await client.drop_database(TEST_DB_NAME)
    await client.close()
