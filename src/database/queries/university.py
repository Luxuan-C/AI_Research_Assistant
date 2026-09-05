from ..database import Database
from ..query import Query


class University:
    def __init__(self, database: Database):
        self.__database = database
        self.__table = "university"

    def __get_field_by_id(self, field: str, id: int):
        """
        Retrieves the value of a field based on the University record's ID.
        """
        return Query.get_data(
            self.__database,
            self.__table,
            select=field,
            filters={ "id": id }
        )

    def get_name(self, id: int):
        """
        Retrieves a University's name based on its ID.
        """
        return self.__get_field_by_id("name", id)

    def get_country_code(self, id: int):
        """
        Retrieves a University's country code based on its ID.
        """
        return self.__get_field_by_id("country_code", id)

    def get_ror_url(self, id: int):
        """
        Retrieves a University's ror url based on its ID.
        """
        return self.__get_field_by_id("ror_url", id)

    def get_type(self, id: int):
        """
        Retrieves a University's type based on its ID.
        """
        return self.__get_field_by_id("type", id)
