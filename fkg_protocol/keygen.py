"""One-shot key provisioning for the local stack (run by the `keygen` compose service).

Writes each service's private key only into that service's own volume (owned by its uid, mode 0600)
and every public key into the shared keyring. Existing keys are kept.
"""
from __future__ import annotations

import os
from pathlib import Path

from .keys import SERVICES, generate

OUT = Path(os.environ.get("KEYGEN_OUT", "/out"))
# uid of the process that must read each private key (see registry/agent Dockerfiles).
OWNERS = {"registry": 10001, **{p: 10002 for p in SERVICES if p != "registry"}}


def main() -> None:
    created = generate({s: OUT / s for s in SERVICES}, OUT / "public")
    for service in SERVICES:
        for path in (OUT / service, OUT / service / "private.pem"):
            os.chown(path, OWNERS[service], OWNERS[service])
        (OUT / service).chmod(0o700)
    for pem in (OUT / "public").glob("*.pem"):
        pem.chmod(0o644)
    print(f"keys ready; newly generated: {created or 'none'}")


if __name__ == "__main__":
    main()
