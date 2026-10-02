#!/usr/bin/env python3
import argparse, hashlib, json, os, selectors, signal, stat, subprocess, time
from pathlib import Path
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=argparse.ArgumentParser(); p.add_argument('--nexus',type=Path,required=True); p.add_argument('--root',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
env={**os.environ,'XDG_STATE_HOME':str(a.root/'xdg-state'),'XDG_RUNTIME_DIR':str(a.root/'xdg-runtime')}; cmd=[str(a.nexus)]; before={'db':digest(a.root/'xdg-state/lojix/lojix.sema'),'archive':digest(a.root/'old-startup.rkyv'),'source_store':digest(a.root/'old-state/store.db')}; out=bytearray(); err=bytearray(); failure=None; proc=None
try:
 proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE); sel=selectors.DefaultSelector(); sel.register(proc.stdout,selectors.EVENT_READ,out); sel.register(proc.stderr,selectors.EVENT_READ,err); deadline=time.monotonic()+30; ready=False
 while time.monotonic()<deadline and not ready:
  for key,_ in sel.select(deadline-time.monotonic()):
   data=os.read(key.fileobj.fileno(),65536)
   if data: key.data.extend(data)
   else: sel.unregister(key.fileobj)
  if any(x.startswith(b'(LojixNexusReady ') for x in out.splitlines()):
   line=next(x for x in out.splitlines() if x.startswith(b'(LojixNexusReady ')); fields=line.decode().rstrip(')').split(); expected=[str(a.root/'old-state/ordinary.sock'),str(a.root/'old-state/owner.sock')]
   if fields[1:]!=expected: raise RuntimeError('readiness socket paths differ')
   for path in expected:
    if not stat.S_ISSOCK(os.lstat(path).st_mode) or not Path(path).resolve().is_relative_to(a.root.resolve()): raise RuntimeError('socket confinement failed')
   ready=True
  if proc.poll() is not None and not ready: raise RuntimeError('early exit before readiness')
 if not ready: raise RuntimeError('readiness timeout')
 proc.send_signal(signal.SIGTERM)
 while proc.poll() is None and time.monotonic()<deadline:
  for key,_ in sel.select(.1):
   data=os.read(key.fileobj.fileno(),65536)
   if data: key.data.extend(data)
 proc.wait(timeout=1)
 if proc.returncode: raise RuntimeError(f'shutdown status {proc.returncode}')
except Exception as e:
 failure=str(e)
finally:
 if proc and proc.poll() is None: proc.kill(); proc.wait()
 a.output.mkdir(parents=True,exist_ok=True); (a.output/'startup.stdout').write_bytes(out); (a.output/'startup.stderr').write_bytes(err); (a.output/'startup.status').write_text(str(proc.returncode if proc else -1)+'\n'); (a.output/'startup-evidence.json').write_text(json.dumps({'command':cmd,'xdg_state':env['XDG_STATE_HOME'],'xdg_runtime':env['XDG_RUNTIME_DIR'],'before':before,'after':{'db':digest(a.root/'xdg-state/lojix/lojix.sema'),'archive':digest(a.root/'old-startup.rkyv'),'source_store':digest(a.root/'old-state/store.db')},'error':failure})+'\n')
if failure: raise SystemExit(failure)
