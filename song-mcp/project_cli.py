"""Independent project CLI; never requires a running GUI or HTTP service."""
import argparse
import json
import sys
import uuid
from pathlib import Path

from common import ROOT
from core.projects import ProjectStore, Conflict


def main(argv=None):
    import os
    parser = argparse.ArgumentParser(description='Import, review, correct and export versioned song projects.')
    parser.add_argument('--project-root', type=Path, default=Path(os.environ.get('MGMV_PROJECT_ROOT', ROOT / 'song-projects')))
    commands = parser.add_subparsers(dest='command', required=True)
    imp = commands.add_parser('import')
    imp.add_argument('analysis', type=Path)
    imp.add_argument('--mix', type=Path)
    imp.add_argument('--vocals', type=Path)
    commands.add_parser('list')
    for name in ('read', 'history', 'validate', 'apply', 'restore', 'export'):
        sub = commands.add_parser(name)
        sub.add_argument('project_id')
        if name == 'apply': sub.add_argument('correction', type=Path)
        if name == 'restore':
            sub.add_argument('target_revision', type=int)
            sub.add_argument('--expected-revision', required=True, type=int)
            sub.add_argument('--transaction-id', required=True)
        if name == 'export':
            sub.add_argument('output', type=Path)
            sub.add_argument('--revision', type=int)
    args = parser.parse_args(argv)
    try:
        store = ProjectStore(args.project_root)
        if args.command == 'import':
            value = store.import_analysis(args.analysis, {k: v for k, v in {'mix': args.mix, 'vocals': args.vocals}.items() if v})
        elif args.command == 'list': value = store.list()
        elif args.command == 'read': value = store.read(args.project_id)
        elif args.command == 'history': value = store.history(args.project_id)
        elif args.command == 'validate': value = {'review_items': store.read(args.project_id)['analysis']['review_items']}
        elif args.command == 'apply': value = store.apply(args.project_id, json.loads(args.correction.read_text(encoding='utf-8-sig')))
        elif args.command == 'export': value = store.export(args.project_id, args.output, args.revision)
        else:
            project = store.read(args.project_id)
            correction = {'schema_version': 1, 'project_id': args.project_id, 'base_revision': args.expected_revision,
                          'base_analysis_sha256': project['base_analysis_sha256'], 'transaction_id': args.transaction_id}
            value = store.apply(args.project_id, correction, target_revision=args.target_revision)
        print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except Conflict as error:
        print(str(error), file=sys.stderr); return 4
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(str(error), file=sys.stderr); return 1


if __name__ == '__main__': raise SystemExit(main())
