#!/bin/bash

# Build script for unRAID Storage Analyzer

set -e

echo "Building unRAID Storage Analyzer..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed"
    exit 1
fi

# Build the Docker image
echo "Building Docker image..."
docker build -t unraid-storage-analyzer:latest .

echo "Build completed successfully!"
echo ""
echo "To run the container:"
echo "docker run -d \\"
echo "  --name unraid-storage-analyzer \\"
echo "  -p 8080:8080 \\"
echo "  -v /data:/data:ro \\"
echo "  -v /path/to/app/data:/app/data \\"
echo "  --restart unless-stopped \\"
echo "  unraid-storage-analyzer:latest"
echo ""
echo "Or use docker-compose:"
echo "docker-compose up -d" 