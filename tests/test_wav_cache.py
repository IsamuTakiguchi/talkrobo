"""相づちの事前合成キャッシュのテスト（VOICEVOX 不要）。"""

from __future__ import annotations

from talkrobo.tts.voicevox import build_wav_cache


class FakeVoicevoxClient:
    def __init__(self, voice_key: str = "v1") -> None:
        self.synth_calls: list[str] = []
        self._voice_key = voice_key

    def synth(self, text: str) -> bytes:
        self.synth_calls.append(text)
        return f"WAV:{text}".encode()

    def voice_key(self) -> str:
        return self._voice_key


def test_builds_files_and_mapping(tmp_path):
    client = FakeVoicevoxClient()
    cache = build_wav_cache(client, ["ピカ？", "ふんふん"], tmp_path, "persona1")

    assert set(cache) == {"ピカ？", "ふんふん"}
    assert all(path.exists() for path in cache.values())
    assert cache["ピカ？"].read_bytes() == "WAV:ピカ？".encode()
    assert client.synth_calls == ["ピカ？", "ふんふん"]


def test_second_run_reuses_cached_files(tmp_path):
    """2回目の起動では合成しない（起動を速くするのがキャッシュの目的）。"""
    client = FakeVoicevoxClient()
    build_wav_cache(client, ["ピカ？"], tmp_path, "persona1")
    client.synth_calls.clear()

    build_wav_cache(client, ["ピカ？"], tmp_path, "persona1")
    assert client.synth_calls == []


def test_persona_change_invalidates_cache(tmp_path):
    client = FakeVoicevoxClient()
    first = build_wav_cache(client, ["ピカ？"], tmp_path, "persona1")
    second = build_wav_cache(client, ["ピカ？"], tmp_path, "persona2")

    assert first["ピカ？"] != second["ピカ？"]
    assert client.synth_calls == ["ピカ？", "ピカ？"]


def test_voice_change_invalidates_cache(tmp_path):
    """声（話者・ピッチ）を変えたら作り直す。"""
    first = build_wav_cache(FakeVoicevoxClient("v1"), ["ピカ？"], tmp_path, "persona1")
    second = build_wav_cache(FakeVoicevoxClient("v2"), ["ピカ？"], tmp_path, "persona1")

    assert first["ピカ？"] != second["ピカ？"]


def test_synth_failure_is_skipped_not_fatal(tmp_path):
    """1件の合成に失敗しても、残りのキャッシュ作成は続ける。"""

    class BrokenOnce(FakeVoicevoxClient):
        def synth(self, text: str) -> bytes:
            if text == "こわれる":
                raise RuntimeError("synth failed")
            return super().synth(text)

    cache = build_wav_cache(BrokenOnce(), ["こわれる", "ピカ？"], tmp_path, "p")

    assert "こわれる" not in cache
    assert "ピカ？" in cache
