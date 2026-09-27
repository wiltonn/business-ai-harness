"""Generate the SYNTHETIC interview fixture with exact ground truth.

Audio: Windows SAPI TTS, one WAV per sentence (two voices), laid out with pauses.
Video: 1920x1080@30 testsrc2 with a burned-in 17-block frame barcode
(block 0 = marker, blocks 1..16 = source frame number bits), speaker label and
timecode. The barcode lets verification recover, for every output frame, exactly
which source frame it came from — so cut accuracy is measured, not eyeballed.

Outputs (media git-ignored):
  fixtures/media/synth-interview-001.mp4
  fixtures/synth-interview-001.transcript.json   (ground-truth sentence timings)
  fixtures/synth-interview-001.manifest.json     (hashes, probe facts)
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from harness.tools import FFMPEG, ffprobe_json  # noqa: E402

FIX = Path(__file__).resolve().parents[1] / "experiments" / "video-editing" / "fixtures"
SCRIPT = FIX / "synthetic_interview_script.json"
MEDIA = FIX / "media"
TTS_DIR = MEDIA / "tts"
FIXTURE_ID = "synth-interview-001"

SAMPLE_RATE = 48000
FPS = 30
W, H = 1920, 1080
LEAD_IN_S = 1.0
PAUSE_SENTENCE_S = 0.6
PAUSE_TURN_S = 1.4
TAIL_S = 1.5

# Barcode geometry — shared with harness.verify.
from harness.verify import BARCODE  # noqa: E402

PS_TTS = r"""
param([string]$JobFile)
Add-Type -AssemblyName System.Speech
$jobs = Get-Content -Raw -Encoding UTF8 $JobFile | ConvertFrom-Json
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
foreach ($j in $jobs) {
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $s.SelectVoice($j.voice)
  $s.Rate = 0
  $s.SetOutputToWaveFile($j.out, $fmt)
  $s.Speak($j.text)
  $s.Dispose()
}
"""


def synthesize(script: dict) -> list[dict]:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    jobs, sentences = [], []
    for turn in script["turns"]:
        voice = script["speakers"][turn["speaker"]]["voice"]
        for i, text in enumerate(turn["sentences"], start=1):
            sid = f"{turn['id']}_s{i}"
            out = TTS_DIR / f"{sid}.wav"
            sentences.append({"sentence_id": sid, "turn_id": turn["id"],
                              "speaker": turn["speaker"], "text": text, "wav": out})
            if not out.exists():
                jobs.append({"voice": voice, "text": text, "out": str(out)})
    if jobs:
        job_file = TTS_DIR / "jobs.json"
        job_file.write_text(json.dumps(jobs), encoding="utf-8")
        ps_file = TTS_DIR / "tts.ps1"
        ps_file.write_text(PS_TTS, encoding="utf-8")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(ps_file), "-JobFile", str(job_file)], check=True)
    return sentences


def assemble_audio(sentences: list[dict], out_wav: Path) -> float:
    frames = bytearray()
    silence = lambda s: b"\x00\x00" * int(round(s * SAMPLE_RATE))  # noqa: E731
    frames += silence(LEAD_IN_S)
    prev_turn = None
    for s in sentences:
        if prev_turn is not None:
            frames += silence(PAUSE_TURN_S if s["turn_id"] != prev_turn else PAUSE_SENTENCE_S)
        with wave.open(str(s["wav"]), "rb") as w:
            assert w.getframerate() == SAMPLE_RATE and w.getsampwidth() == 2 and w.getnchannels() == 1
            data = w.readframes(w.getnframes())
        start = len(frames) // 2 / SAMPLE_RATE
        frames += data
        s["start"] = round(start, 4)
        s["end"] = round(len(frames) // 2 / SAMPLE_RATE, 4)
        prev_turn = s["turn_id"]
    frames += silence(TAIL_S)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))
    return len(frames) // 2 / SAMPLE_RATE


def build_filter(script: dict, sentences: list[dict], duration: float) -> str:
    font = "fontfile='C\\:/Windows/Fonts/arial.ttf'"
    b = BARCODE
    parts = [f"[0:v]drawbox=x={b['x'] - 16}:y={b['y'] - 12}:w={b['cells'] * b['stride'] + 24}:"
             f"h={b['size'] + 24}:color=black:t=fill"]
    # marker block (always on) + 16 frame-number bits
    parts.append(f"drawbox=x={b['x']}:y={b['y']}:w={b['size']}:h={b['size']}:color=white:t=fill")
    for bit in range(16):
        x = b["x"] + (bit + 1) * b["stride"]
        parts.append(f"drawbox=x={x}:y={b['y']}:w={b['size']}:h={b['size']}:color=white:t=fill:"
                     f"enable='eq(mod(floor(n/{2 ** bit}),2),1)'")
    parts.append(f"drawbox=x=0:y={H - 150}:w={W}:h=150:color=black@0.55:t=fill")
    parts.append(f"drawtext={font}:text='SYNTHETIC FIXTURE {FIXTURE_ID}':x=40:y={H - 130}:"
                 f"fontsize=34:fontcolor=white@0.8")
    parts.append(f"drawtext={font}:text='src %{{pts\\:hms}}  frame %{{n}}':x=40:y={H - 80}:"
                 f"fontsize=40:fontcolor=yellow")
    # speaker label per turn
    turns: dict[str, list[dict]] = {}
    for s in sentences:
        turns.setdefault(s["turn_id"], []).append(s)
    for tid, ss in turns.items():
        spk = script["speakers"][ss[0]["speaker"]]["name"].replace("'", "")
        parts.append(f"drawtext={font}:text='{spk} ({tid})':x=w-tw-40:y={H - 105}:fontsize=44:"
                     f"fontcolor=white:enable='between(t,{ss[0]['start']:.3f},{ss[-1]['end']:.3f})'")
    return ",".join(parts) + "[v]"


def main() -> None:
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    MEDIA.mkdir(parents=True, exist_ok=True)
    sentences = synthesize(script)
    wav = MEDIA / f"{FIXTURE_ID}.wav"
    duration = assemble_audio(sentences, wav)
    filt = MEDIA / "fixture.filter.txt"
    filt.write_text(build_filter(script, sentences, duration), encoding="utf-8")
    out = MEDIA / f"{FIXTURE_ID}.mp4"
    subprocess.run([
        str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc2=size={W}x{H}:rate={FPS}:duration={duration:.3f}",
        "-i", str(wav),
        "-filter_complex_script", str(filt), "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-g", "60", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-shortest", str(out),
    ], check=True)

    transcript = {
        "fixture_id": FIXTURE_ID,
        "ground_truth": True,
        "speakers": script["speakers"],
        "sentences": [{k: v for k, v in s.items() if k != "wav"} for s in sentences],
    }
    (FIX / f"{FIXTURE_ID}.transcript.json").write_text(json.dumps(transcript, indent=2), encoding="utf-8")

    probe = ffprobe_json(out)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    manifest = {
        "fixture_id": FIXTURE_ID,
        "synthetic": True,
        "rights": "Generated locally; no third-party rights.",
        "path": f"media/{FIXTURE_ID}.mp4",
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "duration_sec": float(probe["format"]["duration"]),
        "video": {"codec": v["codec_name"], "width": v["width"], "height": v["height"],
                  "fps": v["r_frame_rate"], "gop": 60},
        "barcode": BARCODE,
        "generator": "scripts/make_synthetic_fixture.py",
    }
    (FIX / f"{FIXTURE_ID}.manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "duration": duration, "sentences": len(sentences)}))


if __name__ == "__main__":
    main()
