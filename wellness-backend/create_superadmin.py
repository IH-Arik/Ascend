import asyncio
import os
import sys

sys.path.append(os.getcwd())

from app.core.security import get_password_hash
from app.db.mongodb import init_db
from app.models.user import User


ACCOUNTS = [
    {
        "email": "superadmin.demo.supertest@example.com",
        "password": "SuperAdmin123!",
        "name": "Demo Superadmin",
        "organization_name": "Dominion Wellness Solutions",
        "role": "superadmin",
    },
    {
        "email": "leader.new.demo@example.com",
        "password": "Leader@1234",
        "name": "Demo Admin Lead",
        "organization_name": "Dominion Wellness Solutions",
        "role": "Admin Lead",
    },
]


async def ensure_account(account: dict[str, str]) -> None:
    existing = await User.find_one({"email": account["email"]})
    hashed_password = get_password_hash(account["password"])

    if existing is None:
        user = User(
            email=account["email"],
            hashed_password=hashed_password,
            name=account["name"],
            organization_name=account["organization_name"],
            role=account["role"],
            is_active=True,
            is_verified=True,
            onboarding_completed=True,
        )
        await user.insert()
        print(f"Created {account['role']} account: {account['email']}")
        return

    existing.hashed_password = hashed_password
    existing.name = account["name"]
    existing.organization_name = account["organization_name"]
    existing.role = account["role"]
    existing.is_active = True
    existing.is_verified = True
    existing.onboarding_completed = True
    await existing.save()
    print(f"Updated {account['role']} account: {account['email']}")


async def create_admin_accounts() -> None:
    await init_db()
    for account in ACCOUNTS:
        await ensure_account(account)


if __name__ == "__main__":
    asyncio.run(create_admin_accounts())
