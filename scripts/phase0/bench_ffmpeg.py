"""Benchmark FFmpeg: render de cenas 1080p30 com zoompan, concat, mux, cortes."""
import os
import platform
import subprocess
import time

from common import OUT, save

SCENES = int(os.environ.get("SCENES", "75"))
SAMPLE = min(SCENES, int(os.environ.get("SAMPLE", str(SCENES))))
W = pathlib = None
work = OUT / "tmp_ffmpeg"
work.mkdir(parents=True, exist_ok=True)


def run(cmd):
    t0 = time.monotonic()
    p = subprocess.run(cmd, capture_output=True, text=True)
    return time.monotonic() - t0, p.returncode, p.stderr[-400:]


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()


res = {
    "scenes": SCENES, "nproc": os.cpu_count(), "python": platform.python_version(),
    "ffmpeg": sh("ffmpeg -version | head -1"), "mem": sh("free -m | sed -n 2p"),
}

# imagem sintetica 1920x1080 (gradiente + ruido) como "arte" da cena
img = work / "base.png"
run(["ffmpeg", "-y", "-f", "lavfi", "-i", "gradients=s=1920x1080:d=1,noise=alls=4:allf=t",
     "-frames:v", "1", str(img)])

scene_times, files = [], []
for i in range(SAMPLE):
    out = work / f"s{i:03d}.mp4"
    t, rc, err = run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(img), "-vf",
        "scale=3840:2160,zoompan=z='min(zoom+0.0006,1.12)':d=240:"
        "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,format=yuv420p",
        "-frames:v", "240", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-g", "30", "-keyint_min", "30", str(out)])
    if rc:
        res["scene_error"] = err
        break
    scene_times.append(t)
    files.append(out)

if scene_times:
    avg = sum(scene_times) / len(scene_times)
    res["scene_sec_avg"] = round(avg, 2)
    res["scene_sec_total_sample"] = round(sum(scene_times), 1)
    res["extrapolated_75_scenes_min"] = round(avg * 75 / 60, 1)

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{f.name}'\n" for f in files))
    t, rc, err = run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                      str(work / "video.mp4")])
    res["concat_sec"] = round(t, 1)
    dur = len(files) * 8
    t, rc, err = run(["ffmpeg", "-y", "-i", str(work / "video.mp4"), "-f", "lavfi", "-i",
                      f"sine=frequency=220:duration={dur}", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                      "-shortest", "-movflags", "+faststart", str(work / "final.mp4")])
    res["mux_sec"] = round(t, 1)
    res["final_mb"] = round((work / "final.mp4").stat().st_size / 1e6, 1) if (work / "final.mp4").exists() else None

    mid = max(0, dur // 2 - 5)
    t, rc, _ = run(["ffmpeg", "-y", "-ss", str(mid), "-i", str(work / "final.mp4"), "-t", "10",
                    "-c", "copy", str(work / "cut_fast.mp4")])
    res["cut_fast_sec"] = round(t, 2)
    t, rc, _ = run(["ffmpeg", "-y", "-ss", str(mid + 0.4), "-i", str(work / "final.mp4"), "-t", "10",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
                    str(work / "cut_precise.mp4")])
    res["cut_precise_sec"] = round(t, 2)
    if len(files) >= 2:
        t, rc, err = run(["ffmpeg", "-y", "-i", str(files[0]), "-i", str(files[1]), "-filter_complex",
                          "xfade=transition=fade:duration=1:offset=7", "-c:v", "libx264", "-preset",
                          "veryfast", "-crf", "23", str(work / "xfade.mp4")])
        res["xfade_pair_sec"] = round(t, 1)
        res["xfade_ok"] = rc == 0

# limpa temporarios (nada de midia vai para o branch de resultados)
for f in work.glob("*"):
    f.unlink()
work.rmdir()

md = "# Benchmark FFmpeg\n\n" + "\n".join(f"- **{k}**: {v}" for k, v in res.items()) + "\n"
save("ffmpeg", res, md)
print(md)
