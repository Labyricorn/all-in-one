"""Loopback API and live MCP share the same durable core and detached workers."""
import argparse
import asyncio
import contextlib
import json
import logging
import os
import secrets
import socket
import subprocess
import urllib.request
import webbrowser
import uuid
from urllib.parse import unquote
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.routing import Route, Mount
from starlette.concurrency import run_in_threadpool

from common import ROOT, write_json, probe_media
from core.projects import Conflict
from server import mcp, project_store, submit_song, get_job, list_jobs, open_project, cancel_job

API_VERSION = 1


def show_review(record, open_browser=False):
    """Print a direct UI link and optionally connect the browser via a fragment."""
    url = record['url'] + '/app'
    print('Review UI:', url, flush=True)
    if open_browser:
        # Fragments stay in the browser; they are not sent in HTTP requests/logs.
        webbrowser.open(url + '#token=' + record['token'])


@contextlib.contextmanager
def discovery_lease(path):
    """OS-owned lease avoids duplicate startup; released automatically on crash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a+b') as stream:
        if stream.tell() == 0: stream.write(b'0'); stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Another service is starting for this discovery file; retry after it becomes healthy.') from error
        try: yield
        finally:
            stream.seek(0)
            if os.name == 'nt': msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def create_app(token):
    store = project_store()

    async def health(request):
        return JSONResponse({'name': 'mgmv-local', 'api_version': API_VERSION})

    async def upload_media(request):
        """Retain browser-selected media outside source for detached workers."""
        directory = ROOT / 'song-inputs' / uuid.uuid4().hex
        path = None
        accepted = False
        try:
            name = unquote(request.headers.get('x-filename', 'audio.wav'))
            name = name.replace('\\', '/').rsplit('/', 1)[-1]
            name = ''.join(c if c.isalnum() or c in ' ._-' else '_' for c in name)[-160:]
            if not name or not Path(name).suffix:
                raise ValueError('Choose an audio or video file with a file extension.')
            directory.mkdir(parents=True)
            path = directory / ('input-' + name)
            size = 0
            with path.open('wb') as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > 2 * 1024 ** 3:
                        raise ValueError('Media files must be smaller than 2 GB.')
                    await run_in_threadpool(output.write, chunk)
            if not size:
                raise ValueError('The selected file is empty.')
            source, probe = await run_in_threadpool(probe_media, str(path))
            accepted = True
            return JSONResponse({'path': str(source), 'name': name, 'size_bytes': size,
                                 'duration_seconds': float(probe['container_duration_seconds']) if probe.get('container_duration_seconds') else None}, status_code=201)
        except (ValueError, OSError, KeyError, subprocess.TimeoutExpired) as error:
            return JSONResponse({'error': str(error)}, status_code=400)
        finally:
            if not accepted:
                if path and path.exists():
                    path.unlink()
                if directory.exists():
                    directory.rmdir()

    async def dispatch(request):
        try:
            body = await request.json() if request.method == 'POST' else {}
            if request.url.path == '/api/v1/projects':
                if request.method == 'GET':
                    value = {'projects': await run_in_threadpool(store.list)}
                elif 'analysis_data' in body:
                    if set(body) != {'analysis_data'}:
                        raise ValueError('Supply analysis_data alone, or analysis_path/job_id.')
                    imported = await run_in_threadpool(store.import_data, body['analysis_data'])
                    value = {k: v for k, v in imported.items() if k != 'analysis'}
                else:
                    value = await run_in_threadpool(open_project, **body)
            elif request.url.path == '/api/v1/jobs':
                value = await run_in_threadpool(submit_song, **body) if request.method == 'POST' else await run_in_threadpool(list_jobs)
            elif 'job_id' in request.path_params:
                value = await run_in_threadpool(cancel_job if request.method == 'POST' else get_job, request.path_params['job_id'])
            else:
                project = request.path_params['project_id']
                action = request.path_params.get('action', 'read')
                if action == 'read': value = await run_in_threadpool(store.read, project)
                elif action == 'corrections': value = await run_in_threadpool(store.apply, project, body, 'gui')
                elif action == 'proposals':
                    value = await run_in_threadpool(store.propose, project, body) if request.method == 'POST' else {'items': await run_in_threadpool(store.proposals, project)}
                elif action == 'restore': value = await run_in_threadpool(store.apply, project, body['correction'], 'gui', body['target_revision'])
                elif action == 'history': value = {'items': await run_in_threadpool(store.history, project)}
                elif action == 'export':
                    value = (await run_in_threadpool(store.read, project, body.get('revision')))['analysis']
                else: raise ValueError('Unknown API action.')
            return JSONResponse(value)
        except Conflict as error:
            return JSONResponse({'error': str(error), 'expected_revision': error.expected, 'current_revision': error.actual}, status_code=409)
        except Exception as error:
            logging.getLogger('mgmv').warning('API operation failed: %s', error)
            return JSONResponse({'error': str(error)}, status_code=400)

    async def artifact(request):
        try:
            path = await run_in_threadpool(store.artifact, request.path_params['project_id'], request.path_params['role'])
            return FileResponse(path, media_type='audio/wav')
        except (ValueError, OSError) as error:
            return JSONResponse({'error': str(error)}, status_code=404)

    async def debug(request):
        name = 'src/playback.mjs' if request.url.path.endswith('.mjs') else 'debug.html'
        return FileResponse(Path(__file__).resolve().parents[1] / 'desktop' / name,
                            media_type='text/javascript' if name.endswith('.mjs') else 'text/html')

    async def editor(request):
        name = request.url.path.rsplit('/', 1)[-1]
        files = {'app': ('app.html', 'text/html'), 'app.js': ('src/app.js', 'text/javascript'),
                 'app.css': ('src/app.css', 'text/css'), 'playback.mjs': ('src/playback.mjs', 'text/javascript')}
        filename, media_type = files[name]
        return FileResponse(Path(__file__).resolve().parents[1] / 'desktop' / filename, media_type=media_type)

    async def events(request):
        after = int(request.query_params.get('after', 0))
        async def stream():
            nonlocal after
            previous_jobs = None
            while not await request.is_disconnected():
                for event in await run_in_threadpool(store.events, after):
                    after = event['sequence']
                    yield f'id: {after}\nevent: revision\ndata: {json.dumps(event)}\n\n'
                jobs = await run_in_threadpool(list_jobs)
                job_state = json.dumps(jobs, sort_keys=True)
                if job_state != previous_jobs:
                    yield f'event: jobs\ndata: {job_state}\n\n'
                    previous_jobs = job_state
                yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})

    http_mcp = mcp.streamable_http_app(json_response=True, stateless_http=True)

    @contextlib.asynccontextmanager
    async def lifespan(app):
        async with mcp.session_manager.run():
            yield

    app = Starlette(routes=[Route('/health', health), Route('/debug', debug), Route('/debug/playback.mjs', debug), Route('/app', editor), Route('/app/{asset}', editor), Route('/api/v1/projects', dispatch, methods=['GET', 'POST']),
                            Route('/api/v1/media', upload_media, methods=['POST']),
                            Route('/api/v1/jobs', dispatch, methods=['GET', 'POST']),
                            Route('/api/v1/jobs/{job_id}', dispatch),
                            Route('/api/v1/jobs/{job_id}/cancel', dispatch, methods=['POST']),
                            Route('/api/v1/events', events),
                            Route('/api/v1/projects/{project_id}/artifacts/{role}', artifact),
                            Route('/api/v1/projects/{project_id}', dispatch),
                            Route('/api/v1/projects/{project_id}/{action}', dispatch, methods=['GET', 'POST']),
                            Mount('/', http_mcp)], lifespan=lifespan)

    class LocalAccess:
        def __init__(self, application): self.application = application
        async def __call__(self, scope, receive, send):
            if scope['type'] == 'http':
                headers = dict(scope.get('headers', []))
                host = headers.get(b'host', b'').decode()
                origin = headers.get(b'origin', b'').decode()
                allowed = ('http://' + host, 'tauri://localhost', 'http://tauri.localhost')
                authorized = secrets.compare_digest(headers.get(b'authorization', b'').decode(), 'Bearer ' + token)
                if host.split(':')[0] not in ('127.0.0.1', 'localhost') or (origin and origin not in allowed):
                    await JSONResponse({'error': 'Local host/origin required.'}, status_code=403)(scope, receive, send); return
                if scope['path'] not in ('/health', '/debug', '/debug/playback.mjs', '/app', '/app/app.js', '/app/app.css', '/app/playback.mjs') and not authorized:
                    await JSONResponse({'error': 'Use the local discovery bearer token.'}, status_code=401)(scope, receive, send); return
            await self.application(scope, receive, send)
    return LocalAccess(app)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Start the authenticated loopback API/MCP service; closing a UI does not stop jobs.')
    parser.add_argument('--port', type=int, default=0, help='0 chooses a free port; bind only to 127.0.0.1.')
    parser.add_argument('--discovery', type=Path, default=ROOT / 'song-service.json')
    parser.add_argument('--log-level', choices=['debug', 'info', 'warning'], default='info')
    parser.add_argument('--open-browser', action='store_true', help='Open and connect the review UI when ready.')
    parser.add_argument('--no-browser', action='store_false', dest='open_browser', help='Print the UI URL without opening a browser.')
    args = parser.parse_args(argv)
    if args.discovery.is_file():
        try:
            record = json.loads(args.discovery.read_text())
            # A stale discovery file must never cause a request to a remote host.
            url = record['url']
            from urllib.parse import urlsplit
            if urlsplit(url).hostname != '127.0.0.1': raise ValueError('Invalid discovery host.')
            with urllib.request.urlopen(url + '/health', timeout=2) as response:
                info = json.load(response)
            if info == {'name': 'mgmv-local', 'api_version': API_VERSION}:
                print('Compatible service already running:', url, flush=True)
                show_review(record, args.open_browser)
                return 0
        except (OSError, ValueError, KeyError): pass
    try:
        with discovery_lease(args.discovery):
            return run_service(args)
    except (ValueError, OSError) as error:
        parser.error(str(error))


def run_service(args):
    token = secrets.token_urlsafe(32)
    with socket.socket() as listener:
        try:
            listener.bind(('127.0.0.1', args.port))
        except OSError as error:
            raise ValueError('Requested loopback port is unavailable: ' + str(error)) from error
        listener.listen(128)
        port = listener.getsockname()[1]
        record = {'api_version': API_VERSION, 'url': f'http://127.0.0.1:{port}', 'mcp_url': f'http://127.0.0.1:{port}/mcp', 'token': token}
        write_json(args.discovery, record)
        print('Discovery:', args.discovery, '| API/MCP:', record['url'], flush=True)
        try:
            config = uvicorn.Config(create_app(token), log_level=args.log_level)
            class ReviewServer(uvicorn.Server):
                async def startup(self, sockets=None):
                    await super().startup(sockets=sockets)
                    if self.started:
                        show_review(record, args.open_browser)
            ReviewServer(config).run(sockets=[listener])
        finally:
            if args.discovery.is_file() and json.loads(args.discovery.read_text()).get('token') == token:
                args.discovery.unlink()
    return 0


if __name__ == '__main__': raise SystemExit(main())
