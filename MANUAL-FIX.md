# Manual Fix for Docker Issues on unRAID

If you're experiencing Docker issues with the Storage Analyzer, follow these steps:

## Quick Fix Commands

Run these commands on your unRAID server in the `/mnt/user/appdata/unraid-storage-analyzer` directory:

### 1. Clean Up Existing Containers and Images
```bash
# Stop and remove the container
docker stop unraid-storage-analyzer
docker rm unraid-storage-analyzer

# Remove the image
docker rmi unraid-storage-analyzer:latest

# Clean up any dangling images
docker image prune -f
```

### 2. Create Required Directories
```bash
mkdir -p app-data database
```

### 3. Build Fresh Image
```bash
docker-compose build --no-cache
```

### 4. Start the Container
```bash
docker-compose up -d
```

### 5. Check Status
```bash
# Check if container is running
docker ps | grep storage-analyzer

# Check logs
docker logs unraid-storage-analyzer
```

## Alternative: Use the Fix Script

If you have the `fix-docker.sh` script:
```bash
chmod +x fix-docker.sh
./fix-docker.sh
```

## Troubleshooting

### If the container still won't start:

1. **Check Docker Compose version**:
   ```bash
   docker-compose --version
   ```

2. **Check available disk space**:
   ```bash
   df -h
   ```

3. **Check Docker daemon status**:
   ```bash
   systemctl status docker
   ```

4. **Check Docker logs**:
   ```bash
   journalctl -u docker.service -f
   ```

### If you get permission errors:

1. **Check directory permissions**:
   ```bash
   ls -la
   ```

2. **Fix permissions if needed**:
   ```bash
   chmod 755 app-data database
   ```

### If the build fails:

1. **Check Docker build context**:
   ```bash
   ls -la
   ```

2. **Ensure all files are present**:
   ```bash
   ls -la Dockerfile docker-compose.yml
   ```

## Data Persistence Verification

After the container is running, verify data persistence:

1. **Check if database file exists**:
   ```bash
   ls -la database/
   ```

2. **Check if app-data directory has content**:
   ```bash
   ls -la app-data/
   ```

3. **Test persistence by restarting**:
   ```bash
   docker-compose restart
   ls -la database/  # Should still exist
   ```

## Access the Application

Once running, access the web interface at:
```
http://your-unraid-ip:8080
```

## Common Issues and Solutions

### Issue: "Unable to find image" error
**Solution**: The image wasn't built properly. Run the build command again.

### Issue: Port already in use
**Solution**: Change the port in docker-compose.yml or stop the conflicting service.

### Issue: Permission denied on volumes
**Solution**: Check unRAID share permissions and ensure Docker has access.

### Issue: Container exits immediately
**Solution**: Check the logs with `docker logs unraid-storage-analyzer` for error details.
