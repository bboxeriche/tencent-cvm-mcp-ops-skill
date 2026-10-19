"""Offline behavior checks. SDK models are real; API clients are always mocked."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_instances_template", ROOT / "tencent-cvm-mcp-ops/references/run_instances_template.py"
)
template = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(template)


def parameters():
    return {
        "Placement": {"Zone": "ap-guangzhou-6"},
        "ImageId": "img-example",
        "InstanceType": "EXAMPLE.SMALL1",
        "VirtualPrivateCloud": {"VpcId": "vpc-example", "SubnetId": "subnet-example"},
        "SystemDisk": {"DiskType": "CLOUD_PREMIUM", "DiskSize": 50},
        "InstanceChargeType": "PREPAID",
        "InstanceChargePrepaid": {"Period": 1, "RenewFlag": "NOTIFY_AND_MANUAL_RENEW"},
        "InstanceCount": 1,
        "ClientToken": "offline-test-only",
    }


class PurchaseBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.request = Path(self.temp.name) / "request.local.json"
        self.write(parameters())

    def write(self, data):
        self.request.write_text(json.dumps(data), encoding="utf-8")

    def test_mode_defaults_to_dryrun(self):
        args = template.parse_args(["--request-json", str(self.request)])
        self.assertEqual(args.mode, "dryrun")

    def test_unknown_mode_never_creates_client(self):
        with patch.object(template, "create_client") as factory, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                template.main(["dryurn", "--request-json", str(self.request)])
            self.assertEqual(raised.exception.code, 2)
            factory.assert_not_called()

    def test_real_requires_confirmation_before_any_api_request(self):
        with patch.object(template, "create_client") as factory, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                template.main(["real", "--request-json", str(self.request)])
            factory.assert_not_called()

    def test_nested_sdk_models_serialize(self):
        request = template.build_request(parameters(), dry_run=True)
        payload = json.loads(request.to_json_string())
        self.assertEqual(payload["Placement"]["Zone"], "ap-guangzhou-6")
        self.assertEqual(payload["VirtualPrivateCloud"]["VpcId"], "vpc-example")
        self.assertEqual(payload["InstanceChargePrepaid"]["Period"], 1)
        self.assertTrue(payload["DryRun"])

    def test_request_file_cannot_turn_off_dryrun(self):
        data = parameters()
        data["DryRun"] = False
        client = Mock()
        client.RunInstances.return_value.RequestId = "offline-request-id"
        template.execute(client, data)
        client.RunInstances.assert_called_once()
        self.assertTrue(client.RunInstances.call_args.args[0].DryRun)
        self.assertFalse(data["DryRun"])

    def test_real_preflights_then_submits_same_parameters_once(self):
        client = Mock()
        preflight = Mock(RequestId="offline-dryrun-id")
        result = Mock()
        result.to_json_string.return_value = '{"RequestId":"offline-create-id","InstanceIdSet":["ins-example"]}'
        client.RunInstances.side_effect = [preflight, result]
        template.execute(client, parameters(), real=True)
        self.assertEqual(client.RunInstances.call_count, 2)
        before, after = [json.loads(c.args[0].to_json_string()) for c in client.RunInstances.call_args_list]
        self.assertTrue(before.pop("DryRun"))
        self.assertFalse(after.pop("DryRun"))
        self.assertEqual(before, after)

    def test_failed_preflight_blocks_purchase_and_is_not_retried(self):
        client = Mock()
        client.RunInstances.side_effect = TencentCloudSDKException("InvalidParameter", "offline failure")
        with self.assertRaises(TencentCloudSDKException):
            template.execute(client, parameters(), real=True)
        client.RunInstances.assert_called_once()
        self.assertTrue(client.RunInstances.call_args.args[0].DryRun)

    def test_missing_preflight_request_id_blocks_purchase(self):
        client = Mock()
        client.RunInstances.return_value.RequestId = None
        with self.assertRaises(ValueError):
            template.execute(client, parameters(), real=True)
        client.RunInstances.assert_called_once()

    def test_uncertain_create_is_not_retried(self):
        client = Mock()
        client.RunInstances.side_effect = [
            Mock(RequestId="offline-dryrun-id"),
            TencentCloudSDKException("ClientNetworkError", "offline timeout"),
        ]
        with self.assertRaises(TencentCloudSDKException):
            template.execute(client, parameters(), real=True)
        self.assertEqual(client.RunInstances.call_count, 2)

    def test_placeholder_request_is_rejected_before_client_creation(self):
        example = ROOT / "tencent-cvm-mcp-ops/references/run_instances_request.example.json"
        with patch.object(template, "create_client") as factory, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(template.main(["--request-json", str(example)]), 1)
            factory.assert_not_called()

    def test_real_requires_idempotency_token(self):
        data = parameters()
        del data["ClientToken"]
        self.write(data)
        with self.assertRaises(ValueError):
            template.load_parameters(self.request, real=True)

    def test_prepaid_requires_purchase_period(self):
        data = parameters()
        del data["InstanceChargePrepaid"]
        self.write(data)
        with self.assertRaises(ValueError):
            template.load_parameters(self.request)

    def test_missing_credentials_fail_without_cloud_calls(self):
        with patch.dict(template.os.environ, {}, clear=True), patch.object(template.cvm_client, "CvmClient") as factory:
            with self.assertRaises(ValueError):
                template.create_client()
            factory.assert_not_called()

    def test_credentials_are_taken_from_environment(self):
        env = {
            "TENCENTCLOUD_SECRET_ID": "offline-id",
            "TENCENTCLOUD_SECRET_KEY": "offline-key",
            "TENCENTCLOUD_REGION": "ap-guangzhou",
            "TENCENTCLOUD_TOKEN": "offline-session-token",
        }
        with patch.dict(template.os.environ, env, clear=True), patch.object(template.cvm_client, "CvmClient") as factory:
            template.create_client()
            creds, region, profile = factory.call_args.args
            self.assertEqual(creds.secretId, env["TENCENTCLOUD_SECRET_ID"])
            self.assertEqual(creds.token, env["TENCENTCLOUD_TOKEN"])
            self.assertEqual(region, "ap-guangzhou")
            self.assertEqual(profile.httpProfile.endpoint, "cvm.tencentcloudapi.com")


if __name__ == "__main__":
    unittest.main()
