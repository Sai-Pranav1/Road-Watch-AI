#!/usr/bin/env bash
# =============================================================================
# Road Damage Reporting Platform - One-Click Direct Boot Script
# Hackathon MVP v2.0 Unified Runner
# =============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "======================================================================"
echo "🚧  INITIALIZING ROAD DAMAGE REPORTING PLATFORM (MVP v2.0)"
echo "======================================================================"

# 1. Setup Python Virtual Environment
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# 2. Check & Install Dependencies
echo "📦 Verifying dependencies..."
python -m pip install -q -r requirements.txt || true

# 3. Create necessary runtime directories
mkdir -p app/static/uploads

echo ""
echo "======================================================================"
echo "🚀 SYSTEM READY - LAUNCHING UNIFIED APPLICATION"
echo "======================================================================"
echo "📱 Citizen Web App:      http://localhost:8000/"
echo "🗺️  Authority Dashboard: http://localhost:8000/admin"
echo "📖 OpenAPI Documentation: http://localhost:8000/docs"
echo "⚡ Health Endpoint:       http://localhost:8000/health"
echo "======================================================================"
echo "Press Ctrl+C to terminate the server."
echo ""

# 4. Boot FastAPI Server
exec python main.py
