# InstagramProfileCrawler

Create optimized image datasets from Instagram profiles for LoRA training, with optional Visual AI filtering and automatic caption generation.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Status](https://img.shields.io/badge/status-alpha-orange.svg)

## Features

### Core Functionality
- 📸 **Profile Scraping** - Extract posts and story highlights from Instagram profiles
- 📥 **Image Download** - Download images at optimal resolution for LoRA training
- 🎨 **Image Optimization** - Process images for consistent dimensions and quality
- 🔄 **Deduplication** - Remove duplicate images using content-based hashing
- 📊 **Statistics Tracking** - Comprehensive metrics for every processing step

### Visual AI Integration
- 🤖 **Ollama Support** - Integrate with local AI models for advanced processing
- ✍️ **Automatic Captioning** - Generate descriptive captions for each image
- 🏷️ **Smart Tagging** - Extract relevant tags and metadata
- 🔍 **Image Filtering** - Automatically filter out low-quality or unsuitable images
- 💬 **Caption Pairs** - Generate prompt/negative prompt pairs for LoRA training

## Installation

### Prerequisites
- Python 3.10 or higher
- Ollama (for Visual AI features) - [Install Ollama](https://ollama.ai)

### Quick Start

```bash
# Clone repository
git clone https://github.com/instagram-profile-crawler/InstagramProfileCrawler.git
cd InstagramProfileCrawler

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\Activate.ps1
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Install Playwright browsers
python -m playwright install

# Run with default settings
instagram-crawler username
# Or run via main.py directly
python main.py username
```

## Configuration

### Environment Variables (.env)

Create a `.env` file in the project root:

```env
# Instagram Session
INSTAGRAM_SESSION_ID=your_session_id_here

# Visual AI (Ollama)
VISUAL_AI_ROUTE=http://localhost:11434/api/generate
VISUAL_AI_MODEL=llava

# Processing Settings
OUTPUT_DIR=./dataset
MAX_IMAGES=1000
RATE_LIMIT_DELAY=1
IMAGE_QUALITY=90
TARGET_SIZE_MB=5

# Caption Generation
GENERATE_CAPTIONS=true
CAPTION_PAIRS_FORMAT=json

# Image Filtering
FILTERING_ENABLED=true
MIN_CONFIDENCE=0.7
FILTERING_PROMPT="keep only images of beautifull backgounds and nature, exclude people. (This is an example guideline that will be used by the visual model to filter out images, edit it before use)"
```

### YAML Configuration (config/settings.yaml)

```yaml
profile:
  username: "instagram_username"
  max_posts: 100

output:
  format: "json"
  include_metadata: true

visual_ai:
  enabled: true
  model: "llava"
  generate_captions: true

processing:
  optimize_images: true
  target_size_mb: 5
  deduplicate: true
```

## Usage

### Basic Usage

```bash
# Scrape a single profile
instagram-crawler username

# With specific options
instagram-crawler username --max-posts 200 --output ./my_dataset

# Optimize images for LoRA
instagram-crawler username --optimize --deduplicate

# Generate captions with Visual AI
instagram-crawler username --generate-captions --caption-format json

# Filter images using AI
instagram-crawler username --filter
```

### Batch Processing

```bash
# Create a batch file (batch.txt)
echo "username1" > batch.txt
echo "username2" >> batch.txt
echo "username3" >> batch.txt

# Process all usernames
instagram-crawler --batch batch.txt
```

### Command-Line Options

```
positional arguments:
  username              Instagram username to scrape (default: None)

profile options:
  --max-posts, -m       Maximum number of posts to scrape (default: 100)

output options:
  --output, -o          Output directory for downloaded images (default: ./dataset)

processing options:
  --optimize            Optimize images for LoRA training
  --deduplicate         Remove duplicate images

Visual AI options:
  --generate-captions   Generate captions using Visual AI
  --caption-format      Format for caption output (text/json/pairs)
  --filter              Filter images using Visual AI

batch options:
  --batch               Batch file with list of usernames

verbosity:
  --verbose, -v         Enable verbose output
  --quiet, -q           Minimal output
```

## Output Formats

### Caption Pairs (JSON)

```json
{
  "image": "sunset_mountains",
  "prompt": "beautiful sunset over mountains with orange and pink sky",
  "negative_prompt": "blurry, low quality, watermark, logo, screenshot",
  "confidence": 0.92,
  "tags": ["sunset", "mountains", "nature", "landscape"],
  "timestamp": "2026-05-06T10:30:00Z"
}
```

### Caption Pairs (Text)

```
# Pairs format (one per line)
prompt_image: beautiful sunset over mountains with orange and pink sky
negative_prompt_image: blurry, low quality, watermark, logo, screenshot
```

## Visual AI Models

Supported models via Ollama:

- **llava** - General vision-language model (recommended)
- **babyllama** - Lightweight vision model
- **mistral** - Advanced reasoning with vision

Supported models via llama.cpp:

- Any HuggingFace GGUF Vision model (e.g., LLaVA, Gemma, Qwen-VL)
Note: download mmproj file for your model from HuggingFace GGUF models for best results, run the model with --mmproj parameter 

## Project Structure

```
InstagramProfileCrawler/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Command-line interface
│   ├── instagram/
│   │   ├── __init__.py
│   │   ├── auth.py         # Instagram authentication
│   │   ├── scraper.py      # Profile scraping logic
│   │   └── models.py       # Data models
│   ├── images/
│   │   ├── __init__.py
│   │   ├── downloader.py  # Image downloading
│   │   ├── optimizer.py   # Image optimization
│   │   └── deduplicator.py # Duplicate detection
│   ├── filtering/
│   │   ├── __init__.py
│   │   └── visual_ai.py   # Visual AI integration
│   ├── config/
│   │   ├── __init__.py
│   │   ├── env.py         # Environment config
│   │   └── yaml.py        # YAML config
│   └── utils/
│       ├── __init__.py
│       ├── logger.py      # Rich-formatted logging
│       ├── retry.py       # Retry logic
│       └── stats.py       # Statistics tracking
├── config/
│   └── settings.yaml
├── tests/
├── .env.example
├── pyproject.toml
└── README.md
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/ tests/

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Acknowledgments

- [Playwright](https://playwright.dev/) - Web automation library
- [Ollama](https://ollama.ai) - Local AI model runner
- [Pillow](https://pillow.readthedocs.io/) - Python imaging library
- [Rich](https://rich.readthedocs.io/) - Pretty terminal output

## Roadmap

- [ ] Support for Instagram Reels
- [ ] Advanced image cropping and composition
- [ ] Multi-profile batch processing
- [ ] Web UI dashboard
- [ ] Support for additional AI models
- [ ] Real-time progress visualization
- [ ] Dataset validation tools

## Support

For issues, questions, or contributions:
- Open an [Issue](https://github.com/instagram-profile-crawler/InstagramProfileCrawler/issues)
- Create a [Pull Request](https://github.com/instagram-profile-crawler/InstagramProfileCrawler/pulls)
- Contact: dev@example.com

---

Made with ❤️ for AI researchers and creators.

