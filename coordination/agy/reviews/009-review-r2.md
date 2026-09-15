# Task 009 revision review — final provenance correction

2026-09-15. Reviewed tip: `c5af1af2b61b395f6459ec31cdcddfdafb7e65b3`.
R1–R4's substantive data corrections reproduce. A fresh offline audit reproduces
all numeric/public JSON content (apart from source path/hash), all seven image
panels pixel-for-pixel, and the complete contact-sheet PNG. Public state/history/
image IDs match the original requests. No physics/reset/subprocess/model calls.

One required correction remains: `audit.json.audit_source_sha256` is
`bf08442f985113e342efd55cc7c335360b0c22ec60ef4fe68fd7fd45e49d3627`,
but the committed script hashes to
`546ee547bde8606b64a0713743cb52a51492664dacb0d3c21e75b41d48ad412d`.
The report claims the artifact is tied to its final script, which is not yet true.

Regenerate the Task 009 artifact with the final script after any source formatting
changes; update every affected artifact/report digest and verify the embedded
script digest equals the actual bytes. Preserve the original C1/C2 archives.
Also replace prose/JSON saying physical contact "begins" at sample 117 with
"first sampled contact": 30 Hz snapshots cannot identify exact collision onset.
Complete wording/source formatting first, then generate evidence last. Do not
change controller behavior, run models or step physics. A full suite is unnecessary;
run the focused C1/C2 audit tests and exact artifact/digest checks. Commit/push the
same branch, return its exact tip, and stop for acceptance.
