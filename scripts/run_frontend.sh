#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
if [[ ! -f .env.local ]]; then
  echo "Copy .env.example to .env.local and set Supabase keys first."
  exit 1
fi
npm install
npm run dev
