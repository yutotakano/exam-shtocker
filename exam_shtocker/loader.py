from threading import Thread
from itertools import cycle
from time import sleep
from shutil import get_terminal_size
from colorama import Fore


class Loader:
    def __init__(
        self, desc: str = "Loading...", end: str = "Done!", timeout: float = 0.1
    ):
        """
        A loader-like context manager

        Args:
            desc (str, optional): The loader's description. Defaults to "Loading...".
            end (str, optional): Final print. Defaults to "Done!".
            timeout (float, optional): Sleep time between prints. Defaults to 0.1.
        """
        self.desc = desc
        self.end = end
        self.timeout = timeout

        self._thread = Thread(target=self._animate, daemon=True)
        self.steps = ["⢿", "⣻", "⣽", "⣾", "⣷", "⣯", "⣟", "⡿"]
        self.done = False

    def start(self):
        self._thread.start()
        return self

    def _animate(self):
        for c in cycle(self.steps):
            if self.done:
                break
            cols = get_terminal_size((80, 20)).columns
            print("\r" + " " * cols, end="", flush=True)
            print(f"\r{c} {self.desc}", flush=True, end="")
            sleep(self.timeout)

    def __enter__(self):
        self.start()

    def cancel(self, end: str = "Failed!"):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(
            f"\r{Fore.RED}⨯{Fore.RESET} {self.desc} {Fore.RED}{end}{Fore.RESET}",
            flush=True,
        )

    def stop(self, end: str = "Done!"):
        self.done = True
        cols = get_terminal_size((80, 20)).columns
        print("\r" + " " * cols, end="", flush=True)
        print(
            f"\r{Fore.GREEN}✓{Fore.RESET} {self.desc} {Fore.GREEN}{end}{Fore.RESET}",
            flush=True,
        )

    def __exit__(self, exc_type: type, exc_value: Exception, tb: object):
        # handle exceptions with those variables ^
        if exc_type:
            self.cancel(str(exc_value))
            return True
        self.stop(self.end)
