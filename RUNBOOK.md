# Diagnostic case record

Copy this template for each investigation. Label simulated cases explicitly.

- **Environment:** testnet/mainnet, expected chain ID, date/time UTC, Python version.
- **Symptom:** exact observed behavior; what the user expected.
- **Scope:** one wallet/app/provider or multiple? What is still unknown?
- **Reproduction:** command and public test inputs; omit provider credentials.
- **Evidence:** sanitized JSON from two providers; explorer observations and timestamps.
- **Hypothesis:** separate observations from inferred causes.
- **Next action:** provider/network comparison, input check, or escalation with evidence.
- **Retest:** command, observed result, and whether the original symptom changed.
- **Limitations:** provider visibility, sequential queries, clock skew, finality/reorg uncertainty.

## Suggested reproducible cases

1. **Wrong network (deliberate configuration error):** query BSC testnet with expected chain ID 56. The tool should stop after detecting 97. Retest with expected 97.
2. **Unavailable endpoint (simulation):** point to an unused local port. Expect a transport error without credential-bearing URL details. This demonstrates error handling, not a public provider outage.
3. **Provider comparison:** compare block heights/timestamps from two live providers. Explain normal sequential-query differences; do not call small differences a synchronization failure.
4. **Failed inclusion:** use an actual public testnet failed transaction and capture the receipt status. Determine the failure reason separately; status 0 alone cannot establish out-of-gas or a particular revert reason.
