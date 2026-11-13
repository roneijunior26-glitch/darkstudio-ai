from datetime import datetime, timezone

import pytest

from app.workers import tts
from app.workers.errors import PermanentError, WaitQuota
from app.workers.handlers import generate_audio as ga

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)
WAV = tts.pcm_to_wav(b"\x00\x00" * 24000, 24000)  # 1 s


class Db:
    def __init__(self, voice=None, project=None, used=0, scene=None):
        self.voice = voice if voice is not None else {"engine": "gemini", "model_ref": "m:Kore", "speed": 1, "style_prompt": "grave"}
        self.project = project or {"voice_id": "v1", "channel_id": "c1"}
        self.scene = scene or {"id": "s1", "project_id": "p1", "user_id": "u1", "narration_text": "Ola mundo", "audio_asset_id": None}
        self.used, self.uploads, self.updates = used, [], []

    def select(self, table, q=""):
        return {"scenes": [self.scene], "projects": [self.project], "voice_profiles": [self.voice] if self.voice else [],
                "channels": [{"default_voice_id": None, "niche_preset_id": None}]}[table]

    def count(self, table, q=""):
        return self.used

    def upload(self, *a):
        self.uploads.append(a)

    def insert(self, table, rows):
        return [{"id": "a1"}]

    def update(self, table, q, v):
        self.updates.append((table, v))


def test_generates_audio_and_measures_duration():
    db = Db()
    res = ga.run({"payload": {"scene_id": "s1"}}, db, lambda text, voice: WAV, now=NOW)
    assert res["duration_s"] == 1.0
    assert db.uploads[0][1] == "u1/p1/audio/s1.wav"
    assert ("scenes", {"audio_asset_id": "a1", "duration_s": 1.0}) in db.updates


def test_skips_existing_audio():
    db = Db(scene={"id": "s1", "project_id": "p", "user_id": "u", "narration_text": "x", "audio_asset_id": "a0"})
    assert ga.run({"payload": {"scene_id": "s1"}}, db, lambda *a: 1 / 0, now=NOW) == {"skipped": "narracao ja existe"}


def test_gemini_quota_guard_waits():
    with pytest.raises(WaitQuota):
        ga.run({"payload": {"scene_id": "s1"}}, Db(used=100), lambda *a: WAV, now=NOW)


def test_kokoro_ignores_daily_limit():
    db = Db(voice={"engine": "kokoro", "model_ref": "pm_santa", "speed": 0.95}, used=9999)
    assert ga.run({"payload": {"scene_id": "s1"}}, db, lambda *a: WAV, now=NOW)["duration_s"] == 1.0


def test_project_without_voice_is_permanent():
    db = Db(project={"voice_id": None, "channel_id": "c1"})
    with pytest.raises(PermanentError, match="sem voz"):
        ga.run({"payload": {"scene_id": "s1"}}, db, lambda *a: WAV, now=NOW)


def test_unsupported_engine():
    with pytest.raises(PermanentError, match="nao suportado"):
        tts.synthesize("x", {"engine": "edge", "model_ref": "x"})


def test_quota_wait_daily_vs_minute():
    assert tts.quota_wait("quotaId: GenerateRequestsPerDayPerProjectPerModel", NOW) == datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
    assert tts.quota_wait("PerMinute", NOW).minute == 1 and tts.quota_wait("x", NOW).second == 30
    late = datetime(2026, 11, 13, 9, tzinfo=timezone.utc)
    assert tts.quota_wait("PerDay", late) == datetime(2026, 11, 14, 8, tzinfo=timezone.utc)
