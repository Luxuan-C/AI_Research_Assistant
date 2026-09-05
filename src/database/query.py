from database.database import Database

from typing import Any


class Query:
    @staticmethod
    def get_data(
            database: Database,
            table: str,
            select: str = "*",
            filters: dict[str, Any] | None = None       # { "id": 17 }, filter for id == 17
    ):
        """
        Retrieves data from the database.
        """
        query = (
            database.connection
            .table(table)
            .select(select)
        )

        # add filters
        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)

        response = query.execute()

        return response.data
