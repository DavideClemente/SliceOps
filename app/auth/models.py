from pydantic import BaseModel

Plan = str


class ApiKeyData(BaseModel):
    key: str
    owner: str
    plan: str
    active: bool
    created_at: str
