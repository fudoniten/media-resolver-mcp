# Media Resolver MCP Server

A Model Context Protocol (MCP) server that enables Home Assistant Assist (LLM agent) to intelligently resolve and play media via Mopidy and Icecast.

## Features

- **11 MCP Tools** for music and podcast playback
- **LLM-Powered Disambiguation** using LangChain (supports Claude, GPT, Ollama, etc.)
- **Web Admin UI** with configuration management, testing, and request history
- **Mopidy Integration** with automatic backend detection
- **Podcast Support** via RSS feed parsing
- **Genre-based Playback** with flexible configuration
- **Request Logging** with full LLM interaction tracking

## Architecture

```
User → Home Assistant Assist → MCP Tools → Media Resolver
                                              ↓
                                    ┌─────────┴─────────┐
                                    ↓                   ↓
                                Mopidy              Podcast RSS
                                    ↓                   ↓
                                Icecast          (parsed feeds)
                                    ↓
                            Playback Devices
```

## Quick Start

### Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled (recommended)
  - OR Python 3.12+ for manual installation
- Mopidy server with HTTP API enabled
- Icecast streaming server (optional but recommended)
- LLM API key (Anthropic, OpenAI, or local Ollama)

> **Note:** If you have Nix installed but flakes are not enabled, add the following to `~/.config/nix/nix.conf`:
> ```
> experimental-features = nix-command flakes
> ```

### Installation with Nix (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/media-selector-mcp.git
cd media-selector-mcp
```

2. Configure the server:
```bash
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your settings
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

4. Run the server:
```bash
nix run
```

The server will start on `http://localhost:8000` with:
- MCP endpoint: `/mcp`
- Admin UI: `/admin`

#### Additional Nix Commands

```bash
# Build the package
nix build

# Enter development shell with all dependencies
nix develop

# Run the built package directly
./result/bin/media-resolver
```

### Installation with pip

If you don't have Nix installed, you can use pip:

1. Clone the repository:
```bash
git clone https://github.com/yourusername/media-selector-mcp.git
cd media-selector-mcp
```

2. Install dependencies:
```bash
pip install -e .
```

3. Configure the server:
```bash
cp config/config.yaml.example config/config.yaml
# Edit config/config.yaml with your settings
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. Run the server:
```bash
python -m media_resolver.server
# Or use the installed command
media-resolver
```

The server will start on `http://localhost:8000` with:
- MCP endpoint: `/mcp`
- Admin UI: `/admin`

## Configuration

### Main Configuration File (`config/config.yaml`)

```yaml
server:
  host: "0.0.0.0"
  port: 8000
  log_level: "INFO"

mopidy:
  rpc_url: "http://mopidy:6680/mopidy/rpc"
  timeout: 10

icecast:
  stream_url: "http://icecast:8000/mopidy"
  mount: "/mopidy"

llm:
  provider: "anthropic"  # or openai, ollama, azure, cohere
  model: "claude-3-5-sonnet-20241022"
  temperature: 0.7
  max_tokens: 2000
  # base_url: "http://localhost:11434"  # for Ollama

podcast_feeds:
  - name: "Radiolab"
    rss_url: "https://feeds.npr.org/510298/podcast.xml"
    tags: ["science", "storytelling"]
  # Add more feeds...

genre_mappings:
  - genre: "jazz"
    playlists: ["Jazz Classics"]
  # Add more mappings...
```

### Environment Variables (`.env`)

```bash
# LLM API Keys
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Mopidy
MOPIDY_RPC_URL=http://mopidy:6680/mopidy/rpc

# Icecast
ICECAST_STREAM_URL=http://icecast:8000/mopidy
```

## MCP Tools

The server exposes 11 tools for Home Assistant:

### Playback Control
- `get_stream_url()` - Get Icecast stream URL
- `now_playing()` - Get current playback info

### Music Tools
- `play_music_by_artist(artist, mode, limit, shuffle)` - Play artist's tracks
- `play_music_by_genre(genre, mode, limit, shuffle)` - Play genre-based music
- `play_playlist(name, mode, shuffle)` - Play playlist by name
- `play_song_search(query, mode, limit)` - Search and play songs

### Podcast Tools
- `play_podcast_latest(show, mode)` - Play latest episode
- `play_podcast_random(show, mode, recent_count)` - Play random episode
- `search_podcast(show, query, limit)` - Search episodes
- `play_podcast_episode(id, mode)` - Play specific episode
- `play_podcast_by_genre(genre, mode)` - Play by podcast genre

## Home Assistant Integration

### 1. Add MCP Integration in Home Assistant

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "Model Context Protocol"
3. Enter the MCP server URL: `http://media-resolver:8000/mcp`
4. Verify tools appear in the integration

### 2. Create Helper Scripts

Create a script in Home Assistant to play URLs in specific rooms:

