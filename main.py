#!/usr/bin/env python3
import sys
import os

# Ensure the project root is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ui.app import SpotDLApp
from app.core.constants import APP_NAME, APP_VERSION

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--internal-spotdl-run':
        # Internal bypass to use the bundled spotdl module directly
        sys.argv.pop(1)
        from spotdl.console.entry_point import console_entry_point
        sys.exit(console_entry_point())

    app = SpotDLApp()
    app.mainloop()
