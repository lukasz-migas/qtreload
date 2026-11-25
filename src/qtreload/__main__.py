"""Run a Qt application with hot reloading: python -m qtreload [options] (script.py | -m module) [arguments]."""

from qtreload.launch import cli

if __name__ == "__main__":
    cli()
