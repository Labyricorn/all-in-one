"""Print a local MCP configuration with resolved paths; write nothing implicitly."""
import argparse
import json
import os
import sys
from pathlib import Path


def configuration(python=None):
    source = Path(__file__).resolve().parent
    return {'command': str(Path(python or sys.executable).resolve()),
            'args': [str(source / 'server.py')], 'cwd': str(source.parent),
            'env': {'PYTHONIOENCODING': 'utf-8', **{
                key: os.environ[key] for key in
                ('MGMV_WORKSPACE_ROOT', 'MGMV_ANALYZER_ROOT', 'MGMV_MODEL_CACHE', 'MGMV_PROJECT_ROOT')
                if key in os.environ}}}


def render(format, python=None):
    config = configuration(python)
    if format == 'json':
        return json.dumps({'mcpServers': {'mgmv_song': config}}, indent=2)
    # JSON strings/arrays are valid TOML basic strings/arrays here.
    lines = ['[mcp_servers.mgmv_song]']
    lines += [key + ' = ' + json.dumps(config[key]) for key in ('command', 'args', 'cwd')]
    lines += ['startup_timeout_sec = 30', 'tool_timeout_sec = 60', 'enabled = true',
              '', '[mcp_servers.mgmv_song.env]']
    lines += [key + ' = ' + json.dumps(value) for key, value in config['env'].items()]
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--format', choices=['json', 'toml'], default='json')
    parser.add_argument('--python', help='Lyric-environment Python; defaults to this interpreter.')
    parser.add_argument('--http-discovery', type=Path, help='Generate live HTTP MCP connection settings from the local service discovery file.')
    args = parser.parse_args()
    if args.http_discovery:
        from urllib.parse import urlsplit
        record = json.loads(args.http_discovery.read_text())
        if record.get('api_version') != 1 or urlsplit(record['mcp_url']).hostname != '127.0.0.1':
            parser.error('Unsupported or non-loopback discovery record.')
        config = {'url': record['mcp_url'], 'headers': {'Authorization': 'Bearer ' + record['token']}}
        if args.format == 'json': print(json.dumps({'mcpServers': {'mgmv_song_live': config}}, indent=2))
        else:
            print('[mcp_servers.mgmv_song_live]\nurl = ' + json.dumps(config['url']) + '\n\n[mcp_servers.mgmv_song_live.http_headers]\nAuthorization = ' + json.dumps(config['headers']['Authorization']))
    else: print(render(args.format, args.python))
