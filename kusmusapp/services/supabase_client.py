"""
Supabase Client Service
Initializes and provides the Supabase client for all data operations.
"""
import os
import logging
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_supabase_client: Client = None

def get_supabase() -> Client:
    """Returns the singleton Supabase client instance."""
    global _supabase_client
    if _supabase_client is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if not url or not key:
            logger.error("SUPABASE_URL and SUPABASE_KEY must be set in .env")
            raise RuntimeError("Supabase credentials not configured. Set SUPABASE_URL and SUPABASE_KEY in your .env file.")
        _supabase_client = create_client(url, key)
        logger.info("Supabase client initialized successfully.")
    return _supabase_client
