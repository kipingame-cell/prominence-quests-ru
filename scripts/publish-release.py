#!/usr/bin/env python3
"""Verify the committed translation archive before immutable publication."""
import hashlib, json, os, pathlib, subprocess, tempfile, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
report=json.loads((root/'validation-report.json').read_text())
archive=root/'downloads/Prominence-quests-ru.zip'
with zipfile.ZipFile(archive) as zipped:
    assert zipped.testzip() is None
    for row in report['chapters']:
        source=root/'chapters'/row['file']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==row['sha256']
        matches=[n for n in zipped.namelist() if n.endswith('/'+row['file']) or n==row['file']]
        assert len(matches)==1, f'Chapter is missing or duplicated: {row["file"]}'
        assert zipped.read(matches[0])==source.read_bytes(), f'Archive differs: {row["file"]}'
repo=os.environ['GITHUB_REPOSITORY'];sha=os.environ['GITHUB_SHA'];tag='translation-'+sha[:12]
def gh(*args,check=True):
    return subprocess.run(['gh',*args],capture_output=True,text=True,check=check)
with tempfile.TemporaryDirectory() as temp:
    directory=pathlib.Path(temp);checksum=directory/(archive.name+'.sha256')
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
    notes=directory/'notes.md';notes.write_text(f'Русский перевод 31 главы FTB Quests. Исходный коммит: {sha}.\n\nАрхив побайтово сверен с chapters/ и validation-report.json. Minecraft не запускался; номер сборки Prominence пока не установлен. Инструкция установки — в README.\n')
    probe=gh('api',f'repos/{repo}/releases/tags/{tag}',check=False)
    if probe.returncode:
        if '404' not in probe.stderr:raise RuntimeError(probe.stderr)
        gh('release','create',tag,'--repo',repo,'--target',sha,'--title','Prominence · русские квесты',
           '--notes-file',str(notes),'--draft','--latest=false')
        release=json.loads(gh('api',f'repos/{repo}/releases/tags/{tag}').stdout)
    else:release=json.loads(probe.stdout)
    assets={a['name'] for a in release['assets']}
    for file in [archive,checksum]:
        if file.name not in assets:gh('release','upload',tag,str(file),'--repo',repo)
    verify=directory/'verify';verify.mkdir()
    gh('release','download',tag,'--repo',repo,'--dir',str(verify))
    for file in [archive,checksum]:
        assert (verify/file.name).read_bytes()==file.read_bytes(), 'Existing/uploaded asset differs; no overwrite performed'
    if release['draft']:gh('release','edit',tag,'--repo',repo,'--draft=false','--latest')
    print(f'Published and download verified: {tag}')
