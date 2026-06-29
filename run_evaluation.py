#!/usr/bin/env python
import sys

from evisi_eval.cli import main


if __name__ == "__main__":
    sys.argv.insert(1, "run")
    main()
