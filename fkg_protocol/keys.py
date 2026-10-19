"""Ed25519 service identities. Each service holds its own private key and a keyring of public keys."""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

SERVICES = ("registry", "persona_a", "persona_b", "persona_c", "persona_d")


def load_private(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    return key


class Keyring:
    """Public keys by service id, loaded from <dir>/<service_id>.pem."""

    def __init__(self, keys: dict[str, Ed25519PublicKey]):
        self._keys = dict(keys)

    @classmethod
    def from_dir(cls, directory: Path) -> "Keyring":
        keys = {}
        for pem in sorted(directory.glob("*.pem")):
            key = serialization.load_pem_public_key(pem.read_bytes())
            if isinstance(key, Ed25519PublicKey):
                keys[pem.stem] = key
        return cls(keys)

    def get(self, service_id: str) -> Ed25519PublicKey | None:
        return self._keys.get(service_id)

    def __contains__(self, service_id: str) -> bool:
        return service_id in self._keys


def generate(private_dirs: dict[str, Path], public_dir: Path) -> list[str]:
    """Create any missing key pairs. Each private key goes only to its own directory."""
    created = []
    public_dir.mkdir(parents=True, exist_ok=True)
    for service, directory in private_dirs.items():
        directory.mkdir(parents=True, exist_ok=True)
        priv_path = directory / "private.pem"
        if not priv_path.exists():
            key = Ed25519PrivateKey.generate()
            priv_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
            priv_path.chmod(0o600)
            created.append(service)
        key = load_private(priv_path)
        (public_dir / f"{service}.pem").write_bytes(key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    return created
