#!/bin/bash
#
# Local Testing Helper Script for Mac
#
# This script sets up and runs the EPG generator locally on macOS
# for development and testing purposes.
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Component and repository directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_ROOT="$SCRIPT_DIR/.venv"
cd "$SCRIPT_DIR"

# Log functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Python 3 is installed
check_python() {
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 is not installed. Please install Python 3.8 or later."
        log_info "Install using: brew install python3"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    log_success "Found Python $PYTHON_VERSION"
}

# Create virtual environment if it doesn't exist
setup_venv() {
    if [ ! -d "$VENV_ROOT" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv "$VENV_ROOT"
        log_success "Virtual environment created"
    else
        log_info "Virtual environment already exists"
    fi
}

# Activate virtual environment
activate_venv() {
    log_info "Activating virtual environment..."
    source "$VENV_ROOT/bin/activate"
}

# Install dependencies
install_deps() {
    log_info "Installing dependencies..."
    pip install --upgrade pip > /dev/null 2>&1
    pip install -r "$SCRIPT_DIR/requirements.txt"
    log_success "Dependencies installed"
}

# Create output directories
setup_dirs() {
    log_info "Setting up output directories..."
    mkdir -p output/EPG/NZL
    mkdir -p output/EPG/AUS/SYD
    mkdir -p output/EPG/AUS/BNE
    mkdir -p output/EPG/AUS/ADL
    mkdir -p output/EPG/AUS/OOL
    mkdir -p output/EPG/AUS/MEL
    mkdir -p debug
    log_success "Output directories created"
}

# Run the EPG generator
run_epg() {
    log_info "Starting EPG generation..."
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    export OUTPUT_DIR="$SCRIPT_DIR/output"
    export DEBUG_DIR="$SCRIPT_DIR/debug"

    cd src
    python3 main.py
    EXIT_CODE=$?
    cd "$SCRIPT_DIR"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ $EXIT_CODE -eq 0 ]; then
        log_success "EPG generation completed successfully!"
    else
        log_error "EPG generation failed with exit code $EXIT_CODE"
        exit $EXIT_CODE
    fi
}

# Show generated files
show_results() {
    log_info "Generated bundles:"
    echo ""

    if [ -d "output/EPG" ]; then
        find output/EPG -name "*.zip" -type f | while read -r file; do
            SIZE=$(du -h "$file" | cut -f1)
            echo "  📦 $file ($SIZE)"
        done

        BUNDLE_COUNT=$(find output/EPG -name "*.zip" -type f | wc -l | tr -d ' ')
        echo ""
        log_success "Total bundles created: $BUNDLE_COUNT"
    else
        log_warning "No bundles were created"
    fi
}

# Clean up old bundles
clean() {
    log_warning "Cleaning old bundles and debug files..."
    rm -rf output/EPG/*
    rm -rf debug/*
    log_success "Cleanup complete"
}

# Show usage
usage() {
    cat << EOF
Usage: $0 [OPTION]

Local testing helper script for the EPG generator on macOS.

Options:
    (no args)   Run EPG generation with full setup
    --clean     Clean old bundles and debug files, then run
    --setup     Only set up environment (venv, dependencies)
    --help      Show this help message

Examples:
    $0              # Run EPG generation
    $0 --clean      # Clean and run
    $0 --setup      # Set up environment only

Environment Variables:
    LOG_LEVEL       Set logging level (DEBUG, INFO, WARNING, ERROR)
                    Example: LOG_LEVEL=DEBUG $0

Output:
    ./output/EPG/   Generated EPG bundles
    ./debug/        Debug JSON files

EOF
}

# Main script logic
main() {
    case "${1:-}" in
        --help|-h)
            usage
            exit 0
            ;;
        --clean)
            log_info "Running in clean mode"
            clean
            ;;
        --setup)
            log_info "Setting up environment only"
            check_python
            setup_venv
            activate_venv
            install_deps
            setup_dirs
            log_success "Environment setup complete!"
            log_info "To activate the virtual environment manually:"
            log_info "  source epg_generator/.venv/bin/activate"
            exit 0
            ;;
        "")
            # Default: full run
            ;;
        *)
            log_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac

    # Full run
    echo ""
    log_info "═══════════════════════════════════════════════════════"
    log_info "  ProCentric EPG Generator - Local Testing"
    log_info "═══════════════════════════════════════════════════════"
    echo ""

    check_python
    setup_venv
    activate_venv
    install_deps
    setup_dirs

    echo ""
    run_epg
    echo ""

    show_results

    echo ""
    log_info "═══════════════════════════════════════════════════════"
    log_success "All done!"
    log_info "═══════════════════════════════════════════════════════"
    echo ""
    log_info "Next steps:"
    log_info "  • Check bundles in: ./epg_generator/output/EPG/"
    log_info "  • View debug data in: ./epg_generator/debug/"
    log_info "  • Run again: ./epg_generator/run_local.sh"
    log_info "  • Clean and run: ./epg_generator/run_local.sh --clean"
    echo ""
}

# Run main function
main "$@"
