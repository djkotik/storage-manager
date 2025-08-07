#!/bin/bash

echo "=== Storage Manager Database Fix ==="
echo "This script will fix database lock issues and restart the application."
echo

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "Error: docker-compose is not installed or not in PATH"
    exit 1
fi

# Stop the application first
echo "1. Stopping the application..."
docker-compose down

# Wait a moment for containers to stop
sleep 5

# Run the database fix script
echo "2. Running database fix script..."
docker-compose run --rm backend python /app/fix_database_lock.py

# Restart the application
echo "3. Restarting the application..."
docker-compose up -d

echo
echo "✅ Database fix completed!"
echo "The application should now be running and accessible."
echo "Check the logs with: docker-compose logs -f"
