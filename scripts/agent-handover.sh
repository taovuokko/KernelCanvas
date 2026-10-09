#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: bash scripts/agent-handover.sh KC-101' >&2; exit 2; }
id="$1"
[[ "$id" =~ ^KC-[0-9]{3,}$ ]] || { echo 'Invalid task id' >&2; exit 2; }
repo="$(git rev-parse --show-toplevel)"; cd "$repo"
branch="$(git branch --show-current)"
cat <<EOF
# Handover — ${id}

- Status: PART | READY_FOR_REVIEW | BLOCKED | FINAL (select one)
- Agent / owner: TODO
- Reviewer (different from owner): TODO
- Branch: ${branch}
- Commit(s): TODO
- PR / canonical task issue: TODO

## Outcome
TODO — what concretely changed?

## Changed paths and contracts
TODO — list paths; confirm ownership; explain contract changes or NONE.

## Verification (do not invent results)
| Check / environment | Result (PASS / FAIL / NOT RUN) | Evidence / reason |
| --- | --- | --- |
| cargo fmt --all -- --check | NOT RUN | TODO |
| cargo check --workspace | NOT RUN | TODO |
| cargo clippy --workspace --all-targets -- -D warnings | NOT RUN | TODO |
| cargo test --workspace | NOT RUN | TODO |
| npm run build --prefix apps/web | NOT RUN | TODO |
| GitHub Actions CI run | NOT RUN | TODO |

## Yocto evidence tier
NONE | FIXTURE | METADATA | IMAGE BUILD | QEMU BOOT | HARDWARE (select only actually verified)

## Security / safety / licensing notes
TODO

## Known gaps and blockers
TODO

## Next recommended action
TODO
EOF
