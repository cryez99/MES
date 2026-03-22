import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import main

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()