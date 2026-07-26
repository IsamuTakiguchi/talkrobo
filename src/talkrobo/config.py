"""設定ファイル (config/config.yaml) の読み込み。"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config/config.yaml")
EXAMPLE_CONFIG_PATH = Path("config/config.example.yaml")


class ChildConfig(BaseModel):
    """子供の情報。name が空なら初回起動時に音声で聞く。"""

    name: str = ""
    reading: str = ""
    honorific: str = "くん"
    age: int = 6

    @property
    def is_configured(self) -> bool:
        return bool(self.name.strip())

    @property
    def call_name(self) -> str:
        """呼びかけに使う名前。例: 「はると」+「くん」→「はるとくん」"""
        return f"{self.name.strip()}{self.honorific.strip()}"

    @property
    def spoken_name(self) -> str:
        """TTS に渡す読み。reading があればそちらを優先する。"""
        base = self.reading.strip() or self.name.strip()
        return f"{base}{self.honorific.strip()}"


class LLMConfig(BaseModel):
    model: str = "claude-haiku-4-5"
    max_tokens: int = 300
    history_turns: int = 8
    effort: str = "low"


class STTConfig(BaseModel):
    model_size: str = "small"
    compute_type: str = "int8"
    device: str = "auto"
    language: str = "ja"


class TTSConfig(BaseModel):
    url: str = "http://127.0.0.1:50021"
    timeout: float = 20.0


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    max_record_seconds: float = 15.0
    input_device: int | str | None = None
    output_device: int | str | None = None


class FillerConfig(BaseModel):
    enabled: bool = True
    ack_after: float = 0.3
    thinking_after: float = 1.5
    wait_after: float = 3.5
    timeout_after: float = 8.0


class LimitsConfig(BaseModel):
    daily_limit_minutes: int = 30
    quiet_start: str = "20:00"
    quiet_end: str = "07:00"


class PriceRow(BaseModel):
    """per MTok の USD 単価。"""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


class BudgetConfig(BaseModel):
    monthly_yen: float = 1000.0
    warn_at_percent: int = 80
    usd_jpy: float = 155.0
    prices: dict[str, PriceRow] = Field(default_factory=dict)


class HardwareConfig(BaseModel):
    button_pin: int = 17
    tail_servo_pin: int = 18
    head_servo_pin: int = 27
    eye_led_pin: int = 12
    eye_led_count: int = 2
    cheek_led_pin: int = 13
    cheek_led_count: int = 2
    led_brightness: float = 0.4


class Config(BaseModel):
    persona: str = "pikachu"
    child: ChildConfig = Field(default_factory=ChildConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    filler: FillerConfig = Field(default_factory=FillerConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    data_dir: Path = Path("data")

    # 実行時に解決されるパス（YAML には書かない）
    root: Path = Path(".")

    @property
    def persona_path(self) -> Path:
        return self.root / "config" / "personas" / f"{self.persona}.yaml"

    @property
    def data_path(self) -> Path:
        path = self.data_dir
        if not path.is_absolute():
            path = self.root / path
        return path

    @property
    def profile_path(self) -> Path:
        return self.data_path / "profile.json"

    @property
    def usage_path(self) -> Path:
        return self.data_path / "usage.jsonl"

    @property
    def log_dir(self) -> Path:
        return self.data_path / "logs"

    @property
    def filler_cache_dir(self) -> Path:
        return self.data_path / "cache" / "fillers"

    @classmethod
    def load(cls, path: Path | None = None, root: Path | None = None) -> Config:
        """YAML を読み込む。存在しなければ example にフォールバックする。"""
        load_dotenv()
        root = root or Path.cwd()

        if path is None:
            candidate = root / DEFAULT_CONFIG_PATH
            path = candidate if candidate.exists() else root / EXAMPLE_CONFIG_PATH

        if not path.exists():
            raise FileNotFoundError(
                f"設定ファイルが見つかりません: {path}\n"
                f"`cp {EXAMPLE_CONFIG_PATH} {DEFAULT_CONFIG_PATH}` を実行してください。"
            )

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw["root"] = root
        return cls.model_validate(raw)


def get_api_key() -> str:
    """ANTHROPIC_API_KEY を取得する。未設定なら分かりやすく落とす。"""
    load_dotenv()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY が設定されていません。\n"
            "`cp .env.example .env` して API キーを書き込んでください。"
        )
    return key
