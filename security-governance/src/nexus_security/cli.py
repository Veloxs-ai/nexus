from __future__ import annotations

from pathlib import Path

import typer

from nexus_security.config import load_config
from nexus_security.models import AccessRequest, Decision
from nexus_security.service import SecurityGovernanceService

app = typer.Typer(help="Security and governance control plane.")


@app.command()
def validate_config(config_path: Path) -> None:
    config = load_config(config_path)
    typer.echo(f"Loaded {len(config.roles)} roles and {len(config.tenants)} tenants.")


@app.command()
def check_access(
    config_path: Path,
    role: str,
    permission: str,
    user_tenant: str,
    resource_tenant: str,
    data_scope: str,
) -> None:
    config = load_config(config_path)
    service = SecurityGovernanceService(config, config_path.parent.parent)
    decision = service.check_access(
        AccessRequest(
            role=role,
            permission=permission,
            user_tenant=user_tenant,
            resource_tenant=resource_tenant,
            data_scope=data_scope,
        )
    )
    typer.echo(f"allowed: {str(decision.decision == Decision.ALLOWED).lower()}")
    typer.echo(f"reason: {decision.reason}")


@app.command()
def encrypt(config_path: Path, plaintext: str) -> None:
    config = load_config(config_path)
    service = SecurityGovernanceService(config, config_path.parent.parent)
    typer.echo(service.encrypt(plaintext))


@app.command()
def decrypt(config_path: Path, ciphertext: str) -> None:
    config = load_config(config_path)
    service = SecurityGovernanceService(config, config_path.parent.parent)
    typer.echo(service.decrypt(ciphertext))


@app.command()
def audit(config_path: Path, event_type: str, actor_id: str, tenant_id: str, decision: Decision) -> None:
    config = load_config(config_path)
    service = SecurityGovernanceService(config, config_path.parent.parent)
    service.record_event(event_type, actor_id, tenant_id, decision)
    typer.echo("audit_event_written: true")


if __name__ == "__main__":
    app()