```yaml
# configuration.yaml or scripts.yaml
script:
  play_url_in_area:
    fields:
      area_name:
        description: "Area name (e.g., living room)"
      url:
        description: "Media URL to play"
    sequence:
      - service: media_player.play_media
        target:
          entity_id: >
            {% set area_map = {
              'living room': 'media_player.living_room_speaker',
              'kitchen': 'media_player.kitchen_speaker',
              'bedroom': 'media_player.bedroom_speaker'
            } %}
            {{ area_map.get(area_name, 'media_player.default') }}
        data:
          media_content_id: "{{ url }}"
          media_content_type: "music"
```

### 3. Configure Assist Agent

Add instructions to your Home Assistant Assist agent configuration:

```
When the user requests music or podcast playback:

1. Determine the target room/area from the request
2. Call the appropriate MCP tool (e.g., play_music_by_artist, play_podcast_latest)
3. Extract the playback_url from the response
4. Call script.play_url_in_area with the area and URL
5. If requires_clarification is true, ask the clarification_question
```

### Example Usage

```
User: "Play Beatles songs in the living room"
Assistant:
  1. Calls play_music_by_artist(artist="Beatles", mode="replace", shuffle=true)
  2. Gets response: {playback_url: "http://icecast:8000/mopidy", ...}
  3. Calls script.play_url_in_area(area_name="living room", url="...")
  4. Confirms: "Playing Beatles in the living room"
```

## Docker Deployment

### Build Image

```bash
docker build -t media-resolver-mcp:latest .
```

### Run with Docker Compose

```yaml
version: '3.8'

services:
  media-resolver:
    image: media-resolver-mcp:latest
    container_name: media-resolver
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      MOPIDY_RPC_URL: "http://mopidy:6680/mopidy/rpc"
      ICECAST_STREAM_URL: "http://icecast:8000/mopidy"
      ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"
      LLM_PROVIDER: "anthropic"
      LLM_MODEL: "claude-3-5-sonnet-20241022"
    volumes:
      - ./config:/app/config
    depends_on:
      - mopidy
      - icecast
```

## Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: media-resolver
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: media-resolver
        image: media-resolver-mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: MOPIDY_RPC_URL
          value: "http://mopidy-service:6680/mopidy/rpc"
        - name: ICECAST_STREAM_URL
          value: "http://icecast-service:8000/mopidy"
        - name: ANTHROPIC_API_KEY
          valueFrom:
            secretKeyRef:
              name: media-resolver-secrets
              key: anthropic-api-key
        volumeMounts:
        - name: config
          mountPath: /app/config
---
apiVersion: v1
kind: Service
metadata:
  name: media-resolver-service
spec:
  selector:
    app: media-resolver
  ports:
  - port: 8000
    targetPort: 8000
```

## Admin Web UI

Access the admin UI at `http://localhost:8000/admin` to:

- **Dashboard**: View statistics and system status
- **Configuration**: Update LLM settings in real-time
- **Testing**: Test disambiguation with sample data
- **Request History**: View detailed logs with LLM reasoning

### Swapping LLM Backends

The admin UI allows you to swap LLM providers without restarting:

1. Go to `/admin/config`
2. Select provider (Anthropic, OpenAI, Ollama, etc.)
3. Enter model name
4. Adjust temperature and token limits
5. Click "Update Configuration"

Changes apply immediately to new requests.

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
```

### Project Structure

```
media-selector-mcp/
├── src/media_resolver/
│   ├── server.py              # FastMCP server entry point
│   ├── config.py               # Configuration management
│   ├── models.py               # Pydantic data models
│   ├── request_logger.py       # Request logging
│   ├── tools/                  # MCP tool implementations
│   │   ├── music.py
│   │   ├── podcast.py
│   │   └── playback.py
│   ├── mopidy/                 # Mopidy client
│   │   ├── client.py
│   │   └── capabilities.py
│   ├── podcast/                # Podcast resolution
│   │   ├── rss_parser.py
│   │   └── resolver.py
│   ├── disambiguation/         # LLM disambiguation
│   │   ├── service.py
│   │   └── llm_provider.py
│   └── admin/                  # Web admin UI
│       ├── routes.py
│       └── templates/
├── tests/
├── config/
│   └── config.yaml.example
├── Dockerfile
├── pyproject.toml
└── README.md
```

## Troubleshooting

### Mopidy Connection Issues

- Verify Mopidy is running: `curl http://mopidy:6680/mopidy/api`
- Check RPC URL in configuration
- Ensure Mopidy HTTP extension is enabled

### Icecast Stream Not Playing

- Verify Icecast is accessible from playback devices
- Check firewall rules
- Test stream URL: `curl http://icecast:8000/mopidy`

### LLM Errors

- Verify API key is set correctly
- Check model name is valid for your provider
- For Ollama: ensure base_url is set and Ollama is running

### Podcast Feeds Not Loading

- Verify RSS URL is accessible
- Check feed format (must have audio enclosures)
- Look in request history for detailed errors

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please open an issue or pull request.

## Credits

Built with:
- [FastMCP](https://github.com/anthropics/fastmcp) - MCP server framework
- [LangChain](https://github.com/langchain-ai/langchain) - LLM orchestration
- [Mopidy](https://mopidy.com/) - Music server
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [htmx](https://htmx.org/) - Dynamic UI updates
