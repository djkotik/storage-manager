#!/bin/bash

# Storage Analyzer Docker Publishing Script
# This script builds and publishes the Docker image to Docker Hub

set -e

# Configuration
DOCKER_USERNAME=${DOCKER_USERNAME:-"scottmcc"}
IMAGE_NAME="storage-analyzer"
VERSION=$(cat VERSION)
LATEST_TAG="${DOCKER_USERNAME}/${IMAGE_NAME}:latest"
VERSION_TAG="${DOCKER_USERNAME}/${IMAGE_NAME}:v${VERSION}"

echo "=== Storage Analyzer Docker Publishing Script ==="
echo "Docker Username: $DOCKER_USERNAME"
echo "Image Name: $IMAGE_NAME"
echo "Version: $VERSION"
echo "Latest Tag: $LATEST_TAG"
echo "Version Tag: $VERSION_TAG"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running or not accessible"
    exit 1
fi

# Check if user is logged into Docker Hub
if ! docker info | grep -q "Username"; then
    echo "Warning: Not logged into Docker Hub"
    echo "Please run: docker login"
    echo ""
fi

# Build the image
echo "Building Docker image..."
docker build --no-cache -t $LATEST_TAG -t $VERSION_TAG .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully"
else
    echo "❌ Docker build failed"
    exit 1
fi

# Ask for confirmation before pushing
echo ""
read -p "Do you want to push the image to Docker Hub? (y/N): " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Pushing latest tag..."
    docker push $LATEST_TAG
    
    echo "Pushing version tag..."
    docker push $VERSION_TAG
    
    echo "✅ Docker images pushed successfully"
    echo ""
    echo "Images available at:"
    echo "  Latest: https://hub.docker.com/r/$DOCKER_USERNAME/$IMAGE_NAME"
    echo "  Version: https://hub.docker.com/r/$DOCKER_USERNAME/$IMAGE_NAME/tags"
else
    echo "Skipping push to Docker Hub"
fi

echo ""
echo "=== Publishing Complete ==="
echo ""
echo "Next steps for unRAID Community Applications:"
echo "1. Create a GitHub repository with your code"
echo "2. Update the unraid-template.xml with your Docker Hub repository"
echo "3. Fork the Community Applications repository:"
echo "   https://github.com/CommunityApplications/unraid-ca-templates"
echo "4. Add your template to the templates directory"
echo "5. Submit a pull request"
echo ""
echo "For local testing, you can now run:"
echo "  docker run -d --name storage-analyzer -p 8080:8080 $LATEST_TAG"
