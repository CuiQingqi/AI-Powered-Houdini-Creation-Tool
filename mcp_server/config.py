"""
Configuration reader for MCP Server.

Reads from config/houdini_ai.ini and provides dataclass-based access.
"""

import os
from configparser import ConfigParser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 9877


@dataclass
class McpServerConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    transport: str = "streamable-http"


@dataclass
class WebUIConfig:
    port: int = 9000
    auto_open: bool = True


@dataclass
class AIConfig:
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    openai_model: str = "deepseek-chat"
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-4-20250514"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3"
    max_iterations: int = 20
    temperature: float = 0.7
    context_limit: int = 128000

    def as_dict(self) -> Dict[str, any]:
        """Convert to dict for provider creation."""
        return {
            "provider": self.provider,
            "openai_api_key": self.openai_api_key,
            "openai_base_url": self.openai_base_url,
            "openai_model": self.openai_model,
            "anthropic_api_key": self.anthropic_api_key,
            "anthropic_base_url": self.anthropic_base_url,
            "anthropic_model": self.anthropic_model,
            "ollama_base_url": self.ollama_base_url,
            "ollama_model": self.ollama_model,
            "temperature": self.temperature,
        }

    @property
    def is_configured(self) -> bool:
        """Check if any API key is set."""
        if self.provider in ("openai", "deepseek", "glm"):
            return bool(self.openai_api_key)
        if self.provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.provider == "ollama":
            return True  # No API key needed for local
        return False


@dataclass
@dataclass
class ObsidianConfig:
    vault_path: str = ""
    auto_save: bool = True


@dataclass
class AppConfig:
    bridge: BridgeConfig = field(default_factory=BridgeConfig)
    mcp_server: McpServerConfig = field(default_factory=McpServerConfig)
    web_ui: WebUIConfig = field(default_factory=WebUIConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    obsidian: ObsidianConfig = field(default_factory=ObsidianConfig)
    log_level: str = "INFO"
    log_dir: str = "logs"

    @property
    def bridge_url(self) -> str:
        return f"ws://{self.bridge.host}:{self.bridge.port}"

    @property
    def mcp_url(self) -> str:
        return f"http://{self.mcp_server.host}:{self.mcp_server.port}/mcp"

    @property
    def web_ui_url(self) -> str:
        return f"http://{self.mcp_server.host}:{self.web_ui.port}"


def find_config_dir() -> Path:
    """Find the config directory relative to this package."""
    this_dir = Path(__file__).resolve().parent.parent  # selfHoudiniAgent/
    return this_dir / "config"


def find_web_ui_dir() -> Path:
    """Find the Web UI directory relative to this package."""
    this_dir = Path(__file__).resolve().parent.parent  # selfHoudiniAgent/
    return this_dir / "web_ui"


def read_config() -> AppConfig:
    """Read configuration from config/houdini_ai.ini."""
    config = AppConfig()
    ini_path = find_config_dir() / "houdini_ai.ini"

    if not ini_path.exists():
        return config

    parser = ConfigParser()
    parser.read(str(ini_path), encoding="utf-8")

    if parser.has_section("bridge"):
        config.bridge.host = parser.get("bridge", "host", fallback="127.0.0.1")
        config.bridge.port = parser.getint("bridge", "port", fallback=9877)

    if parser.has_section("mcp_server"):
        config.mcp_server.host = parser.get("mcp_server", "host", fallback="127.0.0.1")
        config.mcp_server.port = parser.getint("mcp_server", "port", fallback=9000)
        config.mcp_server.transport = parser.get("mcp_server", "transport", fallback="streamable-http")

    if parser.has_section("web_ui"):
        config.web_ui.port = parser.getint("web_ui", "port", fallback=9000)
        config.web_ui.auto_open = parser.getboolean("web_ui", "auto_open", fallback=True)

    if parser.has_section("ai"):
        config.ai.provider = parser.get("ai", "provider", fallback="deepseek")
        config.ai.model = parser.get("ai", "model", fallback="deepseek-chat")
        config.ai.openai_api_key = parser.get("ai", "openai_api_key", fallback="")
        config.ai.openai_base_url = parser.get("ai", "openai_base_url", fallback="https://api.deepseek.com/v1")
        config.ai.openai_model = parser.get("ai", "openai_model", fallback="deepseek-chat")
        config.ai.anthropic_api_key = parser.get("ai", "anthropic_api_key", fallback="")
        config.ai.anthropic_base_url = parser.get("ai", "anthropic_base_url", fallback="https://api.anthropic.com")
        config.ai.anthropic_model = parser.get("ai", "anthropic_model", fallback="claude-sonnet-4-20250514")
        config.ai.ollama_base_url = parser.get("ai", "ollama_base_url", fallback="http://localhost:11434/v1")
        config.ai.ollama_model = parser.get("ai", "ollama_model", fallback="llama3")
        config.ai.max_iterations = parser.getint("ai", "max_iterations", fallback=20)
        config.ai.temperature = parser.getfloat("ai", "temperature", fallback=0.7)
        config.ai.context_limit = parser.getint("ai", "context_limit", fallback=128000)

    if parser.has_section("obsidian"):
        config.obsidian.vault_path = parser.get("obsidian", "vault_path", fallback="")
        config.obsidian.auto_save = parser.getboolean("obsidian", "auto_save", fallback=True)

    if parser.has_section("logging"):
        config.log_level = parser.get("logging", "level", fallback="INFO")
        config.log_dir = parser.get("logging", "dir", fallback="logs")

    return config
