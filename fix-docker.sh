#!/bin/bash

# Fix Docker issues for Storage Analyzer on unRAID
echo "=== Storage Analyzer Docker Fix Script ==="
echo ""

# Stop and remove any existing containers
echo "Stopping and removing existing containers..."
docker stop unraid-storage-analyzer 2>/dev/null || echo "Container not running"
docker rm unraid-storage-analyzer 2>/dev/null || echo "Container not found"

# Remove any dangling images
echo "Cleaning up dangling images..."
docker image prune -f

# Remove the specific image if it exists
echo "Removing existing storage analyzer image..."
docker rmi unraid-storage-analyzer:latest 2>/dev/null || echo "Image not found"

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p app-data database

# Build the image fresh
echo "Building fresh Docker image..."
docker-compose build --no-cache

# Start the container
echo "Starting container..."
docker-compose up -d

# Check status
echo ""
echo "Container status:"
docker ps | grep storage-analyzer || echo "Container not found in running list"

echo ""
echo "Container logs:"
docker logs unraid-storage-analyzer --tail 20

echo ""
echo "=== Fix Complete ==="
echo "If the container is running, you can access it at: http://your-unraid-ip:8080"
echo "To check logs: docker logs -f unraid-storage-analyzer"
