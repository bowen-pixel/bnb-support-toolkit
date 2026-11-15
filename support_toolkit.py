"""Read-only EVM JSON-RPC diagnostics. Python 3.10+, standard library only."""
import argparse
import json
import os
import re
import ssl
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class DiagnosticError(Exception):
    pass


def quantity(value):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise DiagnosticError("Invalid RPC hex quantity")
    return int(value, 16)


class RpcClient:
    def __init__(self, url, timeout=8):
        parsed = urlparse(url)
        if parsed.scheme not in ("https", "http") or not parsed.hostname:
            raise DiagnosticError("RPC URL must be an HTTP(S) URL")
        if timeout <= 0:
            raise DiagnosticError("Timeout must be positive")
        self.url, self.timeout, self.request_id = url, timeout, 0

    def call(self, method, params):
        self.request_id += 1
        payload = {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params}
        req = Request(self.url, json.dumps(payload).encode(),
                      {"Content-Type": "application/json", "User-Agent": "bnb-support-toolkit/0.1"})
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
        except HTTPError as exc:
            raise DiagnosticError(f"HTTP {exc.code}: check provider access/rate limits") from None
        except URLError as exc:
            if isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise DiagnosticError("TLS certificate verification failed: check the Python CA bundle; do not disable verification") from None
            raise DiagnosticError("RPC transport failed: check connectivity, TLS, endpoint, or timeout") from None
        except (TimeoutError, OSError):
            # Provider URLs can contain credentials; do not echo transport exceptions.
            raise DiagnosticError("RPC transport failed: check connectivity, TLS, endpoint, or timeout") from None
        if len(raw) > 2_000_000:
            raise DiagnosticError("RPC response exceeded size limit")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeError):
            raise DiagnosticError("RPC returned invalid JSON") from None
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or data.get("id") != self.request_id:
            raise DiagnosticError("Invalid JSON-RPC envelope or response ID")
        if ("error" in data) == ("result" in data):
            raise DiagnosticError("RPC must return exactly one of result/error")
        if "error" in data:
            err = data["error"]
            code = err.get("code", "unknown") if isinstance(err, dict) else "unknown"
            raise DiagnosticError(f"RPC error {code}: consult provider documentation")
        return data["result"]


def health(client, expected_chain, now=None):
    start = time.monotonic()
    chain = quantity(client.call("eth_chainId", []))
    if chain != expected_chain:
        return {"state": "wrong_network", "expected_chain_id": expected_chain, "chain_id": chain}
    block = client.call("eth_getBlockByNumber", ["latest", False])
    if not isinstance(block, dict):
        raise DiagnosticError("Latest block unavailable")
    height, stamp = quantity(block.get("number")), quantity(block.get("timestamp"))
    now = time.time() if now is None else now
    age = round(now - stamp, 1)
    return {"state": "responding", "chain_id": chain, "block_height": height,
            "block_age_seconds": age, "probe_latency_ms": round((time.monotonic() - start) * 1000, 1)}


def compare_health(reports, max_age, max_lag):
    heights = [r["block_height"] for r in reports if r.get("state") == "responding"]
    highest = max(heights, default=0)
    for report in reports:
        if report.get("state") == "responding":
            report["relative_lag_blocks"] = highest - report["block_height"]
            report["state"] = "warning" if (report["block_age_seconds"] > max_age or
                report["block_age_seconds"] < -30 or report["relative_lag_blocks"] > max_lag) else "ok"
    return reports


