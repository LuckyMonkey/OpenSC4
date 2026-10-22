"""Bounded binary line transport; timeout poisons and terminates the helper."""
import os
import ctypes
import signal
import selectors
import subprocess
import time


def terminate_with_parent():
    """Linux helper lifetime follows the sidecar even if the host kills it."""
    parent = os.getppid()
    if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError('cannot configure helper parent-death signal')
    if os.getppid() != parent or parent == 1:
        os.kill(os.getpid(), signal.SIGKILL)


class TransportError(RuntimeError):
    pass


class HelperTransport:
    def __init__(self, process, timeout=30.0, max_reply=32 * 1024 * 1024):
        self.process = process
        self.timeout = timeout
        self.max_reply = max_reply
        self.failed = False
        os.set_blocking(process.stdin.fileno(), False)
        os.set_blocking(process.stdout.fileno(), False)

    def exchange(self, command):
        if self.failed or self.process.poll() is not None:
            raise TransportError('helper unavailable')
        if '\n' in command or '\r' in command:
            raise TransportError('multiline helper command rejected')
        deadline = time.monotonic() + self.timeout
        data = memoryview((command + '\n').encode())
        reply = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdin, selectors.EVENT_WRITE)
                while data:
                    self._wait(selector, deadline)
                    try:
                        count = os.write(self.process.stdin.fileno(), data)
                        data = data[count:]
                    except BlockingIOError:
                        continue
                selector.unregister(self.process.stdin)
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while True:
                    self._wait(selector, deadline)
                    try:
                        block = os.read(self.process.stdout.fileno(), 65536)
                    except BlockingIOError:
                        continue
                    if not block:
                        raise TransportError('helper EOF')
                    reply.extend(block)
                    if len(reply) > self.max_reply:
                        raise TransportError('helper reply exceeds limit')
                    if b'\n' in block:
                        line, remainder = bytes(reply).split(b'\n', 1)
                        if remainder:
                            raise TransportError('unsolicited helper output')
                        return line.decode('utf-8')
        except (OSError, UnicodeError, TransportError) as exc:
            self.failed = True
            self.terminate()
            raise TransportError(str(exc)) from exc

    @staticmethod
    def _wait(selector, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not selector.select(remaining):
            raise TransportError('helper deadline exceeded')

    def terminate(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=2)

    def close(self):
        self.terminate()
        self.process.stdin.close()
        self.process.stdout.close()
