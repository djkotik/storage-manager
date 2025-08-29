# Publishing Storage Analyzer to unRAID Community Applications

This guide will walk you through the process of publishing your Storage Analyzer to the unRAID Community Applications.

## Prerequisites

1. **GitHub Account**: You'll need a GitHub account to host your code
2. **Docker Hub Account**: You'll need a Docker Hub account to host your Docker images
3. **unRAID Community Applications Account**: You'll need access to submit to Community Applications

## Step 1: Fix Data Persistence Issue

The current Docker setup has a data persistence issue. I've already fixed this by updating the `docker-compose.yml` file to properly mount the database file:

```yaml
volumes:
  - /data:/data:ro
  - ./app-data:/app/data
  - ./database:/app/storage_manager.db  # This line was added
```

This ensures that:
- Your database (`storage_manager.db`) persists between container restarts
- Your application data (`/app/data`) persists
- Your scanned data (`/data`) remains read-only for security

## Step 2: Create GitHub Repository

1. Create a new repository on GitHub (e.g., `scottmcc/storage-analyzer`)
2. Push your current code to the repository:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/scottmcc/storage-analyzer.git
   git push -u origin main
   ```

## Step 3: Build and Push to Docker Hub

1. **Login to Docker Hub**:
   ```bash
   docker login
   ```

2. **Build and push the image**:
   ```bash
   # Use the provided script
   ./publish.sh
   
   # Or manually:
   docker build -t scottmcc/storage-analyzer:latest .
   docker push scottmcc/storage-analyzer:latest
   ```

## Step 4: Create Icon

Create a 128x128 PNG icon for your application:
- Use the unRAID orange color (`#f37920`)
- Simple, clean design
- Save as `icon.png` in your repository root
- See `create-icon.md` for detailed instructions

## Step 5: Update Template

The `unraid-template.xml` file is already created with the correct structure. You may need to update:
- Repository name (if different from `scottmcc/storage-analyzer`)
- GitHub URLs
- Docker Hub URLs

## Step 6: Submit to Community Applications

1. **Fork the Community Applications repository**:
   - Go to: https://github.com/CommunityApplications/unraid-ca-templates
   - Click "Fork" to create your own copy

2. **Add your template**:
   - Clone your fork locally
   - Copy your `unraid-template.xml` to the `templates` directory
   - Rename it to something like `scottmcc-storage-analyzer.xml`

3. **Update the template file**:
   - Change the `TemplateURL` to point to your GitHub repository
   - Ensure all paths and URLs are correct

4. **Submit a pull request**:
   - Commit your changes
   - Push to your fork
   - Create a pull request to the main Community Applications repository

## Step 7: Testing

Before submitting, test your template:

1. **Test locally**:
   ```bash
   docker run -d \
     --name storage-analyzer-test \
     -p 8080:8080 \
     -v /path/to/test/data:/data:ro \
     -v /path/to/appdata:/app/data \
     -v /path/to/database:/app/storage_manager.db \
     scottmcc/storage-analyzer:latest
   ```

2. **Test in unRAID**:
   - Install your template manually in unRAID
   - Verify all paths work correctly
   - Test data persistence between restarts

## Important Notes

### Data Persistence
- **Database**: The database file (`storage_manager.db`) must be mounted to persist scan results
- **App Data**: The `/app/data` directory stores logs and settings
- **Data Path**: The `/data` mount is read-only for security

### Security Considerations
- The data path is mounted as read-only (`:ro`)
- The application runs as a non-root user
- Database and app data are in separate volumes

### Performance
- Large storage scans may take several hours
- The application uses SQLite for efficiency
- Memory usage is optimized for unRAID systems

## Troubleshooting

### Common Issues

1. **Database not persisting**:
   - Ensure the database volume mount is correct
   - Check file permissions on the host

2. **Permission denied**:
   - Ensure Docker has read access to the data path
   - Check unRAID share permissions

3. **Container won't start**:
   - Check Docker logs: `docker logs storage-analyzer`
   - Verify all required volumes are mounted

### Support

- **GitHub Issues**: Users can report issues on your GitHub repository
- **unRAID Forums**: Provide support in the unRAID community forums
- **Documentation**: Keep the README updated with troubleshooting steps

## Final Checklist

- [ ] Data persistence is working correctly
- [ ] Docker image builds and runs successfully
- [ ] Template XML is properly formatted
- [ ] Icon is created and uploaded
- [ ] GitHub repository is public and well-documented
- [ ] Docker Hub image is pushed and accessible
- [ ] Template has been tested in unRAID
- [ ] Pull request is submitted to Community Applications

## Timeline

- **Immediate**: Fix data persistence and test locally
- **This week**: Create GitHub repository and push Docker image
- **Next week**: Submit to Community Applications
- **Following week**: Monitor for feedback and issues

Good luck with your submission! The Storage Analyzer looks like a great addition to the unRAID community.
