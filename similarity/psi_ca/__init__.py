"""PSI-CA (private set intersection cardinality) via OpenMined PSI (ECDH, semi-honest).

Two roles exchange only serialized protocol messages (blinded curve points), never plaintext
identifiers. Only the client (the designated output party) learns |X ∩ Y|; both sides learn
the other's set size. This is an unreviewed integration of an established library: no
cryptographic claim beyond the library's own threat model is made here.
"""
from __future__ import annotations

from collections.abc import Iterable

import private_set_intersection.python as psi

PROTOCOL = "psi_ca/openmined-ecdh/2.0.6"
# RAW gives exact cardinality; GCS/Bloom trade a false-positive rate for smaller messages.
_DATA_STRUCTURE = psi.DataStructure.RAW
_FPR = 1e-9


def _items(values: Iterable[str]) -> list[str]:
    items = sorted(set(values))
    if not items:
        raise ValueError("PSI-CA input set must be non-empty")
    return items


class PsiCaServer:
    """The non-output party. Never learns the intersection or its size."""

    def __init__(self, values: Iterable[str]):
        self._items = _items(values)
        self._server = psi.server.CreateWithNewKey(False)  # reveal_intersection=False

    def setup_message(self, num_client_inputs: int) -> bytes:
        setup = self._server.CreateSetupMessage(_FPR, num_client_inputs, self._items, _DATA_STRUCTURE)
        return setup.SerializeToString()

    def process_request(self, request: bytes) -> bytes:
        req = psi.Request()
        req.ParseFromString(request)
        return self._server.ProcessRequest(req).SerializeToString()


class PsiCaClient:
    """The designated output party. Learns only the intersection cardinality."""

    def __init__(self, values: Iterable[str]):
        self._items = _items(values)
        self._client = psi.client.CreateWithNewKey(False)

    @property
    def size(self) -> int:
        return len(self._items)

    def request_message(self) -> bytes:
        return self._client.CreateRequest(self._items).SerializeToString()

    def cardinality(self, setup: bytes, response: bytes) -> int:
        s, r = psi.ServerSetup(), psi.Response()
        s.ParseFromString(setup)
        r.ParseFromString(response)
        return int(self._client.GetIntersectionSize(s, r))
