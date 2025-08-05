# unRAID Storage Analyzer & Media Manager

A comprehensive Dockerized application for unRAID servers that provides detailed disk usage analysis, media management, and storage optimization tools.

## Features

- **Disk Usage Visualization**: Treemap and sunburst charts for visual storage analysis
- **Media Management**: Automatic detection and metadata extraction for TV shows and movies
- **Duplicate Detection**: Find and manage duplicate files efficiently
- **Storage Analytics**: Track storage usage over time with customizable timeframes
- **File Management**: Delete, move, and organize files with trash bin functionality
- **Theme Support**: Multiple themes including Plex and unRAID styles
- **Responsive Design**: Works on desktop, tablet, and mobile devices

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd storage-manager
   ```

2. **Build and run**:
   ```bash
   chmod +x build.sh
   ./build.sh
   docker-compose up -d
   ```

3. **Access the application**:
   Open your browser and navigate to `http://localhost:8080`

### Manual Docker Deployment

```bash
docker run -d \
  --name unraid-storage-analyzer \
  -p 8080:8080 \
  -v /data:/data:ro \
  -v /path/to/app/data:/app/data \
  --restart unless-stopped \
  unraid-storage-analyzer:latest
```

### Environment Variables

- `SCAN_TIME`: Daily scan time (default: "01:00")
- `DATA_PATH`: Path to scan (default: "/data")
- `MAX_SCAN_DURATION`: Maximum scan duration in hours (default: 6)
- `FLASK_ENV`: Environment mode (development/production)

## Development

### Prerequisites

- Python 3.9+
- Node.js 16+
- Docker

### Quick Development Setup

```bash
chmod +x dev-setup.sh
./dev-setup.sh
```

### Manual Development Setup

1. **Backend Setup**:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```

2. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

3. **Docker Build**:
   ```bash
   chmod +x build.sh
   ./build.sh
   ```

## Usage

### First Run

1. **Start the application** using Docker or development setup
2. **Navigate to the Dashboard** and click "Start Scan"
3. **Wait for the scan to complete** (this may take several hours for large storage)
4. **Explore the results** in the various sections:
   - Dashboard: Overview and statistics
   - Files: Browse and manage files
   - Media: View media files with metadata
   - Analytics: Storage usage trends
   - Settings: Configure the application

### Key Features

- **File Browsing**: Search, filter, and sort files by various criteria
- **Media Detection**: Automatic identification of movies, TV shows, and music
- **Storage Analytics**: Track usage over time with interactive charts
- **Theme Switching**: Choose between unRAID, Plex, dark, and light themes
- **Trash Bin**: Safe file deletion with restore capability
- **Database Reset**: Clean slate option in settings

### Performance Considerations

- **Large Storage**: For 70TB+ storage, initial scans may take 6+ hours
- **Memory Usage**: Application uses SQLite for efficiency
- **Scan Scheduling**: Configure automatic daily scans during low-usage periods
- **File System**: Supports all file systems handled by unRAID

## Architecture

- **Backend**: Python Flask API with SQLite database
- **Frontend**: React with TypeScript and Tailwind CSS
- **Scanner**: Efficient file system scanner with media detection
- **Database**: SQLite for persistence and scan history
- **Themes**: CSS custom properties for easy theme switching

## Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure Docker has read access to `/data`
2. **Scan Timeout**: Increase `MAX_SCAN_DURATION` environment variable
3. **Memory Issues**: Monitor container memory usage during large scans
4. **Database Corruption**: Use the reset database option in settings

### Logs

- **Application Logs**: `/app/logs/app.log` inside container
- **Docker Logs**: `docker logs unraid-storage-analyzer`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

MIT License 