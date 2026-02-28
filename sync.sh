#!/bin/bash
# Quick sync to GitHub
cd "$(dirname "$0")"
git add .
git commit --no-gpg-sign -m "${1:-sync: update files}"
git push origin main
