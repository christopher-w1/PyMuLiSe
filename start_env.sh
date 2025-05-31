#!/bin/bash
source ".env_vars.sh"
source "./venv/bin/activate"
export PYTHONPATH="$(pwd)"
echo "✅ Virtual environment activated with environment variables."
