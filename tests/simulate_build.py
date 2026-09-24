import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import glob, os, re, shutil, subprocess, sys
ADDON = sys.argv[2] if len(sys.argv) > 2 else ADDON
TREE = sys.argv[1]
lines, buf = [], ""
for raw in open(f"{ADDON}/Dockerfile", encoding="utf-8"):
    raw = raw.rstrip("\n")
    if raw.strip().startswith("#") or not raw.strip():
        continue
    if raw.endswith("\\"):
        buf += raw[:-1] + " "; continue
    lines.append(buf + raw); buf = ""
tmpmap, results, other_runs = {}, [], []
started = False
for ln in lines:
    if "git clone" in ln: started = True; continue
    if not started: continue
    if ln.startswith("COPY "):
        _, src, dst = ln.split(None, 2)
        s = os.path.join(ADDON, src.rstrip("/.")) if src.endswith("/.") else os.path.join(ADDON, src)
        if dst.startswith("/tmp/"):
            tmpmap[dst] = s; continue
        if dst.startswith("/"):   # /opt/generate_config.py, /run.sh: irrelevant
            continue
        d = os.path.join(TREE, dst)
        if "*" in src:            # COPY local_commands/*.py ./modules/commands/
            os.makedirs(d, exist_ok=True)
            for f in sorted(glob.glob(os.path.join(ADDON, src))):
                shutil.copy(f, os.path.join(d, os.path.basename(f)))
            continue
        if src.endswith("/") and os.path.isdir(os.path.join(ADDON, src)):   # COPY folder/ dest/
            os.makedirs(d, exist_ok=True); subprocess.run(["cp", "-r", os.path.join(ADDON, src) + ".", d], check=True)
            continue
        if src.endswith("/."):
            os.makedirs(d, exist_ok=True); subprocess.run(["cp", "-r", s + "/.", d], check=True)
        else:
            os.makedirs(os.path.dirname(d), exist_ok=True); shutil.copy(s, d)
    elif ln.startswith("RUN "):
        m = re.search(r"python3 (/tmp/\S+\.py)", ln)
        if m:
            script = tmpmap.get(m.group(1))
            if script is None:   # a script inside a folder copied to /tmp (COPY local_patches/ /tmp/local_patches/)
                for tmp_dir, src_dir in tmpmap.items():
                    if tmp_dir.endswith("/") and m.group(1).startswith(tmp_dir):
                        script = os.path.join(src_dir, m.group(1)[len(tmp_dir):])
            scripts = [script]
            if os.path.basename(script) == "apply_all.py":   # one step for all patches: report each one, in ORDER
                order_file = os.path.join(os.path.dirname(script), "ORDER")
                scripts = [os.path.join(os.path.dirname(script), n.strip()) for n in open(order_file, encoding="utf-8")
                           if n.strip() and not n.strip().startswith("#")]
                listed = {os.path.basename(x) for x in scripts}
                for extra in sorted(glob.glob(os.path.join(os.path.dirname(script), "patch_*.py"))):
                    if os.path.basename(extra) not in listed:
                        results.append((os.path.basename(extra), 1, "staat niet in local_patches/ORDER"))
            for one in scripts:
                r = subprocess.run([sys.executable, one], cwd=TREE, capture_output=True, text=True)
                msg = (r.stdout + r.stderr).strip().splitlines()
                results.append((os.path.basename(one), r.returncode, msg[-1][:150] if r.returncode and msg else ""))
        else:
            other_runs.append(ln[:110])
for name, rc, msg in results:
    print(("OK   " if rc == 0 else "FAIL ") + name + ("" if rc == 0 else "\n       " + msg))
print(f"\n{sum(1 for r in results if r[1]==0)}/{len(results)} patches OK; overige RUN-stappen: {len(other_runs)}")
for o in other_runs: print("   ", o)
sys.exit(1 if any(rc for _, rc, _ in results) else 0)
