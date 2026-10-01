"""Deploy this project to a free Hugging Face Space (Docker).

    pip install huggingface_hub
    python scripts/deploy_hf.py --user YOUR_HF_USERNAME --token hf_xxx

Get a token (type "Write") at https://huggingface.co/settings/tokens.
Optional secrets are read from your environment or .env and stored in the Space, never in the code:
  GROQ_API_KEY      (optional) AI reading of messy invoices
  CONTACT_EMAIL / CONTACT_WHATSAPP   where landing-page buttons send people
Your demo link will be:  https://YOUR_HF_USERNAME-docuflow.hf.space
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SPACE = "docuflow"
HEADER = """---
title: DocuFlow - Invoices to Excel
emoji: 🧾
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8001
pinned: false
short_description: Upload invoices, bills and forms. Get a clean Excel sheet.
---

"""
SECRETS = ["GROQ_API_KEY", "CONTACT_EMAIL", "CONTACT_WHATSAPP"]
IGNORE = [".venv/*", ".venv/**", "data/*", "data/**", ".env", "**/__pycache__/**", "*.pyc", ".git/*", ".git/**"]


def read_env_file() -> dict:
    out = {}
    env = BASE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True, help="your Hugging Face username")
    ap.add_argument("--token", default=os.getenv("HF_TOKEN"), help="Hugging Face write token (or set HF_TOKEN)")
    ap.add_argument("--space", default=SPACE, help="Space name")
    args = ap.parse_args()
    if not args.token:
        raise SystemExit("Please pass --token hf_... (create one at https://huggingface.co/settings/tokens, type: Write)")
    from huggingface_hub import HfApi
    api = HfApi(token=args.token)
    repo_id = f"{args.user}/{args.space}"
    url = f"https://{args.user.lower()}-{args.space.lower()}.hf.space"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "space"
        shutil.copytree(BASE, dst, ignore=shutil.ignore_patterns(".venv", "data", ".env", "__pycache__", ".git"))
        readme = dst / "README.md"
        readme.write_text(HEADER + readme.read_text())
        api.upload_folder(folder_path=str(dst), repo_id=repo_id, repo_type="space", ignore_patterns=IGNORE,
                          commit_message="Deploy from local project")

    env = {**read_env_file(), **os.environ}
    for key in SECRETS:
        if env.get(key):
            api.add_space_secret(repo_id, key, env[key])
            print(f"Secret {key} set")
    api.add_space_variable(repo_id, "PUBLIC_BASE_URL", url)
    print(f"\nDone. The Space is building (first build takes a few minutes):\n  https://huggingface.co/spaces/{repo_id}\nDemo link:\n  {url}")


if __name__ == "__main__":
    main()