def transaction(client, tx_hash, expected_chain):
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
        raise DiagnosticError("Transaction hash must be 0x plus 64 hex characters")
    chain = quantity(client.call("eth_chainId", []))
    if chain != expected_chain:
        return {"state": "wrong_network", "chain_id": chain, "expected_chain_id": expected_chain}
    receipt = client.call("eth_getTransactionReceipt", [tx_hash])
    if receipt is not None:
        if not isinstance(receipt, dict):
            raise DiagnosticError("Invalid transaction receipt")
        status = quantity(receipt.get("status"))
        if status not in (0, 1):
            raise DiagnosticError("Unexpected receipt status")
        tip = quantity(client.call("eth_blockNumber", []))
        height = quantity(receipt.get("blockNumber"))
        return {"state": "included_success" if status else "included_failed", "block_height": height,
                "observed_confirmations": max(0, tip - height + 1),
                "next_step": "Check block explorer and application logs; inclusion is not finality." if status else
                "Inspect contract inputs and execution trace; status alone does not explain the failure."}
    tx = client.call("eth_getTransactionByHash", [tx_hash])
    if tx is None:
        return {"state": "not_found", "next_step": "Verify network/hash and query a second provider; absence does not prove it was dropped."}
    if not isinstance(tx, dict):
        raise DiagnosticError("Invalid transaction object")
    if tx.get("blockNumber") is not None:
        return {"state": "receipt_unavailable", "next_step": "Provider has an included transaction but no receipt; retry or compare another provider."}
    return {"state": "pending", "next_step": "Compare providers and inspect sender nonce/fees; do not infer the root cause from pending status alone."}


def wallet(client, address, expected_chain):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise DiagnosticError("Address must be 0x plus 40 hex characters")
    chain = quantity(client.call("eth_chainId", []))
    if chain != expected_chain:
        return {"state": "wrong_network", "chain_id": chain, "expected_chain_id": expected_chain}
    balance = quantity(client.call("eth_getBalance", [address, "latest"]))
    latest = quantity(client.call("eth_getTransactionCount", [address, "latest"]))
    pending = quantity(client.call("eth_getTransactionCount", [address, "pending"]))
    return {"state": "snapshot", "native_balance_wei": str(balance), "confirmed_nonce": latest,
            "pending_nonce": pending, "pending_nonce_delta": pending - latest,
            "notes": ["Zero native balance cannot pay ordinary gas fees." if balance == 0 else
                      "Positive balance does not establish sufficient funds for a particular transaction.",
                      "Nonce counts are sequential provider observations, not an atomic snapshot or exact mempool count."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-env", action="append", required=True, help="Environment variable containing RPC URL; repeat to compare providers")
    parser.add_argument("--chain-id", type=int, default=97, help="Expected chain ID (default BSC testnet: 97)")
    parser.add_argument("--timeout", type=float, default=8)
    sub = parser.add_subparsers(dest="command", required=True)
    hp = sub.add_parser("health")
    hp.add_argument("--max-age", type=float, default=60, help="Configurable warning threshold in seconds")
    hp.add_argument("--max-lag", type=int, default=10, help="Relative block-height warning threshold")
    sub.add_parser("tx").add_argument("hash")
    sub.add_parser("wallet").add_argument("address")
    args = parser.parse_args()
    if args.timeout <= 0 or args.chain_id <= 0:
        parser.error("timeout and chain-id must be positive")
    if args.command == "health" and (args.max_age < 0 or args.max_lag < 0):
        parser.error("health thresholds must be non-negative")
    reports = []
    for index, env in enumerate(args.rpc_env, 1):
        report = {"provider": f"provider_{index}"}
        try:
            if not os.environ.get(env):
                raise DiagnosticError("RPC environment variable is unset")
            client = RpcClient(os.environ[env], args.timeout)
            result = health(client, args.chain_id) if args.command == "health" else (
                transaction(client, args.hash, args.chain_id) if args.command == "tx" else
                wallet(client, args.address, args.chain_id))
            report.update(result)
        except DiagnosticError as exc:
            report.update(state="error", message=str(exc))
        reports.append(report)
    if args.command == "health":
        compare_health(reports, args.max_age, args.max_lag)
    print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(),
                      "command": args.command, "reports": reports}, indent=2))
    bad = {"error", "warning", "wrong_network", "included_failed", "receipt_unavailable"}
    return int(any(r["state"] in bad for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
