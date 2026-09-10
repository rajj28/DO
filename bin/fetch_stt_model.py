"""Chunked, resumable fetch of the faster-whisper base model to D:.

This network resets connections to huggingface mid-stream: small files slip through
in lucky windows, the 145 MB model.bin does not. So this fetches in SMALL byte-range
chunks - each request is short enough to finish before a reset - and every chunk that
lands is kept. Re-run as many times as needed; it resumes at the byte it stopped on.

    python bin/fetch_stt_model.py
"""
import os, sys, time, urllib.request, urllib.error

DEST = r"D:\do-models\faster-whisper-base"
BASES = ["https://huggingface.co/Systran/faster-whisper-base/resolve/main/",
         "https://hf-mirror.com/Systran/faster-whisper-base/resolve/main/"]
FILES = ["config.json", "tokenizer.json", "vocabulary.txt",
         "preprocessor_config.json", "model.bin"]
CHUNK = 1 << 20        # 1 MiB per request - short enough to beat most resets
UA = {"User-Agent": "Mozilla/5.0"}


def size_remote(fname):
    for base in BASES:
        try:
            req = urllib.request.Request(base + fname, headers={**UA, "Range": "bytes=0-0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                cr = r.headers.get("Content-Range", "")
                if "/" in cr:
                    return int(cr.split("/")[-1]), base
        except Exception:
            continue
    return None, BASES[0]


def fetch(fname):
    out = os.path.join(DEST, fname)
    total, base = size_remote(fname)
    if total is None:
        print(f"  {fname}: cannot reach server to size it; skip for now")
        return False
    have = os.path.getsize(out) if os.path.exists(out) else 0
    if have >= total:
        print(f"  {fname}: complete ({have} bytes)")
        return True
    print(f"  {fname}: {have}/{total} bytes, fetching in 1 MiB chunks ...")
    stall = 0
    while have < total:
        end = min(have + CHUNK - 1, total - 1)
        try:
            req = urllib.request.Request(base + fname,
                headers={**UA, "Range": f"bytes={have}-{end}"})
            with urllib.request.urlopen(req, timeout=45) as r:
                data = r.read()
            with open(out, "ab") as w:
                w.write(data)
            have += len(data)
            stall = 0
            if have % (16 << 20) < CHUNK:      # progress every ~16 MiB
                print(f"    {fname}: {have/1e6:.0f}/{total/1e6:.0f} MB")
        except Exception as e:
            stall += 1
            if stall % 20 == 0:
                print(f"    {fname}: stalled at {have/1e6:.1f} MB "
                      f"({type(e).__name__}); still trying")
            time.sleep(min(5, 0.3 * stall))
            if stall > 400:
                print(f"    {fname}: giving up this run at {have}/{total}; re-run to resume")
                return False
    print(f"  {fname}: complete ({have} bytes)")
    return True


def main():
    os.makedirs(DEST, exist_ok=True)
    ok = all(fetch(f) for f in FILES)
    print("\nMODEL READY at " + DEST if ok else
          "\nINCOMPLETE - re-run; it resumes at the byte it stopped on.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
