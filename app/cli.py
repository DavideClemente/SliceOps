import asyncio

import redis.asyncio as aioredis
import typer

from app.auth.service import AuthService
from app.config import Settings

cli = typer.Typer(name="sliceops", help="SliceOps API key management CLI")


def _get_auth_service() -> tuple[aioredis.Redis, AuthService, Settings]:
    settings = Settings()
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    valid_plans = list(settings._plan_limits.keys())
    return client, AuthService(client, valid_plans=valid_plans), settings


@cli.command()
def create_key(owner: str, plan: str = "free"):
    """Create a new API key."""
    async def _run():
        client, svc, settings = _get_auth_service()
        try:
            plan_lower = plan.lower()
            try:
                settings.get_plan_limits(plan_lower)
            except KeyError:
                available = list(settings._plan_limits.keys())
                typer.echo(f"Invalid plan: {plan}. Available: {available}")
                raise typer.Exit(code=1)
            key_data = await svc.create_key(owner=owner, plan=plan_lower)
            typer.echo(f"Key:   {key_data.key}")
            typer.echo(f"Owner: {key_data.owner}")
            typer.echo(f"Plan:  {key_data.plan}")
        finally:
            await client.aclose()
    asyncio.run(_run())


@cli.command()
def list_keys():
    """List all API keys."""
    async def _run():
        client, svc, _ = _get_auth_service()
        try:
            keys = await svc.list_keys()
            if not keys:
                typer.echo("No keys found.")
                return
            for k in keys:
                status = "active" if k.active else "revoked"
                typer.echo(f"{k.key}  owner={k.owner}  plan={k.plan}  {status}")
        finally:
            await client.aclose()
    asyncio.run(_run())


@cli.command()
def revoke_key(key: str):
    """Revoke an API key."""
    async def _run():
        client, svc, _ = _get_auth_service()
        try:
            success = await svc.revoke_key(key)
            if success:
                typer.echo(f"Revoked: {key}")
            else:
                typer.echo(f"Key not found: {key}")
                raise typer.Exit(code=1)
        finally:
            await client.aclose()
    asyncio.run(_run())


if __name__ == "__main__":
    cli()
