"""
Security sandbox for execute_python and execute_shell.

Blocks dangerous operations that could:
- Delete files (rm, os.remove, shutil.rmtree)
- Modify system settings
- Access sensitive paths

Adapted from Houdini Agent v2's sandbox.py.
"""

import re
import os
from typing import List

# ── Python Sandbox ──────────────────────────────────────────────────

PYTHON_BLOCKED_PATTERNS: List[str] = [
    # File deletion
    r'\bos\.remove\s*\(',
    r'\bos\.unlink\s*\(',
    r'\bshutil\.rmtree\s*\(',
    r'\bshutil\.move\s*\(',
    r'\bos\.rmdir\s*\(',
    r'\bos\.removedirs\s*\(',

    # Process / system
    r'\bos\.system\s*\(',
    r'\bsubprocess\.',
    r'\bos\.popen',
    r'\bos\.execv',
    r'\bos\.spawn',

    # Network (prevent exfiltration)
    r'\bsocket\b',
    r'\brequests\.post\s*\(',
    r'\burllib\.request\.urlopen\s*\(',
    r'\bftplib\.',
    r'\bhttp\.client\b',

    # Permission changes
    r'\bos\.chmod\s*\(',
    r'\bos\.chown\s*\(',
    r'\bos\.setuid\s*\(',

    # Dangerous file writes
    r'\bopen\s*\([^)]*[\'"]w[\'"]',
    r'\bopen\s*\([^)]*[\'"]a[\'"]',

    # Module manipulation
    r'\bimportlib\.',
    r'\b__import__\s*\(',
    r'\bcompile\s*\(',
    r'\beval\s*\(',
    r'\bexec\s*\(',
]


class Sandbox:
    """Security sandbox for code and shell execution."""

    # ── Python Code ─────────────────────────────────────────────

    def is_python_safe(self, code: str) -> bool:
        """Check if Python code is safe to execute."""
        for pattern in PYTHON_BLOCKED_PATTERNS:
            if re.search(pattern, code):
                return False
        return True

    def get_python_violations(self, code: str) -> List[str]:
        """Get list of violated patterns for error reporting."""
        violations = []
        for pattern in PYTHON_BLOCKED_PATTERNS:
            if re.search(pattern, code):
                violations.append(pattern)
        return violations

    # ── Shell Commands ──────────────────────────────────────────

    SHELL_BLOCKED_COMMANDS: List[str] = [
        "rm -rf", "rm -r", "del /s", "del /f",
        "format ", "mkfs.",
        "shutdown", "reboot", "halt",
        "dd if=", "dd if",
        "> /dev/sd", "> /dev/hd",
        "chmod 777", "chmod -R",
        "wget ", "curl ",
        "nc ", "ncat ", "telnet ",
        ":(){ :|:& };:",
        "> ~/.ssh", "> /etc/", "> ~/.bash",
    ]

    SHELL_ALLOWED_PREFIXES: List[str] = [
        "pip ", "python ", "hython ",
        "git ", "hg ",
        "echo ", "cat ", "head ", "tail ",
        "ls ", "dir ", "find ",
        "cp ", "mv ", "mkdir ", "touch ",
        "houdini", "hkey ", "hserver ",
    ]

    def is_shell_safe(self, command: str) -> bool:
        """Check if a shell command is safe."""
        cmd_lower = command.lower().strip()

        for blocked in self.SHELL_BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                return False

        for prefix in self.SHELL_ALLOWED_PREFIXES:
            if cmd_lower.startswith(prefix):
                return True

        if "houdini" in cmd_lower:
            return True

        return False

    def get_shell_violations(self, command: str) -> List[str]:
        """Get violations for a shell command."""
        violations = []
        cmd_lower = command.lower()
        for blocked in self.SHELL_BLOCKED_COMMANDS:
            if blocked in cmd_lower:
                violations.append(blocked)
        return violations

    # ── Path Sandbox ────────────────────────────────────────────

    DANGEROUS_PATHS: List[str] = [
        "/etc/", "C:\\Windows\\", "/boot/", "/sys/",
        "~/.ssh", "~/.gnupg", "/var/log/",
        ".bashrc", ".zshrc", ".profile",
    ]

    def is_path_safe(self, path: str) -> bool:
        """Check if a file path targets safe locations."""
        expanded = os.path.expanduser(path)
        for dangerous in self.DANGEROUS_PATHS:
            if dangerous in path or dangerous in expanded:
                return False
        return True


# Singleton
_sandbox = Sandbox()


def get_sandbox() -> Sandbox:
    return _sandbox
