#!/usr/bin/env bash
# questions_vault.sh — encrypt/decrypt the CISSP question archive into git.
#
# WHY THIS EXISTS
#   data/questions/ holds ~988 questions OCR'd from the official ISACA
#   CISSP practice exam (verbatim stems, options and rationales). That is
#   copyrighted material. This repo is PUBLIC, so committing the raw text
#   would mean redistributing someone else's copyrighted work.
#
# WHAT IT DOES
#   seal  : tar the directory, age-encrypt with a local-only key, write the
#           ciphertext to vault/questions.tar.age, then git-add it.
#           Committing ciphertext keeps full local version control and a
#           complete audit trail in git history without exposing content.
#   open  : decrypt to a scratch dir (does NOT touch data/questions).
#   verify: prove the committed ciphertext still decrypts and matches the
#           live directory file-for-file.
#
# KEY HANDLING
#   The private key lives OUTSIDE the repo at ~/.secrets/knowledge-cockpit/
#   and is never committed. Losing it means losing the ciphertext — back it
#   up somewhere safe and separate from this machine.
#
# Usage: ./scripts/questions_vault.sh {seal|open|verify}
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/data/questions"
VAULT_DIR="$REPO_ROOT/vault"
ARCHIVE="$VAULT_DIR/questions.tar.age"
PUBKEY_FILE="$HOME/.secrets/knowledge-cockpit/questions.pub"
KEY_FILE="$HOME/.secrets/knowledge-cockpit/questions.agekey"
DECRYPT_DIR="$REPO_ROOT/.vault-plaintext"   # gitignored, ephemeral

die() { echo "ERROR: $*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "'$1' not found. Run: brew install $1"; }
need age; need age-keygen; need tar

[ -f "$PUBKEY_FILE" ] || die "no public key at $PUBKEY_FILE (run age-keygen first)"
[ -f "$KEY_FILE" ]   || die "no private key at $KEY_FILE — cannot decrypt without it"

cmd_seal() {
  [ -d "$SRC_DIR" ] || die "source dir missing: $SRC_DIR"
  mkdir -p "$VAULT_DIR"
  n=$(find "$SRC_DIR" -type f | wc -l | tr -d ' ')
  echo "[vault] sealing $n files from data/questions/ ..."
  # macOS ships bsdtar, which has no --sort. Feeding a pre-sorted null-
  # delimited list gives the same deterministic archive: unchanged content
  # produces byte-identical ciphertext instead of a noisy diff.
  list="$VAULT_DIR/.filelist"
  # BSD sort has no -z, so sort the plain paths and re-null-terminate with
  # tr. find -print0 alone would be non-deterministic in ordering.
  (cd "$REPO_ROOT/data" && find questions -type f | LC_ALL=C sort | tr '\n' '\0') > "$list"
  # -C must precede --files-from so names resolve relative to data/.
  tar -cf "$VAULT_DIR/.questions.tar" -C "$REPO_ROOT/data" --null --files-from "$list"
  age -R "$PUBKEY_FILE" -o "$ARCHIVE" < "$VAULT_DIR/.questions.tar"
  rm -f "$VAULT_DIR/.questions.tar" "$list"
  echo "[vault] wrote $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
  if git -C "$REPO_ROOT" diff --quiet -- "$ARCHIVE" 2>/dev/null; then
    echo "[vault] ciphertext unchanged vs HEAD (no new questions)"
  fi
  git -C "$REPO_ROOT" add "$ARCHIVE"
  echo "[vault] staged. Review with: git diff --cached --stat"
}

cmd_open() {
  rm -rf "$DECRYPT_DIR"; mkdir -p "$DECRYPT_DIR"
  age -d -i "$KEY_FILE" "$ARCHIVE" | tar -xf - -C "$DECRYPT_DIR"
  echo "[vault] decrypted to $DECRYPT_DIR/questions/"
  echo "[vault] NOTE: plaintext on disk — delete when done."
}

cmd_verify() {
  rm -rf "$DECRYPT_DIR"; mkdir -p "$DECRYPT_DIR"
  # Compare against the COMMITTED blob, not the working file, so this
  # proves what is actually in git history is recoverable.
  # NOTE: git rev-parse paths are repo-root-relative, so pass the path
  # relative to REPO_ROOT — an absolute path silently fails to resolve.
  rel="${ARCHIVE#"$REPO_ROOT/"}"
  git -C "$REPO_ROOT" show "HEAD:$rel" > "$DECRYPT_DIR/.blob.age"
  age -d -i "$KEY_FILE" "$DECRYPT_DIR/.blob.age" | tar -xf - -C "$DECRYPT_DIR"
  a=$(cd "$SRC_DIR" && find . -type f -exec shasum -a 256 {} + | sort -k2 | shasum -a 256 | cut -d' ' -f1)
  b=$(cd "$DECRYPT_DIR/questions" && find . -type f -exec shasum -a 256 {} + | sort -k2 | shasum -a 256 | cut -d' ' -f1)
  if [ "$a" = "$b" ]; then
    echo "[vault] OK — committed ciphertext decrypts and matches data/questions/ ($a)"
  else
    echo "[vault] MISMATCH  live=$a  vault=$b" >&2
    exit 1
  fi
  rm -rf "$DECRYPT_DIR"
}

case "${1:-}" in
  seal)   cmd_seal ;;
  open)   cmd_open ;;
  verify) cmd_verify ;;
  *)      die "usage: $0 {seal|open|verify}" ;;
esac