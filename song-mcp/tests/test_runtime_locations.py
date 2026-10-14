"""Runtime relocation must survive detached launch and MCP configuration."""
import json
import os
import subprocess
import sys
from pathlib import Path

import tomli

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configure_client import render


def test_worker_paths_survive_detached_launch(tmp_path):
    source = Path(__file__).resolve().parents[1]
    env = dict(os.environ, MGMV_WORKSPACE_ROOT=str(tmp_path/'runtime'),
               MGMV_ANALYZER_ROOT=str(tmp_path/'analyzer'),
               MGMV_MODEL_CACHE=str(tmp_path/'weights'))
    code = "import json,common;print(json.dumps(common.worker_command('a'*32, detached=True)))"
    command = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=source, env=env, text=True))
    # A WMI process has none of the calling server's location overrides.
    clean = {k:v for k,v in os.environ.items() if not k.startswith('MGMV_')}
    probe = "import runpy,sys,json;sys.argv=json.loads(sys.argv[1]);runpy.run_path(sys.argv[0],run_name='runtime_probe');import common;print(json.dumps([str(common.ROOT),str(common.ANALYZER_ROOT),str(common.MODEL_CACHE)]))"
    paths = json.loads(subprocess.check_output([sys.executable, '-c', probe, json.dumps(command[2:])], cwd=source, env=clean, text=True))
    assert paths == [env['MGMV_WORKSPACE_ROOT'], env['MGMV_ANALYZER_ROOT'], env['MGMV_MODEL_CACHE']]
    assert '--detached' in command


def test_client_formats_resolve_same_source_and_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv('MGMV_WORKSPACE_ROOT',str(tmp_path))
    generic=json.loads(render('json'))['mcpServers']['mgmv_song']
    codex=tomli.loads(render('toml'))['mcp_servers']['mgmv_song']
    assert generic['args']==codex['args']
    assert Path(generic['args'][0]).is_file()
    assert generic['env']['MGMV_WORKSPACE_ROOT']==str(tmp_path)
