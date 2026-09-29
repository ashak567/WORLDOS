---
name: worldos-security-threat-model
description: Threat modeling, SSRF prevention, secure defaults, secrets management, and defense-in-depth engineering standards for WORLDOS based on Trail of Bits security playbooks.
---

# WORLDOS Security & Threat Modeling Playbook

WORLDOS ingests data from external networks, runs analytical computations, and exposes APIs. Because it processes untrusted external payloads, it requires strict adherence to secure defaults and proactive threat modeling based on Trail of Bits engineering standards.

---

## 1. Threat Model & Attack Vectors

| Attack Vector | Target Subsystem | Impact | Mitigation |
|---|---|---|---|
| **Server-Side Request Forgery (SSRF)** | Source Ingestion Adapters | Attacker forces adapter to query internal metadata services (`169.254.169.254`, localhost, internal DB). | Strictly whitelist allowed external domains/IPs; block private/loopback/link-local address ranges; resolve DNS and validate before connect. |
| **SQL Injection** | Database Layer / PostGIS | Unauthorized read/write/drop of world state. | Enforce parameterized queries via SQLAlchemy/asyncpg; never interpolate strings into `text("...")` or `ST_GeomFromText`. |
| **GeoJSON / XML Bomb / Resource Exhaustion** | Spatial Engine & Parsers | DoS via gigabyte-sized polygons or recursive billion-laughs XML. | Enforce request size limits (max 10MB); limit maximum polygon vertices; stream and validate incrementally. |
| **Data Poisoning & Sybil Attacks** | Entity Resolution & Fusion | Malicious actor publishes bogus reports to poison the world model. | Require registered sources with cryptographic API keys; enforce provenance; weight confidence by source reputation; quarantine unverified claims. |
| **Credential / Secret Leakage** | Repository / Logging | Leaked database passwords, cloud tokens, or API keys. | Enforce 12-factor environment variables via Pydantic `BaseSettings`; redact credentials from structured logs; run git pre-commit scanning. |

---

## 2. SSRF Prevention in Ingestion Adapters

When an adapter accepts a user-provided or configurable endpoint URL:

```python
import ipaddress
import socket
from urllib.parse import urlparse

FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Private
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Private
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Private
    ipaddress.ip_network("169.254.0.0/16"),   # Link-Local (Cloud metadata)
    ipaddress.ip_network("::1/128"),          # IPv6 Loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 Unique Local
]

def validate_outbound_url(url: str, allowed_hosts: list[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError("Invalid URL scheme")
    
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")
        
    if allowed_hosts and hostname not in allowed_hosts:
        raise ValueError(f"Host {hostname} not in registered adapter allowlist")
        
    # Resolve IP and verify not private
    try:
        ip_str = socket.gethostbyname(hostname)
        ip = ipaddress.ip_address(ip_str)
        for net in FORBIDDEN_NETWORKS:
            if ip in net:
                raise ValueError(f"Forbidden internal IP resolution: {ip}")
    except socket.gaierror:
        raise ValueError(f"Cannot resolve host: {hostname}")
        
    return True
```

---

## 3. Secure Defaults (Trail of Bits Guidelines)

- **No Hardcoded Secrets**: Default development configurations in code must not fall back to production credentials.
- **Strict Pydantic Settings**:
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict
  from pydantic import SecretStr

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")
      
      POSTGRES_USER: str = "postgres"
      POSTGRES_PASSWORD: SecretStr
      POSTGRES_DB: str = "worldos"
      SECRET_KEY: SecretStr
      ENVIRONMENT: str = "development"
  ```
  `SecretStr` prevents accidental printing or logging of passwords in traces.
- **Least Privilege Database Connections**: The web API database user must only have `SELECT, INSERT, UPDATE` on application tables. DDL migrations should run under a dedicated migration user.
- **CORS & Headers**: Set restrictive CORS headers; enforce `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, and `Content-Security-Policy`.

---

## 4. Anti-Patterns to Avoid

- **Anti-Pattern 1: Unsanitized SQL in PostGIS functions**: Doing `f"SELECT ST_GeomFromText('{user_wkt}', 4326)"` instead of passing parameters to PostGIS.
- **Anti-Pattern 2: Logging Raw Request Bodies**: Emitting full JSON payloads into logging systems where user tokens or private data might be preserved indefinitely.
- **Anti-Pattern 3: Disabling SSL Verification**: Setting `verify=False` in `httpx` or `requests` to bypass SSL certificate errors.
