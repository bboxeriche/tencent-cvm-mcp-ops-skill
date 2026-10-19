"""CVM 中国站创建模板：默认预检，正式购买需要明确选择 real 和确认开关。

凭据只从环境变量读取。--request-json 指向与示例相同结构的本地请求文件。
运行前先按 SKILL.md 询价并核对用户授权；脚本不选择或保证使用特定代金券。
"""

import argparse
import json
import os
import sys
from pathlib import Path

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.cvm.v20170312 import cvm_client, models


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", choices=("dryrun", "real"), default="dryrun")
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--confirm-purchase", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "real" and not args.confirm_purchase:
        parser.error("real requires --confirm-purchase after explicit purchase authorization")
    return args


def _has_placeholder(value):
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(v) for v in value)
    return isinstance(value, str) and value.startswith("<") and value.endswith(">")


def load_parameters(path, *, real=False):
    parameters = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("Request JSON must be a non-empty object")
    if _has_placeholder(parameters):
        raise ValueError("Replace all example placeholders before making an API request")
    if parameters.get("InstanceChargeType") not in ("PREPAID", "POSTPAID_BY_HOUR"):
        raise ValueError("Specify InstanceChargeType: PREPAID or POSTPAID_BY_HOUR")
    count = parameters.get("InstanceCount", 1)
    if type(count) is not int or count < 1:
        raise ValueError("InstanceCount must be a positive integer")
    if parameters["InstanceChargeType"] == "PREPAID":
        prepaid = parameters.get("InstanceChargePrepaid")
        if not isinstance(prepaid, dict) or type(prepaid.get("Period")) is not int or prepaid["Period"] < 1:
            raise ValueError("PREPAID requires InstanceChargePrepaid.Period in months")
    if real:
        token = parameters.get("ClientToken")
        if not isinstance(token, str) or not token or not token.isascii() or len(token) > 64:
            raise ValueError("real requires a non-empty ClientToken of at most 64 ASCII characters")
    return parameters


def build_request(parameters, *, dry_run):
    # from_json_string creates the nested SDK model objects needed for serialization.
    payload = dict(parameters)
    payload["DryRun"] = dry_run
    request = models.RunInstancesRequest()
    request.from_json_string(json.dumps(payload))
    return request


def create_client():
    names = ("TENCENTCLOUD_SECRET_ID", "TENCENTCLOUD_SECRET_KEY", "TENCENTCLOUD_REGION")
    missing = [name for name in names if not os.environ.get(name)]
    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))
    creds = credential.Credential(
        os.environ[names[0]], os.environ[names[1]], os.environ.get("TENCENTCLOUD_TOKEN")
    )
    http_profile = HttpProfile()
    http_profile.endpoint = "cvm.tencentcloudapi.com"
    profile = ClientProfile()
    profile.httpProfile = http_profile
    return cvm_client.CvmClient(creds, os.environ[names[2]], profile)


def execute(client, parameters, *, real=False):
    preflight = client.RunInstances(build_request(parameters, dry_run=True))
    if not preflight.RequestId:
        raise ValueError("DryRun response has no RequestId; purchase stopped")
    if not real:
        return {"mode": "dryrun", "RequestId": preflight.RequestId}
    # No automatic retries: an uncertain result must be reconciled before resubmission.
    result = client.RunInstances(build_request(parameters, dry_run=False))
    return {"mode": "real", "response": json.loads(result.to_json_string())}


def main(argv=None):
    args = parse_args(argv)
    try:
        parameters = load_parameters(args.request_json, real=args.mode == "real")
        result = execute(create_client(), parameters, real=args.mode == "real")
    except TencentCloudSDKException as exc:
        print(json.dumps({"error": exc.get_code(), "message": exc.get_message()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
