"""PyInstaller entry point for the GUI executable."""
import multiprocessing

from piirip.gui import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
