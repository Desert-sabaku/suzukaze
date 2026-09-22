"""Run the installed gesture detection package."""

from multiprocessing import freeze_support

from .app import main

if __name__ == "__main__":
    freeze_support()
    main()
