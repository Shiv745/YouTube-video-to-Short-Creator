import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from ui.studio_window import ShivStudioApp


def main():
    app = ShivStudioApp()
    app.mainloop()

if __name__ == "__main__":
    main()
