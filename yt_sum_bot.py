#!/usr/bin/env python3
"""
Production-ready Telegram bot for YT_Sum
Main entry point for the application
"""

import sys
import os
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import yaml
import log_mod
import src.telegram_main as telegram_main

def load_config():
    """Load production configuration"""
    config_path = Path(__file__).parent / "config_prod" / "app.yaml"
    
    if not config_path.exists():
        print(f"ERROR: Configuration file not found: {config_path}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"ERROR: Failed to read configuration: {e}")
        sys.exit(1)

def main():
    """Main entry point for the production bot"""
    print("🚀 YT_Sum Telegram Bot Starting...")
    
    # Load configuration
    config = load_config()
    
    # Initialize logging
    log_mod.init_logging(config)
    log = log_mod.log
    
    log("INFO", "main", "YT_Sum Telegram Bot Starting")
    
    # Start Telegram bot
    try:
        telegram_main.telegram_worker_loop(config, log)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        log("INFO", "main", "Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        log("ERROR", "main", "Fatal error", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()