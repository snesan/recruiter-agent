#!/usr/bin/env python3
import argparse
from pathlib import Path


def render(template_path: Path, output_path: Path, replacements: dict[str, str]) -> None:
    content = template_path.read_text()
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    unresolved = sorted({word for word in content.split('"') if word.startswith("REPLACE_")})
    if unresolved:
        raise SystemExit(f"Unresolved placeholders in {template_path}: {', '.join(unresolved)}")
    output_path.write_text(content)


parser = argparse.ArgumentParser(description="Render AWS deployment JSON files.")
parser.add_argument("--account-id", required=True)
parser.add_argument("--region", required=True)
parser.add_argument("--execution-role-arn", required=True)
parser.add_argument("--openai-secret-arn", required=True)
parser.add_argument("--google-secret-arn", required=True)
args = parser.parse_args()

project_root = Path(__file__).resolve().parents[1]
aws_directory = project_root / "deployment" / "aws"
replacements = {
    "REPLACE_AWS_ACCOUNT_ID": args.account_id,
    "REPLACE_AWS_REGION": args.region,
    "REPLACE_EXECUTION_ROLE_ARN": args.execution_role_arn,
    "REPLACE_OPENAI_SECRET_ARN": args.openai_secret_arn,
    "REPLACE_GOOGLE_SECRET_ARN": args.google_secret_arn,
}

render(
    aws_directory / "task-definition.template.json",
    aws_directory / "task-definition.json",
    replacements,
)
render(
    aws_directory / "secrets-policy.template.json",
    aws_directory / "secrets-policy.json",
    replacements,
)
print(f"Rendered AWS files in {aws_directory}")
