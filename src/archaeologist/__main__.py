"""Allow `python -m archaeologist`."""
import sys
from .cli import main

sys.exit(main())
