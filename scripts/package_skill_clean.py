"""Build a reproducible Skill ZIP, verify contents and test the extracted package."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ALLOWED={"scripts","references","config","tests","evals"}


def package(destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError("output exists; choose a new archive name")
    files=[]
    for path in sorted(ROOT.rglob("*")):
        relative=path.relative_to(ROOT)
        if path.is_symlink():
            raise ValueError(f"symlink is not allowed in a portable Skill: {relative}")
        if not path.is_file() or "__pycache__" in relative.parts or path.suffix in {".pyc",".pyo"}:
            continue
        if relative.as_posix() in {"SKILL.md","VERSION.json"} or relative.parts[0] in ALLOWED:
            if relative.as_posix()=="config/targets.json":
                continue
            files.append(path)
    paths={str(p.relative_to(ROOT)) for p in files}
    if "SKILL.md" not in paths or not any(p.startswith("tests/test_") for p in paths):
        raise ValueError("Skill entrypoint or packaged regression tests missing")
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="skill-package-") as temp:
        archive=Path(temp)/"skill.zip"
        with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as out:
            for path in files:
                info=zipfile.ZipInfo("model-release-analysis/"+path.relative_to(ROOT).as_posix(),date_time=(2026,9,11,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o100644<<16
                out.writestr(info,path.read_bytes())
            info=zipfile.ZipInfo("model-release-analysis/PACKAGE-MANIFEST.json",date_time=(2026,9,11,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            out.writestr(info,json.dumps(manifest,sort_keys=True,indent=2))
        with zipfile.ZipFile(archive) as inp:
            if inp.testzip():
                raise ValueError("archive CRC validation failed")
            inp.extractall(Path(temp)/"unpacked")
        unpacked=Path(temp)/"unpacked/model-release-analysis"
        for relative,expected in manifest.items():
            if hashlib.sha256((unpacked/relative).read_bytes()).hexdigest()!=expected:
                raise ValueError("extracted file hash mismatch")
        environment={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"}
        result=subprocess.run([sys.executable,"scripts/run_local_validation.py"],cwd=unpacked,env=environment,
                              capture_output=True,text=True,timeout=180)
        if result.returncode:
            raise RuntimeError("extracted-package self-test failed:\n"+result.stdout[-5000:]+result.stderr[-5000:])
        destination.write_bytes(archive.read_bytes())
    return {"status":"pass","archive":str(destination),"files":len(files),
            "sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),"extracted_package_self_test":"pass"}


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try: result=package(args.output)
    except Exception as exc:
        print(json.dumps({"status":"fail","error":str(exc)}));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=="__main__": sys.exit(main())
