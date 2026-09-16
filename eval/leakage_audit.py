"""Classify heldout exposure without changing the frozen validator.

Only the explicitly reviewed, byte-identical historical reports below are
archived developer exposure. They are NOT evidence of an unseen holdout.
New copies, changed archives and all other matches fail this audit. The frozen
validator's original --check-leakage remains unchanged and reports every match.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.scoring import load_dataset
from eval.validate_dataset import leakage

# SHA-256 of committed file bytes at the audited revision, not wildcard paths.
ARCHIVE_REVISION = "e9c0c3f2dbc94833ea2ae30ae3ca61a1337e7b82"
ARCHIVE_SHA256 = {'eval/results/baseline.json': '49984ec86fae086b27612a3909a70211c6ec9707bed278c7d5c8c2febba8ce12',
 'eval/results/baseline.md': 'e49894daeb5ee7c711e03e1a37e87e95409d6fe417ad3b7e414371924bd5e735',
 'eval/results/candidate_cpu-t10-v2.json': '27b3ca47459256a6d55750b65238061bb4e744591c3a0ebd385cc7e9a6a0bb80',
 'eval/results/candidate_cpu-t10-v2.md': 'db54fe923159e5124734ab6a41a435d8fd85657ffc09e163468b7ed5ac950f61',
 'eval/results/candidate_greedy-topk1-cpu-v2.json': '1f4f71c41a7a7bdd256423346f300a608b6b25a185e760aeb0aa1d1c483c70ce',
 'eval/results/candidate_greedy-topk1-cpu-v2.md': '30c7df4be74a3eddeccb5ecbaa09dd5e2a0d433a1201652321094d9cba5886a7',
 'eval/results/candidate_qairt-native-06-v1.json': '24dca39bca763fdd3ce81dae4e1927a94247d6bf66e9702dd7789403ec4ac407',
 'eval/results/candidate_qairt-native-06-v1.md': '6743f3e9b0f81dd41a902b138a49791967b0b5bd0ac910e30a77a4426ea7f4d4',
 'eval/results/candidate_qwen17-cpu-t10-v2.json': 'ac20ae53e6db0382c7a47dc0282a8269484b943a78a5fd438fbda03fa8a0faad',
 'eval/results/candidate_qwen17-cpu-t10-v2.md': '10d3ac7503d298567056e1e90f8a4d6253b9ad004e757d31084e8fe6fa0e09b5'}


def audit(root=ROOT, heldout=None, archive_sha256=None):
    root = Path(root)
    if heldout is None:
        heldout = load_dataset([root / "eval/datasets/secretary_heldout.json"])
    archives = ARCHIVE_SHA256 if archive_sha256 is None else archive_sha256
    mismatches = []
    verified = set()
    for name, expected in archives.items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            mismatches.append({"file": name, "reason": "missing or symlinked archive"})
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatches.append({"file": name, "reason": "archive bytes differ from reviewed hash"})
        else:
            verified.add(name)
    matches = leakage(heldout, root)
    archived = [match for match in matches if match["file"] in verified]
    unreviewed = [match for match in matches if match["file"] not in verified]
    runtime = [match for match in unreviewed
               if match["file"].split("/", 1)[0] in {"turbo", "frontend", "configs", "scripts"}]
    return {
        "status": "FAIL" if mismatches or unreviewed else "PASS_WITH_DISCLOSED_EXPOSURE",
        "archive_revision": ARCHIVE_REVISION,
        "heldout_unseen_by_developers": not bool(matches),
        "developer_archive_exposure": archived,
        "unreviewed_exposure": unreviewed,
        "runtime_source_matches": runtime,
        "archive_integrity_errors": mismatches,
        "interpretation": "A source-text match requires review; it does not prove model ingestion. "
                          "Reviewed archived prompts have been exposed to developers and must not guide tuning.",
    }


def main():
    report = audit()
    print(json.dumps(report, indent=2))
    return int(report["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
