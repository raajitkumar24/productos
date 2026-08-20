# Security policy

## Supported version

ProductOS is currently an early-stage project. Security fixes target the latest version on the default branch.

## Reporting a vulnerability

Do not open a public issue containing vulnerability details, credentials, customer data, or exploit material. Use GitHub's private vulnerability reporting feature for this repository. If that feature is unavailable, contact the repository owner through the private contact method listed on the GitHub profile.

Include the affected version, reproduction steps, impact, and any suggested mitigation. Remove secrets and personal or company-sensitive data from the report.

## Deployment boundary

The default local profile deliberately disables authentication and uses fixed development identities. Never expose that profile to a network or connect it to enterprise systems.

Before production deployment, operators must at minimum:

- enable and validate OIDC authentication and tenant claim mappings;
- use PostgreSQL with migrations and tenant-scoped access controls;
- inject model, embedding, judge, MCP, and workload credentials through a secret manager;
- terminate TLS and restrict CORS, ingress, egress, and scheduler access;
- review data retention, logs, traces, evaluation datasets, backups, and deletion procedures;
- use short-lived scoped tokens for scheduler and connector workloads;
- verify source permissions before ingestion and retrieval;
- perform threat modeling, dependency scanning, and an independent security review.

ProductOS does not claim that the example Docker or Kubernetes configuration is production-hardened.
