# Secretary reference — not measured

Application commit: `f8f27ccb520e7a4cc1eca0a062fe4742e28a76b2` (clean at capture).

Accuracy, tool/action/argument rates and latency: **not measured**. No model run was performed.

Missing: production Secretary module, verified native SDK/model configuration and verified SSH access to the Latitude. The implemented benchmark measures first-action intent through the existing ActionCodec/native adapter; it does not execute file tools.

Run on the Latitude after configuring the real SDK/model:

```sh
python eval/run_secretary_eval.py --dataset all --candidate-name reference --config local/secretary-config.json --freeze-baseline --output-dir local/reference
```

See [the evaluation protocol](../../docs/secretary-evaluation.md). Do not reuse prior performance sweep results as correctness evidence.
