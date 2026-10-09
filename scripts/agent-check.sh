#!/usr/bin/env bash
set -uo pipefail
# Checks real source/tooling without installing dependencies or pretending skipped checks passed.
repo="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo 'Not inside a Git checkout' >&2; exit 2; }
cd "$repo"
failed=0; skipped=0; ran=0
run() {
  local desc="$1"; shift
  echo ">>> $desc: $*"
  ((ran+=1))
  if "$@"; then echo "PASS: $desc"; else echo "FAIL: $desc"; ((failed+=1)); fi
}
skip() { echo "NOT RUN: $1"; ((skipped+=1)); }
if [[ -f Cargo.toml ]]; then
  if command -v cargo >/dev/null 2>&1; then
    run 'Rust format' cargo fmt --all -- --check
    run 'Rust check' cargo check --workspace
    if rustup component list --installed 2>/dev/null | grep -q '^clippy'; then
      run 'Rust clippy' cargo clippy --workspace --all-targets -- -D warnings
    else skip 'Rust clippy: component not installed'; fi
    run 'Rust tests' cargo test --workspace
  else skip 'Rust checks: Cargo not installed'; fi
else skip 'Rust checks: Cargo.toml missing'; fi
if [[ -f apps/web/package.json ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    skip 'Web build: npm not installed'
  elif [[ ! -d apps/web/node_modules ]]; then
    skip 'Web build: node_modules absent (run npm ci --prefix apps/web after approval)'
  else
    run 'Web build' npm run build --prefix apps/web
  fi
else skip 'Web build: apps/web/package.json missing'; fi
printf '\nSummary: ran=%s failed=%s not_run=%s\n' "$ran" "$failed" "$skipped"
# Nonzero status if anything was not exercised, to prevent interpreting partial verification as green.
if [[ $failed -gt 0 ]]; then exit 1; fi
if [[ $skipped -gt 0 ]]; then exit 2; fi
exit 0
