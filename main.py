#!/usr/bin/env python3
import sys
import os

# Ensure the project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ui.app import SpotDLApp
from app.core.constants import APP_NAME, APP_VERSION

if __name__ == "__main__":
    app = SpotDLApp()
    app.mainloop()
