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
def gh(*args, check=True):
    p = subprocess.run(['gh', *args], text=True, capture_output=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr)
    return p

def api(path):
    return json.loads(gh('api', path).stdout)

def pages(path, key=None):
    number = 1
    while True:
        join = '&' if '?' in path else '?'
        data = api(f'{path}{join}per_page=100&page={number}')
        rows = data[key] if key else data
        yield from rows
        if len(rows) < 100:
            break
        number += 1

def publish(repo, run, files, directory, dry_run=False):
    tag = 'translation-' + run['head_sha'][:12]
    sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if dry_run:
        print(json.dumps({'tag': tag, 'source': run['head_sha'], 'sha256': sums}))
        return
    directory = pathlib.Path(directory)
    matches = [r for r in pages(f'repos/{repo}/releases') if r['tag_name'] == tag]
    if matches:
        release = max(matches, key=lambda r: (len(r['assets']), -r['id']))
    else:
        archive_commit = api(f'repos/{repo}/git/ref/heads/main')['object']['sha']
        notes = (
            f'Сохранённая успешная сборка #{run["run_number"]}.\n\n'
            f'Исходный коммит сборки: {run["head_sha"]}.\nСнимок архивного тега: {archive_commit}.\n'
            f'Workflow: {run["name"]}.\nИсходный запуск: {run["html_url"]}.\n\n'
            'Файлы перенесены из артефактов этой сборки без пересборки. Тег указывает на снимок архива; '
            'исходники конкретной сборки доступны по исходному коммиту выше. '
            'Контрольные суммы находятся в SHA256SUMS.txt.\n'
        )
        if any(p.suffix == '.apk' for p in files):
            notes += 'APK является debug-сборкой; физическая установка здесь не проверялась. Постоянство сертификата обновлений зависит от настроек проекта.\n'
        payload = directory / 'release-request.json'
        payload.write_text(json.dumps({'tag_name': tag, 'target_commitish': archive_commit,
            'name': 'Prominence · русские квесты', 'body': notes,
            'draft': True, 'prerelease': any(p.suffix == '.apk' for p in files), 'make_latest': 'false'}))
        release = json.loads(gh('api', '--method', 'POST', f'repos/{repo}/releases', '--input', str(payload)).stdout)
    checksum = directory / 'SHA256SUMS.txt'
    checksum.write_text(''.join(f'{sums[p.name]}  {p.name}\n' for p in sorted(files)), encoding='utf-8')
    for p in [*files, checksum]:
        release = api(f'repos/{repo}/releases/{release["id"]}')
        assets = {a['name']: a for a in release['assets']}
        if p.name not in assets:
            uploaded = json.loads(gh('api', '--method', 'POST',
               f'https://uploads.github.com/repos/{repo}/releases/{release["id"]}/assets?name={p.name}',
               '-H', 'Content-Type: application/octet-stream', '--input', str(p)).stdout)
            assets[p.name] = uploaded
        downloaded = directory / 'verify' / p.name
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        with downloaded.open('wb') as stream:
            result = subprocess.run(['gh', 'api', f'repos/{repo}/releases/assets/{assets[p.name]["id"]}',
                '-H', 'Accept: application/octet-stream'], stdout=stream, stderr=subprocess.PIPE)
        if result.returncode or hashlib.sha256(downloaded.read_bytes()).digest() != hashlib.sha256(p.read_bytes()).digest():
            raise RuntimeError(f'Asset differs; refusing overwrite or publication: {tag}/{p.name}')
    if release['draft']:
        payload = directory / 'publish-request.json'
        payload.write_text(json.dumps({'draft': False, 'make_latest': 'false'}))
        gh('api', '--method', 'PATCH', f'repos/{repo}/releases/{release["id"]}', '--input', str(payload))
    print(f'Published and downloaded-byte verified: {tag}', flush=True)



repo = os.environ['GITHUB_REPOSITORY']
sha = os.environ['GITHUB_SHA']
with tempfile.TemporaryDirectory() as temp:
    publish(repo, {'run_number': 31, 'head_sha': sha, 'name': '31 главы FTB Quests: ZIP и SHA-256 сверены; Minecraft не запускался', 'html_url': f'https://github.com/{repo}/actions/runs/{os.environ["GITHUB_RUN_ID"]}'}, [archive], temp)
