"""Montagem do video: um clipe por cena (zoom/pan + narracao + legenda) e concatenacao sem recodificar."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

FPS = 30
PAD_S = 0.3  # respiro depois de cada narracao


def ass_time(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def split_phrases(text: str, max_words: int = 7) -> list[str]:
    """Quebra a narracao em legendas curtas, preferindo pontuacao."""
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        words = sentence.split()
        if not words:
            continue
        n = -(-len(words) // max_words)  # divide em partes iguais
        size = -(-len(words) // n)
        out += [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
    return out


def build_ass(text: str, duration: float) -> str:
    """Legendas cronometradas por proporcao de caracteres sobre a duracao REAL do audio."""
    phrases = split_phrases(text)
    total = sum(len(p) for p in phrases) or 1
    lines, t = [], 0.0
    for p in phrases:
        d = duration * len(p) / total
        safe = p.replace("{", "(").replace("}", ")").replace("\\", "")
        lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(t + d)},Default,,0,0,0,,{safe}")
        t += d
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
            "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            "Style: Default,DejaVu Sans,56,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,120,120,90,1\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n" + "\n".join(lines) + "\n")


def zoompan(camera: str, frames: int) -> str:
    n = max(frames, 1)
    c = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if camera == "slow_zoom_out":
        z = f"z='if(eq(on,0),1.15,max(zoom-0.15/{n},1.0))':{c}"
    elif camera == "pan_left":
        z = f"z=1.12:x='(iw-iw/zoom)*(1-on/{n})':y='ih/2-(ih/zoom/2)'"
    elif camera == "pan_right":
        z = f"z=1.12:x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'"
    elif camera == "static":
        z = f"z=1:{c}"
    else:  # slow_zoom_in
        z = f"z='min(zoom+0.15/{n},1.15)':{c}"
    return f"{z}:d={n}:s=1920x1080:fps={FPS}"


def clip_filter(camera: str, transition: str, duration: float, ass_path: str) -> str:
    frames = round(duration * FPS)
    chain = [f"crop=iw:trunc(iw*9/16/2)*2", "scale=2880:-2", f"zoompan={zoompan(camera, frames)}", "format=yuv420p"]
    if transition == "fade":
        chain += ["fade=t=in:st=0:d=0.3", f"fade=t=out:st={max(duration - 0.3, 0):.2f}:d=0.3"]
    chain.append(f"subtitles={ass_path}")
    return ",".join(chain)


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True, cwd=cwd)
    if p.returncode:
        raise RuntimeError(f"ffmpeg falhou: {p.stderr[-400:]}")


def render_clip(image: Path, audio: Path, scene: dict, audio_dur: float, out: Path) -> float:
    dur = round(audio_dur + PAD_S, 2)
    ass = out.with_suffix(".ass")
    ass.write_text(build_ass(scene["narration_text"], audio_dur))
    run_ffmpeg(["-loop", "1", "-framerate", str(FPS), "-i", str(image), "-i", str(audio),
                "-vf", clip_filter(scene.get("camera_move") or "slow_zoom_in", scene.get("transition") or "fade", dur, ass.name),
                "-af", "apad", "-t", str(dur), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", str(FPS),
                "-keyint_min", str(FPS), "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
                "-movflags", "+faststart", str(out)], cwd=out.parent)  # cwd: o filtro subtitles usa caminho relativo
    return dur


def concat(clips: list[Path], out: Path) -> None:
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{c.name}'\n" for c in clips))
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", lst.name, "-c", "copy", "-movflags", "+faststart", str(out)], cwd=out.parent)


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None
