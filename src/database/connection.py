from dotenv import load_dotenv
from supabase import create_client, Client
import os

load_dotenv()

def connect() -> Client:
    """
    Creates a Supabase database Client.
    """
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")

    return create_client(url, key)


