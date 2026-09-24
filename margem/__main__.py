"""Permite `python -m margem`, alem do console script `margem`."""
import sys

from margem.pipeline import main

sys.exit(main())
