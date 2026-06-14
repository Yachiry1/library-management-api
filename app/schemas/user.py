from datetime import datetime
from uuid import UUID

from pydantic import EmailStr

from app.schemas.common import OrmModel


class UserRead(OrmModel):
    id: UUID
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime
