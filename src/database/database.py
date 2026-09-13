from .connection import connect

from supabase import Client


class Database:
    def __init__(self):
        self._supabase: Client = connect()

    @property
    def connection(self) -> Client:
        return self._supabase