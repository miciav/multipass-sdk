class MultipassError(Exception):
    """Base exception for all multipass-sdk errors."""


class MultipassCommandError(MultipassError):
    def __init__(self, args: list[str], returncode: int, stdout: str, stderr: str):
        self.args_list = args
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"Command {args} failed with exit code {returncode}: {stderr or stdout}"
        )


class MultipassNotInstalledError(MultipassError):
    def __init__(self) -> None:
        super().__init__(
            "Multipass binary not found. Install from https://multipass.run"
        )


class VmNotFoundError(MultipassError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"VM '{name}' not found")


class VmAlreadyRunningError(MultipassError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"VM '{name}' is already running")


class VmNotRunningError(MultipassError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"VM '{name}' is not running")


class VmAlreadySuspendedError(MultipassError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"VM '{name}' is already suspended")


class MultipassTimeoutError(MultipassError):
    def __init__(self, name: str, timeout: float) -> None:
        self.name = name
        self.timeout = timeout
        super().__init__(f"VM '{name}' did not become ready within {timeout}s")
