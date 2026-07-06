# Copyright 2026 Veloxs AI Inc. All rights reserved.
#
# This file is part of Nexus, proprietary and confidential software of
# Veloxs AI Inc. Use is subject to the Nexus Proprietary Software License;
# see the LICENSE file in the project root. Unauthorized copying,
# distribution, or modification of this file, via any medium, is strictly
# prohibited.
#
# SPDX-License-Identifier: LicenseRef-Veloxs-AI-Proprietary

from __future__ import annotations

import argparse
from pathlib import Path

from nexus_security.config import load_config
from nexus_security.models import AccessRequest, Decision
from nexus_security.service import SecurityGovernanceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="security", description="Security and governance control plane."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    validate_config = commands.add_parser("validate-config", help="Load and validate a security config.")
    validate_config.add_argument("config_path", type=Path)

    check_access = commands.add_parser("check-access", help="Evaluate an RBAC access request.")
    check_access.add_argument("config_path", type=Path)
    check_access.add_argument("role")
    check_access.add_argument("permission")
    check_access.add_argument("user_tenant")
    check_access.add_argument("resource_tenant")
    check_access.add_argument("data_scope")

    encrypt = commands.add_parser("encrypt", help="Encrypt a value with the configured key.")
    encrypt.add_argument("config_path", type=Path)
    encrypt.add_argument("plaintext")

    decrypt = commands.add_parser("decrypt", help="Decrypt a value with the configured key.")
    decrypt.add_argument("config_path", type=Path)
    decrypt.add_argument("ciphertext")

    audit = commands.add_parser("audit", help="Record an audit event.")
    audit.add_argument("config_path", type=Path)
    audit.add_argument("event_type")
    audit.add_argument("actor_id")
    audit.add_argument("tenant_id")
    audit.add_argument("decision", type=Decision, choices=list(Decision))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config_path)
    service = SecurityGovernanceService(config, args.config_path.parent.parent)

    if args.command == "validate-config":
        print(f"Loaded {len(config.roles)} roles and {len(config.tenants)} tenants.")
    elif args.command == "check-access":
        decision = service.check_access(
            AccessRequest(
                role=args.role,
                permission=args.permission,
                user_tenant=args.user_tenant,
                resource_tenant=args.resource_tenant,
                data_scope=args.data_scope,
            )
        )
        print(f"allowed: {str(decision.decision == Decision.ALLOWED).lower()}")
        print(f"reason: {decision.reason}")
    elif args.command == "encrypt":
        print(service.encrypt(args.plaintext))
    elif args.command == "decrypt":
        print(service.decrypt(args.ciphertext))
    elif args.command == "audit":
        service.record_event(args.event_type, args.actor_id, args.tenant_id, args.decision)
        print("audit_event_written: true")
    return 0


def app() -> None:
    """Console-script entry point (kept for the `nexus_security.cli:app` script target)."""
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
