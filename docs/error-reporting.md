# Error reporting (Phase 9, D-0126)

1. **Refusals raise; they never return a value.** Every refusal names its cause.
   - Execution refusals are `PaperError` / `ExecutionModeError` / `BrokerToolError`.
   - Every commit refusal is written to the audit log (`commit_refused`).
2. **A wrong answer.** Send the run JSON (`evals/results/*.json`). Every row stores the question, the raw output
   (`metrics.raw_output`), the shown output, the model output (`output_model` under `--display`), metrics and
   grades. Then:
   - `scripts/attribute_failures.py` assigns each failure one cause: HARDWARE, RETRIEVAL, FIXTURE, HARNESS, GRADER or
     MODEL.
   - `scripts/regrade_eval.py` regrades the recorded replies without re-running the model.
3. **A safety defect** (anything that reaches an order or a credential):
   - Engage the kill switch: `engine.kill.engage("HUMAN", reason)`.
   - Verify the audit chain: `engine.audit.verify()`.
   - Run `engine.reconcile()`. A mismatch engages the kill switch automatically.
4. **An installation problem:** run `bash tests/run_all.sh` and send its last 30 lines.
