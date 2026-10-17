"""Start the local Mac API and ML worker together; keep the existing frontend."""
import argparse
import os
from pathlib import Path
import signal
import secrets
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=6767)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    python = ROOT/'ML/.venv/bin/python'
    if not python.is_file():
        parser.error('Create ML/.venv and install backend/requirements.txt plus ML/requirements-mac.txt first')
    env = dict(os.environ)
    env.update(ML_ENGINE='reviewed_pipeline', ML_AUTO_ANALYZE='true', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    command = [str(python), '-m', 'flask', '--app', 'app']
    subprocess.run([str(python), '-c',
        'from app import app; from services.analysis import available; '
        'ctx=app.app_context(); ctx.push(); '
        'assert available(), "Missing local candidate/Qwen weights or Python environment"; '
        'print("Local pipeline weights and runtimes found")'], cwd=ROOT/'backend', env=env, check=True)
    if args.check: return
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', args.port)) == 0:
            parser.error(f'Port {args.port} is already in use; stop the previous API or pass --port')
    subprocess.run(command+['init-db'], cwd=ROOT/'backend', env=env, check=True)
    key_file=Path(env.get('JURY_API_KEY_FILE',ROOT/'backend/instance/jury-api-key.txt'))
    if not env.get('JURY_API_KEY') and not key_file.exists():
        key_file.parent.mkdir(parents=True,exist_ok=True)
        with key_file.open('x') as key: key.write(secrets.token_urlsafe(32)+'\n')
        key_file.chmod(0o600)
    logs = ROOT/'ML/runs/local_service'; logs.mkdir(parents=True, exist_ok=True)
    processes, handles = [], []
    def stop(*_): raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, tail in [('worker', ['analysis-worker']),
                           ('api', ['run', '--host', '127.0.0.1', '--port', str(args.port), '--no-reload'])]:
            log = (logs/f'{name}.log').open('a'); handles.append(log)
            processes.append(subprocess.Popen(command+tail, cwd=ROOT/'backend', env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
        ready = False
        for _ in range(30):
            if any(p.poll() is not None for p in processes):
                raise RuntimeError(f'API/worker stopped. Check logs in {logs}')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/ready', timeout=1) as response:
                    ready = response.status == 200
            except OSError: pass
            if ready: break
            time.sleep(1)
        if not ready: raise RuntimeError(f'API did not become ready. Check {logs}')
        print(f'API ready at http://127.0.0.1:{args.port}; automatic R3D + Qwen worker running.', flush=True)
        print('Open the frontend at http://localhost:3000. Ctrl+C stops API and worker.', flush=True)
        while all(p.poll() is None for p in processes): time.sleep(1)
        raise RuntimeError(f'API/worker stopped. Check logs in {logs}')
    except KeyboardInterrupt: pass
    finally:
        for process in processes:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
        for process in processes:
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL)
        for handle in handles: handle.close()


if __name__ == '__main__': main()
