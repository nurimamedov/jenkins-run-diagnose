# Jenkins Run Diagnose

An offline portfolio demo for comparing a failed CI build with its last
successful build. It answers three questions: which stages actually failed,
what changed since green, and which log lines are worth reading first?

This is an independently written example using fictional stage metadata and logs.
It does not connect to Jenkins, retrieve credentials or modify either run.

## Quick start

Requires Python 3.10+ and no third-party dependencies.

```sh
python3 diagnose.py examples/failed.json examples/last-green.json --tail-lines 3
python3 -B -m unittest discover -s tests -v
```

In the example, **Integration test** failed, ran 1,900 ms longer and reported
a missing queue event. The optional-cache warning was also present in the
green run, so it is absent from the novel signals. **Package** did not run
and is not presented as a separate failure.

## Input contract

Provide two UTF-8 JSON snapshots. The first must have top-level status
`FAILURE`, the second `SUCCESS`. Choose the last comparable green build
yourself; the snapshots have no branch or timestamp semantics.

Each snapshot has a string `run_id` and an array `stages`. A stage has a
unique string `name`, `status` (SUCCESS, FAILURE, ABORTED, UNSTABLE or
NOT_RUN), optional non-negative integer `duration_ms` and optional string
`log`. Use names that encode full stage paths for parallel jobs with repeated
display names. Snapshots are limited to 2 MiB and 100 stages each.

## Output contract

The tool matches failed stages by exact name and reports their baseline status,
duration delta, trimmed tail and novel warning/error-style lines. It normalizes
terminal controls and compares full lines before truncating excerpts. Novel
signals are clues, **not root cause attribution**. Timestamps or other
dynamic values in a line can make it appear novel.

Report keys include `schema_version` (1), `ok`, `failed_run`,
`baseline_run` and `failed_stages`. Missing baseline comparisons are null.
`--tail-lines` (1–40) bounds each excerpt list and `--line-chars` (16–240)
bounds each line. Exit 0 means a comparison was generated, even if the build
failed; exit 2 gives an `error` object for invalid input.

Use synthetic or pre-redacted logs. Output can contain whatever was present
in the supplied logs; control removal and truncation are not secret redaction.

## License

[MIT](LICENSE). Copyright © 2026 Nuri Mamedov. Keep the copyright and license notice when copying or redistributing substantial portions.
