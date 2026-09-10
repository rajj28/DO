"""Transcribe a WAV with the local faster-whisper model. Run by the D: venv python.

Standalone by necessity: faster-whisper lives in D:\do-models\stt-venv, not the
seed's interpreter, so the gate invokes this through that venv as a subprocess. Prints
one line of JSON: {"ok": bool, "text": str, "reason": str}.

    <venv-python> bin/stt_transcribe.py <wav> [model_dir]
"""
import json, os, sys

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "reason": "usage: stt_transcribe.py <wav> [model_dir]"})); return
    wav = sys.argv[1]
    model_dir = sys.argv[2] if len(sys.argv) > 2 else r"D:\do-models\faster-whisper-base"
    if not os.path.exists(wav):
        print(json.dumps({"ok": False, "reason": f"no wav at {wav}"})); return
    need = ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]
    missing = [f for f in need if not os.path.exists(os.path.join(model_dir, f))]
    if missing:
        print(json.dumps({"ok": False, "reason": f"model incomplete, missing {missing}",
                          "model_dir": model_dir})); return
    try:
        from faster_whisper import WhisperModel
        m = WhisperModel(model_dir, device="cpu", compute_type="int8")
        segments, info = m.transcribe(wav, beam_size=1, vad_filter=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        print(json.dumps({"ok": True, "text": text,
                          "language": info.language,
                          "duration": round(info.duration, 1)}))
    except Exception as e:
        print(json.dumps({"ok": False, "reason": f"{type(e).__name__}: {e}"}))

if __name__ == "__main__":
    main()
