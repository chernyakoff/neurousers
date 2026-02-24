from datetime import timedelta
from enum import IntEnum

from tortoise import fields
from tortoise import timezone as tz
from tortoise.models import Model


class Role(IntEnum):
    USER = 0
    ADMIN = 7


class User(Model):
    id = fields.BigIntField(pk=True, generated=False)
    username = fields.CharField(max_length=34, null=True, db_index=True)
    first_name = fields.CharField(null=True, max_length=64)
    last_name = fields.CharField(null=True, max_length=64)
    photo_url = fields.CharField(max_length=256, null=True)
    role = fields.IntEnumField(enum_type=Role, default=Role.USER)
    license_end_date = fields.DatetimeField(null=True)
    balance = fields.BigIntField(default=0)
    ref_code = fields.CharField(max_length=8, null=True, unique=True)
    referred_by: fields.ForeignKeyNullableRelation["User"] = fields.ForeignKeyField(
        "models.User",
        related_name="referrals",
        null=True,
        on_delete=fields.SET_NULL,
    )
    referrals: fields.ReverseRelation["User"]

    # OpenRouter user-level settings shared across projects
    or_api_key = fields.CharField(max_length=256, null=True)
    or_api_hash = fields.CharField(max_length=256, null=True)
    or_model = fields.CharField(max_length=256, null=True)

    class Meta(Model.Meta):
        table = "users"

    async def extend_license(self, days: int) -> None:
        now = tz.now()
        if self.license_end_date is None or self.license_end_date < now:
            self.license_end_date = now + timedelta(days=days)
        else:
            self.license_end_date += timedelta(days=days)
        await self.save(update_fields=["license_end_date"])

    async def add_balance(self, rubles: int) -> None:
        if rubles <= 0:
            return
        self.balance += rubles * 100
        await self.save(update_fields=["balance"])
