# Storage Analyzer

A comprehensive storage analysis tool designed for unRAID systems, providing detailed disk usage analytics, duplicate file detection, and storage management capabilities.

## Features

- **Disk Usage Analysis**: Visual breakdown of storage usage by file type, folder, and disk
- **Duplicate File Detection**: Find and manage duplicate files across your storage
- **Media File Detection**: Automatic detection and categorization of media files
- **Usage Explorer**: Interactive folder size analysis and navigation
- **Multiple Themes**: Support for unRAID, Plex, Emby, Jellyfin, Dark, Light, and Dark Lime themes
- **Real-time Scanning**: Live scan progress and status monitoring
- **Export Capabilities**: Export reports and data for external analysis
- **Customizable Settings**: Configurable scan times, exclusions, and preferences

## Quick Start

### Docker Compose (Recommended)

1. Clone this repository:
```bash
git clone https://github.com/scottmcc/storage-analyzer.git
cd storage-analyzer
```

2. Create the necessary directories:
```bash
mkdir -p app-data database
```

3. Start the application:
```bash
docker-compose up -d
```

4. Access the web interface at `http://localhost:8080`

### Manual Docker Run

```bash
docker run -d \
  --name storage-analyzer \
  -p 8080:8080 \
  -v /path/to/your/data:/data:ro \
  -v /path/to/appdata:/app/data \
  -v /path/to/database:/app/storage_manager.db \
  -e DATA_PATH=/data \
  -e SCAN_TIME=01:00 \
  -e MAX_SCAN_DURATION=6 \
  scottmcc/storage-analyzer:latest
```

## unRAID Community Applications

### Installing via Community Applications

1. Install the Community Applications plugin in unRAID
2. Search for "Storage Analyzer" in the Apps tab
3. Click "Install" and configure the paths:
   - **Data Path**: Path to scan (e.g., `/mnt/user`)
   - **App Data**: Application data directory (e.g., `/mnt/user/appdata/storage-analyzer`)
   - **Database**: Database file location (e.g., `/mnt/user/appdata/storage-analyzer/storage_manager.db`)
   - **Port**: Web interface port (default: 8080)

### Manual Template Installation

1. Download the `unraid-template.xml` file
2. In unRAID, go to the Docker tab
3. Click "Add Container" → "Template"
4. Upload the template file
5. Configure the paths and settings as needed

## Configuration

### Environment Variables

- `DATA_PATH`: Path to scan for files (default: `/data`)
- `SCAN_TIME`: Daily scan time in HH:MM format (default: `01:00`)
- `MAX_SCAN_DURATION`: Maximum scan duration in hours (default: `6`)
- `FLASK_ENV`: Flask environment (default: `production`)

### Volume Mounts

- `/data`: Read-only mount for the data to be scanned
- `/app/data`: Read-write mount for application data (logs, settings)
- `/app/storage_manager.db`: Read-write mount for the database file

## Data Persistence

The application stores data in two locations:
- **Database**: `storage_manager.db` - Contains all scan results, file information, and settings
- **App Data**: `/app/data` - Contains logs, temporary files, and application state

**Important**: Always mount these volumes to persist your data between container restarts.

## Development

### Building from Source

1. Clone the repository:
```bash
git clone https://github.com/scottmcc/storage-analyzer.git
cd storage-analyzer
```

2. Build the Docker image:
```bash
docker build -t storage-analyzer .
```

3. Run with development settings:
```bash
docker run -d \
  --name storage-analyzer-dev \
  -p 8080:8080 \
  -v /path/to/your/data:/data:ro \
  -v /path/to/appdata:/app/data \
  -v /path/to/database:/app/storage_manager.db \
  -e FLASK_ENV=development \
  storage-analyzer
```

### Local Development

#### Frontend (React/TypeScript)
```bash
cd frontend
npm install
npm run dev
```

#### Backend (Python/Flask)
```bash
cd backend
pip install -r requirements.txt
python app.py
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Publishing to unRAID Community Applications

To publish this to the unRAID Community Applications:

1. **Create a GitHub repository** with your code
2. **Build and push to Docker Hub**:
   ```bash
   docker build -t yourusername/storage-analyzer .
   docker push yourusername/storage-analyzer
   ```
3. **Update the template** with your Docker Hub repository
4. **Submit to Community Applications**:
   - Fork the [Community Applications repository](https://github.com/CommunityApplications/unraid-ca-templates)
   - Add your template to the `templates` directory
   - Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/scottmcc/storage-analyzer/issues)
- **Documentation**: Check the [Wiki](https://github.com/scottmcc/storage-analyzer/wiki) for detailed guides
- **Community**: Join discussions in the [unRAID forums](https://forums.unraid.net/)

## Version History

- **v1.11.9**: Theme improvements, navigation fixes, enhanced duplicate detection
- **v1.11.0**: Added comprehensive theme support, improved UI/UX
- **v1.10.0**: Enhanced analytics, better performance, improved scanning
- **v1.0.0**: Initial release with basic storage analysis features 