"""Resumable, retry-heavy fetch of the faster-whisper base model to D:.

Built because this network resets connections to huggingface CDNs intermittently.
Range-resume means each partial success is kept, so repeated runs creep the file in
even over a flaky link. Re-run any time:  python bin/fetch_stt_model.py
"""
import os, sys, time, urllib.request

DEST = r"D:\do-models\faster-whisper-base"
BASES = ["https://huggingface.co/Systran/faster-whisper-base/resolve/main/",
         "https://hf-mirror.com/Systran/faster-whisper-base/resolve/main/"]
FILES = ["config.json", "tokenizer.json", "vocabulary.txt",
         "preprocessor_config.json", "model.bin"]


def fetch(fname, tries=40):
    out = os.path.join(DEST, fname)
    for attempt in range(1, tries + 1):
        have = os.path.getsize(out) if os.path.exists(out) else 0
        base = BASES[attempt % len(BASES)]
        try:
            req = urllib.request.Request(base + fname,
                headers={"User-Agent": "Mozilla/5.0", "Range": f"bytes={have}-"})
            with urllib.request.urlopen(req, timeout=60) as r:
                mode = "ab" if r.status == 206 else "wb"
                if r.status != 206:
                    have = 0
                with open(out, mode) as w:
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        w.write(chunk)
            print(f"  {fname}: {os.path.getsize(out)} bytes  (done)")
            return True
        except Exception as e:
            got = os.path.getsize(out) if os.path.exists(out) else 0
            print(f"  {fname}: attempt {attempt}/{tries}, have {got} bytes, "
                  f"{type(e).__name__}")
            time.sleep(min(10, 1 + attempt * 0.5))
    return False


def main():
    os.makedirs(DEST, exist_ok=True)
    ok = all(fetch(f) for f in FILES)
    print("\nMODEL READY at " + DEST if ok else
          "\nINCOMPLETE - re-run this script; it resumes where it stopped.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
