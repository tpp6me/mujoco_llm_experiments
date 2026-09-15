# AGY completion — task 011 (C3 execution and evidence packaging)

Status: **execution complete; packaged for Codex blind review**
Task brief: `coordination/agy/tasks/011-c3-execution.md`
Branch: `agy/011-c3-execution`
Starting commit (clean source freeze): `19b78537ff52b348f30a10e5147ab5012c5c1ef1`
Worktree: `/private/tmp/mujoco-llms-agy-011`
Execution interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/mjpython`
Packaging interpreter: `/Users/praveen/work/github/mujoco-llms/.venv/bin/python`

---

## 1. Provenance and pre-execution verification

Before simulator initialization or tracked file modifications:
- Confirmed git working tree clean status on branch `agy/011-c3-execution` at exact clean starting commit `19b78537ff52b348f30a10e5147ab5012c5c1ef1`.
- Confirmed local CLI installation (`codex-cli 0.154.0`), ChatGPT authentication status (`Logged in using ChatGPT`), and executable `/Users/praveen/versions/node/v20.18.1/bin/codex`. No API endpoints, API keys, or model probes.
- Verified all 92 pinned files in `experiments/humanoid-pick-place/protocols/C3_FREEZE.json` byte-for-byte against their SHA-256 digests (0 mismatches).
- Verified static instruction digest: `de0525e07f9470be60f9e01c4d720ad4f65260fd54b08065708e4096ce6313d0`.
- Verified serialized runtime schema digest: `79afc9c195908ce3e268e50193db8d188e579d451c0467365a64fb2297fb0dff`.
- Verified serialized geometry evidence digest: `d05eaa296612db243fd9362d1018d7b92d63cb93006221f959422fa1712141d6`.
- Generated and recorded pre-run manifest at `runtime/humanoid/codex-C3/manifest.json` before launch.

---

## 2. Authorized execution

Executed the exact protocol command once:
```sh
/Users/praveen/work/github/mujoco-llms/.venv/bin/mjpython -m humanoid_sim.codex_policy --execute --condition c3 --output runtime/humanoid/codex-C3/seed-820
```

- Process monitored to full completion. No simulator intervention, decision editing, fallback, retry, probe, or extra rollout.
- Captured stdout, stderr, and process exit status in `runtime/humanoid/codex-C3/`.
- The runner generated all episode artifacts in `runtime/humanoid/codex-C3/seed-820/`.

---

## 3. Post-execution audit and verification

- Verified all 92 pinned frozen source files still match their SHA-256 digests following execution.
- Verified all 18 model call requests and observations:
  - Every saved prompt and PNG reproduces byte-for-byte from public call requests via `public_input(req, condition='c3')`.
  - Every CLI event log passes `validate_events`: zero tool items, exactly one turn start and completion, final message agreement with `decision.json`.
  - Observation history strictly excludes `visual_assessment` from all subsequent calls; only command and interface execution status were forwarded.
  - Forwarded interface requests match returned commands.

---

## 4. Evidence packaging

1. **Episode archive**:
   - Packaged all 137 runtime files from `runtime/humanoid/codex-C3/` into `experiments/humanoid-pick-place/results/codex_C3_episode.zip`.
   - Included full member SHA-256 manifest `sha256.json` (138 total archive members).
   - SHA-256: `08202990a01ecd22adc2c860ff2260b126bfae57579963285bba6595e7198972` (3,994,434 bytes).

2. **Machine-readable result**:
   - Saved to `experiments/humanoid-pick-place/results/codex_C3.json`.
   - Contains runner report, private evaluator report, per-decision records, usage statistics, and per-call visual assessment accounting.
   - SHA-256: `eb310fdfe3a6dd0b48e53484eee00a40ae63d90a5b933aa5f7591cea2b653612` (57,145 bytes).

3. **Blind image index**:
   - Saved to `coordination/agy/reports/011-blind-images.json`.
   - Contains 18 ordered entries with call numbers, observation IDs, timestamps, runtime and archive PNG paths, image hashes, and availability flags.
   - Contains no commands, model assessments, private coordinates, or physical outcomes.
   - SHA-256: `2bd78035e079a3020beb46e93bcef18f87b40108aac34eec9b5134ba473eecf8` (7,130 bytes).

---

## 5. Review order and deferral

In strict accordance with the C3 protocol and task instructions:
- AGY has not opened, labelled, or interpreted any saved images.
- Scientific interpretation, result narrative, outcome evaluation, and final updates to `PLAN.md` are deferred to Codex following its independent blind review of `coordination/agy/reports/011-blind-images.json`.
