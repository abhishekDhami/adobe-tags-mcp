from dataclasses import dataclass

from app.clients import ApiClient


@dataclass(slots=True)
class AppContext:
    api: ApiClient
