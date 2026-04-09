# Local Testing Guide

This guide explains how to run the EPG generator locally on macOS for development and testing.

## Quick Start

The easiest way to run locally is using the provided helper script:

```bash
./epg_generator/run_local.sh
```

This will automatically:
- ✅ Check Python installation
- ✅ Create virtual environment
- ✅ Install dependencies
- ✅ Set up output directories
- ✅ Run EPG generation
- ✅ Display results

## Prerequisites

- **macOS** (10.14 or later)
- **Python 3.8+** (install via: `brew install python3`)
- **Internet connection** (for fetching EPG data)

## Script Options

### Run EPG Generation
```bash
./epg_generator/run_local.sh
```
Default mode - runs full EPG generation.

### Clean and Run
```bash
./epg_generator/run_local.sh --clean
```
Removes old bundles and debug files, then runs generation.

### Setup Only
```bash
./epg_generator/run_local.sh --setup
```
Only sets up the environment without running generation. Useful for first-time setup.

### Help
```bash
./epg_generator/run_local.sh --help
```
Display usage information.

## Environment Variables

### Control Log Level

```bash
# Default (INFO)
./epg_generator/run_local.sh

# Debug mode (verbose)
LOG_LEVEL=DEBUG ./epg_generator/run_local.sh

# Warnings and errors only
LOG_LEVEL=WARNING ./epg_generator/run_local.sh

# Errors only
LOG_LEVEL=ERROR ./epg_generator/run_local.sh
```

## Output Locations

### Generated Bundles
```
epg_generator/output/EPG/
├── NZ/
│   └── Procentric_EPG_NZL_20250108.zip
└── AUS/
    ├── SYD/Procentric_EPG_SYD_20250108.zip
    ├── BNE/Procentric_EPG_BNE_20250108.zip
    ├── ADL/Procentric_EPG_ADL_20250108.zip
    ├── OOL/Procentric_EPG_OOL_20250108.zip
    └── MEL/Procentric_EPG_MEL_20250108.zip
```

### Debug Files
```
debug/
└── debug_skynz.json  # Raw GraphQL response from Sky NZ
```

## Manual Setup (Alternative)

If you prefer manual control:

### 1. Create Virtual Environment
```bash
python3 -m venv epg_generator/.venv
```

### 2. Activate Virtual Environment
```bash
source epg_generator/.venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r epg_generator/requirements.txt
```

### 4. Run the Script
```bash
cd epg_generator/src
python3 main.py
```

## Troubleshooting

### Python Not Found
```bash
# Install Python 3 via Homebrew
brew install python3

# Verify installation
python3 --version
```

### Permission Denied
```bash
chmod +x epg_generator/run_local.sh
```

### Dependencies Installation Fails
```bash
# Upgrade pip first
pip install --upgrade pip

# Then try again
pip install -r epg_generator/requirements.txt
```

### "Module not found" Error
Make sure you're running from the correct directory:
```bash
cd /path/to/ProCentricEPG
./epg_generator/run_local.sh
```

Or activate the virtual environment:
```bash
source epg_generator/.venv/bin/activate
```

### Network Timeout
The script fetches EPG data from external APIs. If you see timeout errors:

1. **Check internet connection**
2. **Try again** - APIs may be temporarily unavailable
3. **Increase timeout** in source files:
   - `epg_generator/src/epg_sources/sky_nz/main.py` - line 112 (default: 30s)
   - `epg_generator/src/epg_sources/xmltv_net/main.py` - line 38 (default: 60s)

### Memory Issues
If processing large datasets causes memory issues:
```bash
# Increase Python's memory limit
PYTHONMALLOC=malloc ./epg_generator/run_local.sh
```

## Testing Specific Cities

To test only specific cities, modify `epg_generator/src/main.py`:

```python
# Comment out cities you don't want to test
cities = [
    {"city": "SYD", ...},  # Keep Sydney
    # {"city": "BNE", ...},  # Comment out Brisbane
    # {"city": "ADL", ...},  # Comment out Adelaide
    # etc.
]
```

## Validating Output

### Check Bundle Contents
```bash
# Extract and view a bundle
unzip epg_generator/output/EPG/NZL/Procentric_EPG_NZL_20250108.zip -d temp/
cat temp/Procentric_EPG.json | python3 -m json.tool | less
```

### Verify JSON Structure
```bash
# Validate JSON syntax
python3 -m json.tool epg_generator/output/EPG/NZL/Procentric_EPG.json > /dev/null
echo "Valid JSON!"
```

### Check Bundle Size
```bash
# List all bundles with sizes
find epg_generator/output/EPG -name "*.zip" -exec ls -lh {} \;
```

## Performance Testing

### Measure Execution Time
```bash
time ./epg_generator/run_local.sh
```

### Profile Python Performance
```bash
cd epg_generator/src
python3 -m cProfile -o profile.stats main.py
python3 -m pstats profile.stats
# In pstats prompt:
# >>> sort cumulative
# >>> stats 20
```

## Development Workflow

1. **Make code changes**
2. **Run local test**: `./epg_generator/run_local.sh --clean`
3. **Check output**: Verify bundles in `epg_generator/output/EPG/`
4. **Debug if needed**: Check `debug/` files
5. **Iterate**

## IDE Setup

### VS Code
1. Open folder in VS Code
2. Select Python interpreter: `Command+Shift+P` → "Python: Select Interpreter"
3. Choose: `./epg_generator/.venv/bin/python3`

### PyCharm
1. Open project
2. Settings → Project → Python Interpreter
3. Add interpreter → Existing environment
4. Select: `./epg_generator/.venv/bin/python3`

## Continuous Testing

### Watch for Changes (requires fswatch)
```bash
# Install fswatch
brew install fswatch

# Auto-run on file changes
fswatch -o epg_generator/src/ | xargs -n1 -I{} ./epg_generator/run_local.sh
```

## Comparing with Docker Output

To ensure local testing matches Docker behavior:

```bash
# Run locally
./epg_generator/run_local.sh

# Run in Docker
docker-compose run --rm -e RUN_ONCE=true epg-generator

# Compare outputs
diff -r epg_generator/output/EPG/ bundles/EPG/
```

## Clean Up

### Remove Virtual Environment
```bash
rm -rf epg_generator/.venv/
```

### Remove All Generated Files
```bash
./epg_generator/run_local.sh --clean
# or
rm -rf epg_generator/output/ epg_generator/debug/
```

## Next Steps

- ✅ Local testing working? Try [DOCKER.md](DOCKER.md) for containerized deployment
- ✅ Found a bug? Check the code review in the git history
- ✅ Want to contribute? Follow the development workflow above
