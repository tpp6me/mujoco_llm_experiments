# Phase 5 camera-only development protocol

Frozen before scored camera trials. Use the same twelve case configurations as
Phase 4, including seeds, physical cube layouts, instructions, belt speeds,
spacing, motion capability, deadlines, and 0.25-second runtime-lag threshold.
Run both Codex and a conventional pixel-color baseline. Preserve all 24 episodes,
including failures; no retries or excluded cases.

## Public observations

Return only the literal instruction, frame capture timestamp, observation ID,
calibrated belt velocity, camera calibration, and a rendered overhead RGB image.
Do not return physical cube IDs, object positions, colors, bounding boxes, model
segmentation, or grader settings. Static pixel-coordinate rulers may be drawn;
no object-specific labels or detections are overlaid.

The camera looks down from (0.22, −0.18, 0.70) m, with a 45-degree vertical field
of view, 960 × 720 pixels, principal point (480, 360), and known 3 cm cube top
plane. Calibrated pixel-to-world conversion is purely geometric. It does not
consult the cube state or correct the agent's estimate.

Codex visually chooses a target, assigns a neutral label such as `object_A`,
and supplies its perceived color and pixel center. It explicitly schedules the
same four motion primitives used in Phase 4, using its estimated Y coordinate
and the image capture time. The runtime treats the label only as a queue/contact
log handle; it never resolves it to a true cube ID for control.

Only the private scorer associates estimates with physical objects after the
run. It matches the nearest true object at capture time within 3 cm, records
position/Y error, color accuracy, target-selection correctness, and actual
contacts. This association never changes the requested trajectory or timing.
Read private reports only after all Codex camera submissions are finished.

## Continuous time and comparison

A dedicated graphics process renders captured state while physics continues.
Initialize graphics before starting the wall-paced episode. Record capture-to-
image-ready delay and capture-to-command delay. Rendering time, image inspection,
Codex reasoning, and tool overhead all count toward the latter; do not identify
it as isolated inference latency.

The conventional visual baseline thresholds image RGB values inside the static
belt region, finds connected pixel regions, and estimates their centers. It
receives no true object positions or IDs. It uses the same calibration, queue,
motion compiler, actuator limits, and scorer as Codex. Label its results separately
from the Phase 4 conventional exact-state controller.

The Phase 5 gate is a completed, auditable measurement of perception errors,
missed interceptions, and response delay relative to Phase 4, not a requirement
that every camera trial succeeds. Report all cases by condition and compare
their physical outcomes with the corresponding Phase 4 results. Also report
selected-object position errors and color mistakes, including estimates attached
to expired commands. Distinguish visual selection error, geometric estimation
error, late arrival, cycle conflict, and runtime lag.

## Limits and provenance

The current Codex session has prior context about Phase 4 and the scene. The
same case layouts make comparisons possible but prevent an independent blinded
benchmark; prior layout knowledge remains a potential confound. The public
observation API removes oracle metadata, but the shared filesystem is not an
OS-enforced isolation boundary. During evaluated Codex decisions, use images
and public calibration only; do not run the conventional detector or inspect
private files. Ordinary arithmetic on an explicitly chosen pixel estimate is allowed.

This is a small development study with three mixed-color layouts and fixed
lighting. Exact runtime model version, model-call count, tokens, and cost are
unavailable. Images, public observations, requests, private scoring audits, source
hashes, and videos are retained. Wider robustness and formal benchmarking remain
Phase 6 work.
