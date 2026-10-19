"""Phase 1 smoke check: the PSI-CA library runs in the agent image and returns exact counts.

Uses throwaway sets (not fixture data). Prints one JSON line for the host-side test.
Run: docker compose exec -T agent_a python -m similarity.psi_ca.smoke
"""
from __future__ import annotations

import json

from similarity.psi_ca import PROTOCOL, PsiCaClient, PsiCaServer

CASES = [
    ("partial", [f"SMOKE-{i:04d}" for i in range(0, 40)], [f"SMOKE-{i:04d}" for i in range(25, 70)], 15),
    ("disjoint", ["SMOKE-X1", "SMOKE-X2"], ["SMOKE-Y1", "SMOKE-Y2", "SMOKE-Y3"], 0),
    ("identical", ["SMOKE-Z1", "SMOKE-Z2", "SMOKE-Z3"], ["SMOKE-Z1", "SMOKE-Z2", "SMOKE-Z3"], 3),
]


def run() -> dict:
    results = []
    for name, client_set, server_set, expected in CASES:
        client, server = PsiCaClient(client_set), PsiCaServer(server_set)
        setup = server.setup_message(client.size)
        request = client.request_message()
        response = server.process_request(request)
        wire = setup + request + response
        results.append({
            "case": name,
            "expected": expected,
            "cardinality": client.cardinality(setup, response),
            # No plaintext identifier from either side may appear in any protocol message.
            "plaintext_on_wire": any(v.encode() in wire for v in client_set + server_set),
        })
    return {"protocol": PROTOCOL, "results": results}


if __name__ == "__main__":
    print(json.dumps(run()))
