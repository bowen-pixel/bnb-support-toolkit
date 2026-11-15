# BNB Support Toolkit

A learning project for technical support diagnostics on BNB Smart Chain and EVM-compatible RPC providers. Python 3.10+, no third-party packages. Initial prototype; no claim of production deployment or real user support.

## What it does

- **RPC health:** verifies expected chain ID, reads latest block height/timestamp, measures the whole probe's latency, and compares providers for relative height lag and block-age warnings.
- **Transaction triage:** distinguishes provider-visible pending, not found, included success/failure, and receipt inconsistency. Inclusion is not finality; a missing transaction is not proof it was dropped.
- **Wallet snapshot:** reads native balance and confirmed/pending nonces, with interpretation notes. No wallet connection, private key, signing, or transaction submission.
- **Support evidence:** produces timestamped JSON with provider labels, transport/RPC errors, and next investigation steps. URLs and wallet/hash inputs are not copied into output. Chain data can still be identifying; review reports before sharing.

## Run

```sh
export BSC_RPC_A='https://bsc-testnet-dataseed.bnbchain.org'
export BSC_RPC_B='https://bsc-testnet.bnbchain.org'
python3 support_toolkit.py --rpc-env BSC_RPC_A --rpc-env BSC_RPC_B health
python3 support_toolkit.py --rpc-env BSC_RPC_A --chain-id 56 health  # deliberate wrong-network check
python3 support_toolkit.py --rpc-env BSC_RPC_A tx 0xYOUR_64_HEX_CHARACTER_TRANSACTION_HASH
python3 support_toolkit.py --rpc-env BSC_RPC_A wallet 0xYOUR_40_HEX_CHARACTER_PUBLIC_ADDRESS
python3 -m unittest -v
```

Replace the example hash/address with public test data. Public providers receive your query and network metadata. Keep private provider URLs in environment variables; avoid putting credentials in screenshots or shell history. Default expected chain ID is 97 (BSC testnet); mainnet is 56. The commands use HTTP POST for read RPC methods.

On macOS, a standalone Python installation may lack CA certificates. If the tool reports TLS verification failure, configure a trusted CA bundle (for this machine, `export SSL_CERT_FILE=/etc/ssl/cert.pem` worked). Keep certificate verification enabled.

Use `health --max-age 60 --max-lag 10` to customize warnings. Defaults are diagnostic heuristics, not BNB service-level targets. Comparisons are sequential, so small height differences are normal. A fast-responding provider is not necessarily accurate or fully synchronized. Two providers can both be stale; this tool does not establish canonical chain state.

Exit status: 1 for errors, wrong network, health warnings, failed inclusion, or unavailable receipt; 0 otherwise. Pending/not-found transactions remain inconclusive findings and return 0. JSON `state` is the authoritative classification, not the exit code alone.

## Support workflow

1. Ask for the network, public transaction hash, symptom, and timestamp. Never request seed phrases or private keys.
2. Run `health` against two providers on the same expected network. Check transport errors, chain mismatch, block age, and relative lag.
3. Run `tx` to distinguish pending/not-found from included failure. Compare another provider before drawing conclusions.
4. If relevant, run `wallet` to inspect native balance and nonce observations. A positive balance alone does not prove that a transaction is affordable. Nonce deltas are not exact pending-transaction counts.
5. Record expected/actual behavior, commands, sanitized output, hypothesis, next action, and retest. Follow [RUNBOOK.md](RUNBOOK.md).

## Portfolio milestones

- [x] Initial CLI and automated offline tests.
- [ ] Personally reproduce the diagnostics and explain each RPC method.
- [x] Record a live testnet health report and one deliberately wrong-network report (see `examples/`).
- [ ] Diagnose a real testnet pending or failed transaction, preserving evidence and limitations.
- [ ] Add a Telegram `/status` bot with timeout handling, rate limiting, and redacted logs.
- [ ] Add a Telegram Mini App separately if implemented; a bot is not a Mini App.

Do not claim community moderation, node operation, incident response, or deployed Telegram support based on this prototype. Before using resume bullets, run the project, review the code, reproduce the results, and be ready to explain it.

## References

- [BNB JSON-RPC endpoints](https://docs.bnbchain.org/bnb-smart-chain/developers/json_rpc/json-rpc-endpoint/)
- [BNB wallet configuration](https://docs.bnbchain.org/bnb-smart-chain/developers/wallet-configuration/)
- [Ethereum JSON-RPC method reference](https://ethereum.org/developers/docs/apis/json-rpc/)
