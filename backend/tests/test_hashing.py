from app.pipeline.hashing import artifacts_to_rebuild, input_hash, needs_rebuild

BASE = {
    "image_prompt": "porto antigo ao amanhecer",
    "visual_style": "documental",
    "seed": 7,
    "narration_text": "Havia uma cidade.",
    "voice_id": "v1",
    "speed": 1.0,
    "camera_move": "zoom_in",
    "transition": "fade",
}


def test_hash_is_stable_and_order_independent():
    a = input_hash({"x": 1, "y": [1, 2]})
    b = input_hash({"y": [1, 2], "x": 1})
    assert a == b


def test_hash_changes_with_input():
    assert input_hash({"x": 1}) != input_hash({"x": 2})


def test_needs_rebuild():
    h = input_hash(BASE)
    assert not needs_rebuild(h, BASE)
    assert needs_rebuild(h, {**BASE, "seed": 8})
    assert needs_rebuild(None, BASE)


def test_unchanged_scene_rebuilds_nothing():
    assert artifacts_to_rebuild(BASE, dict(BASE)) == set()


def test_changing_narration_rebuilds_audio_subtitles_and_clip_not_image():
    new = {**BASE, "narration_text": "Havia uma cidade perdida."}
    assert artifacts_to_rebuild(BASE, new) == {"audio", "subtitles", "clip"}


def test_changing_image_prompt_rebuilds_image_and_clip_only():
    new = {**BASE, "image_prompt": "porto antigo a noite"}
    assert artifacts_to_rebuild(BASE, new) == {"image", "clip"}


def test_changing_camera_move_rebuilds_only_clip():
    assert artifacts_to_rebuild(BASE, {**BASE, "camera_move": "pan_left"}) == {"clip"}


def test_changing_voice_rebuilds_audio_subtitles_clip():
    assert artifacts_to_rebuild(BASE, {**BASE, "voice_id": "v2"}) == {"audio", "subtitles", "clip"}
