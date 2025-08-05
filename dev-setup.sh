#!/bin/bash

# Development setup script for unRAID Storage Analyzer

set -e

echo "Setting up development environment..."

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Setup frontend
echo "Setting up frontend..."
cd frontend
npm install
cd ..

# Setup backend
echo "Setting up backend..."
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..

# Create necessary directories
mkdir -p app-data logs

echo "Development environment setup completed!"
echo ""
echo "To start development:"
echo "1. Backend: cd backend && source venv/bin/activate && python app.py"
echo "2. Frontend: cd frontend && npm run dev"
echo ""
echo "Or use docker-compose for development:"
echo "docker-compose up --build" 