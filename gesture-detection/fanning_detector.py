"""Backward-compatible command-line entry point."""

import multiprocessing as mp

from gesture_detection.app import main

if __name__ == "__main__":
    mp.freeze_support()
    main()
