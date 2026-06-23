"""MiniMax TTS UI helpers."""

import streamlit as st

from web.i18n import tr

MINIMAX_MODELS = [
    "speech-2.8-turbo",
    "speech-2.8-hd",
    "speech-2.6-turbo",
    "speech-2.6-hd",
    "speech-02-turbo",
    "speech-02-hd",
]

MINIMAX_VOICES = [
    ("male-qn-qingse", "male-qn-qingse"),
    ("male-qn-jingying", "male-qn-jingying"),
    ("male-qn-daxuesheng", "male-qn-daxuesheng"),
    ("female-shaonv", "female-shaonv"),
    ("female-yujie", "female-yujie"),
    ("female-chengshu", "female-chengshu"),
    ("female-tianmei", "female-tianmei"),
    ("Chinese (Mandarin)_News_Anchor", "Chinese (Mandarin)_News_Anchor"),
    ("Chinese (Mandarin)_Warm_Girl", "Chinese (Mandarin)_Warm_Girl"),
    ("Chinese (Mandarin)_Gentleman", "Chinese (Mandarin)_Gentleman"),
]

MINIMAX_EMOTIONS = [
    "",
    "happy",
    "sad",
    "angry",
    "fearful",
    "disgusted",
    "surprised",
    "calm",
    "fluent",
    "whisper",
]


def render_minimax_tts_controls(tts_config: dict, key_prefix: str) -> dict:
    """Render MiniMax TTS controls and return selected params."""
    minimax_config = tts_config.get("minimax", {})
    saved_model = minimax_config.get("model", "speech-2.8-turbo")
    saved_voice = minimax_config.get("voice_id", "male-qn-qingse")
    saved_speed = minimax_config.get("speed", 1.0)
    saved_emotion = minimax_config.get("emotion") or ""

    model_index = MINIMAX_MODELS.index(saved_model) if saved_model in MINIMAX_MODELS else 0
    voice_ids = [voice_id for voice_id, _ in MINIMAX_VOICES]
    voice_options = [label for _, label in MINIMAX_VOICES]
    voice_index = voice_ids.index(saved_voice) if saved_voice in voice_ids else 0
    emotion_index = MINIMAX_EMOTIONS.index(saved_emotion) if saved_emotion in MINIMAX_EMOTIONS else 0

    model_col, voice_col = st.columns([1, 1])
    with model_col:
        minimax_model = st.selectbox(
            tr("tts.minimax_model"),
            MINIMAX_MODELS,
            index=model_index,
            key=f"{key_prefix}_minimax_model",
        )
    with voice_col:
        selected_voice_display = st.selectbox(
            tr("tts.minimax_voice"),
            voice_options,
            index=voice_index,
            key=f"{key_prefix}_minimax_voice_select",
        )
        selected_voice = voice_ids[voice_options.index(selected_voice_display)]

    custom_voice = st.text_input(
        tr("tts.minimax_custom_voice"),
        value="" if saved_voice in voice_ids else saved_voice,
        placeholder="voice_id",
        help=tr("tts.minimax_custom_voice_help"),
        key=f"{key_prefix}_minimax_custom_voice",
    ).strip()
    if custom_voice:
        selected_voice = custom_voice

    speed_col, emotion_col = st.columns([1, 1])
    with speed_col:
        minimax_speed = st.slider(
            tr("tts.speed"),
            min_value=0.5,
            max_value=2.0,
            value=float(saved_speed),
            step=0.1,
            format="%.1fx",
            key=f"{key_prefix}_minimax_speed",
        )
        st.caption(tr("tts.speed_label", speed=f"{minimax_speed:.1f}"))
    with emotion_col:
        minimax_emotion = st.selectbox(
            tr("tts.minimax_emotion"),
            MINIMAX_EMOTIONS,
            index=emotion_index,
            format_func=lambda value: tr("tts.minimax_emotion_auto") if value == "" else value,
            key=f"{key_prefix}_minimax_emotion",
        )

    return {
        "voice": selected_voice,
        "speed": minimax_speed,
        "model": minimax_model,
        "emotion": minimax_emotion or None,
    }
