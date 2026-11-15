import io
import json
import ssl
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from support_toolkit import DiagnosticError, RpcClient, compare_health, health, transaction, wallet

HASH = "0x" + "a" * 64
ADDRESS = "0x" + "b" * 40


class FakeRpc:
    def __init__(self, values):
        self.values = values
        self.calls = []

    def call(self, method, params):
        self.calls.append((method, params))
        return self.values[method]


class DiagnosticsTests(unittest.TestCase):
    def test_health_wrong_chain_stops_before_other_calls(self):
        rpc = FakeRpc({"eth_chainId": "0x38"})
        self.assertEqual(health(rpc, 97)["state"], "wrong_network")
        self.assertEqual(len(rpc.calls), 1)

    def test_health_reports_lag_and_stale_block(self):
        reports = [health(FakeRpc({"eth_chainId": "0x61", "eth_getBlockByNumber":
                    {"number": hex(h), "timestamp": hex(t)}}), 97, now=1000)
                   for h, t in [(100, 990), (80, 900)]]
        compare_health(reports, 60, 10)
        self.assertEqual([r["state"] for r in reports], ["ok", "warning"])
        self.assertEqual(reports[1]["relative_lag_blocks"], 20)

    def test_all_failures_do_not_produce_healthy_result(self):
        self.assertEqual(compare_health([{"state": "error"}], 60, 10), [{"state": "error"}])

    def test_not_found_does_not_claim_dropped(self):
        rpc = FakeRpc({"eth_chainId": "0x61", "eth_getTransactionReceipt": None,
                       "eth_getTransactionByHash": None})
        result = transaction(rpc, HASH, 97)
        self.assertEqual(result["state"], "not_found")
        self.assertIn("does not prove", result["next_step"])

    def test_pending_and_receipt_inconsistency(self):
        for block, expected in [(None, "pending"), ("0x10", "receipt_unavailable")]:
            rpc = FakeRpc({"eth_chainId": "0x61", "eth_getTransactionReceipt": None,
                           "eth_getTransactionByHash": {"blockNumber": block}})
            self.assertEqual(transaction(rpc, HASH, 97)["state"], expected)

    def test_failed_receipt_and_success_are_distinct(self):
        for status, expected in [("0x0", "included_failed"), ("0x1", "included_success")]:
            rpc = FakeRpc({"eth_chainId": "0x61", "eth_getTransactionReceipt":
                           {"status": status, "blockNumber": "0x10"}, "eth_blockNumber": "0x12"})
            result = transaction(rpc, HASH, 97)
            self.assertEqual(result["state"], expected)
            self.assertEqual(result["observed_confirmations"], 3)

    def test_wallet_preserves_large_integer_balance(self):
        rpc = FakeRpc({"eth_chainId": "0x61", "eth_getBalance": hex(10**24 + 1),
                       "eth_getTransactionCount": "0x2"})
        result = wallet(rpc, ADDRESS, 97)
        self.assertEqual(result["native_balance_wei"], str(10**24 + 1))
        self.assertEqual(rpc.calls[-2:], [("eth_getTransactionCount", [ADDRESS, "latest"]),
                                          ("eth_getTransactionCount", [ADDRESS, "pending"])])

    def test_bad_input_never_reaches_provider(self):
        rpc = FakeRpc({})
        with self.assertRaises(DiagnosticError):
            transaction(rpc, "bad-hash", 97)
        with self.assertRaises(DiagnosticError):
            wallet(rpc, "bad-address", 97)
        self.assertEqual(rpc.calls, [])

    def test_transport_errors_do_not_leak_provider_url(self):
        for error in [URLError("secret-key"), HTTPError("secret-key", 429, "rate limit", {}, None)]:
            with patch("support_toolkit.urlopen", side_effect=error):
                with self.assertRaises(DiagnosticError) as ctx:
                    RpcClient("https://example.org/secret-key").call("eth_chainId", [])
                self.assertNotIn("secret-key", str(ctx.exception))

    def test_tls_certificate_error_has_specific_guidance(self):
        with patch("support_toolkit.urlopen", side_effect=URLError(ssl.SSLCertVerificationError("certificate"))):
            with self.assertRaisesRegex(DiagnosticError, "CA bundle"):
                RpcClient("https://example.org").call("eth_chainId", [])

    def test_rpc_validates_envelope_and_error(self):
        responses = [b"not json", b"[]", b'{"jsonrpc":"2.0","id":99,"result":"0x61"}',
                     b'{"jsonrpc":"2.0","id":1,"error":{"code":-32601}}',
                     b'{"jsonrpc":"2.0","id":1,"result":null,"error":{}}']
        for raw in responses:
            with self.subTest(raw=raw), patch("support_toolkit.urlopen", return_value=io.BytesIO(raw)):
                with self.assertRaises(DiagnosticError):
                    RpcClient("https://example.org").call("eth_chainId", [])

    def test_rpc_sends_read_method_and_accepts_matching_response(self):
        with patch("support_toolkit.urlopen", return_value=io.BytesIO(
                b'{"jsonrpc":"2.0","id":1,"result":"0x61"}')) as transport:
            self.assertEqual(RpcClient("https://example.org").call("eth_chainId", []), "0x61")
            self.assertEqual(json.loads(transport.call_args.args[0].data)["method"], "eth_chainId")


if __name__ == "__main__":
    unittest.main()
