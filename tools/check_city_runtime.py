#!/usr/bin/env python3
"""Data-free city runtime regression checks using the locally built OGB helper."""
import sys, copy, json, subprocess, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'sc4-lab/adapters/openglassbox'))
import city_contract as contract
from openglassbox_sidecar import Backend, digest, BridgeError
from helper_transport import HelperTransport, TransportError
city={'schema':'opensc4.canonical-city.v1','dimensions':{'width':8,'height':8}, 'entities':[
{'id':'home','position':{'x':1,'y':1},'attributes':{'class':'residential','capacity':{'r':200},'pollution':{'air':2},'pollution_radius':{'air':2},'upkeep':5}},
{'id':'job','position':{'x':5,'y':1},'attributes':{'class':'commercial','capacity':{'c':200},'pollution':{'air':1},'pollution_radius':{'air':1},'upkeep':7}}], 'networks':{'road':{'nodes':[{'id':str(x),'position':{'x':x,'y':2}} for x in range(1,7)], 'edges':[{'from':str(x),'to':str(x+1),'kind':'Road'} for x in range(1,6)]}}}
contract.city(city)
bad=copy.deepcopy(city);bad['networks']['road']['edges'][0]['to']='missing'
try: contract.city(bad)
except ValueError: pass
else: raise AssertionError('missing node accepted')
for value in [-1,1.5,float('nan'),float('inf')]:
    try: contract.command({'type':'city_advance','days':value},True)
    except ValueError: pass
    else: raise AssertionError(value)
a=Backend('/tmp/opensc4-openglassbox-helper');b=Backend('/tmp/opensc4-openglassbox-helper')
try:
    payload={'city':city,'start_date':'2000-02-27','seed':42,'funds':50000}
    a.city_init(payload)
    result=a.city_advance(3)
    assert result['date']=='2000-03-01',result
    assert len(result['months'])==1 and result['months'][0]['period']=='2000-02'
    state=a.save()
    b.restore_city(state)
    assert a.checkpoint_observation()==b.checkpoint_observation()
    assert a.events_since(0)==b.events_since(0)
    a.city_advance(2);b.city_advance(2)
    assert a.checkpoint_observation()==b.checkpoint_observation()
    corrupt=copy.deepcopy(state);corrupt['elapsed_days']=20
    try:b.restore_city(corrupt)
    except BridgeError:pass
    else:raise AssertionError('corrupt state accepted')
    print('PASS canonical validation, leap-month accounting, checkpoint reconstruction, continuation, event persistence, integrity rejection')
finally:a.close();b.close()
for code in ['import time; time.sleep(5)', 'print("x"*200, flush=True)', 'pass']:
    process=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    transport=HelperTransport(process, timeout=.1,max_reply=100)
    try: transport.exchange('HELLO')
    except TransportError: pass
    else:raise AssertionError('transport failure not caught')
    finally:transport.close()
print('PASS helper timeout, oversized output, EOF and cleanup')

# Road ordering must be stable across Python hash seeds, not just in one process.
program = "import json,sys; sys.path.insert(0,sys.argv[1]); import sc4_city_ruleset as r; print(json.dumps(r.build(json.loads(sys.stdin.read()))[:2]))"
outputs = []
for seed in ("1", "42", "321"):
    run = subprocess.run([sys.executable, "-c", program, sys.path[0]], input=json.dumps(city),
                         capture_output=True, text=True, check=True, env=dict(os.environ, PYTHONHASHSEED=seed))
    outputs.append(run.stdout)
assert len(set(outputs)) == 1
print('PASS cross-process road/ruleset determinism')

# Exercise protocol-level transactional restore and rejection without touching a retail city.
from openglassbox_sidecar import PROTOCOL
process = subprocess.Popen([sys.executable, str(Path(sys.path[0])/'openglassbox_sidecar.py')],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
def call(operation, payload):
    process.stdin.write(json.dumps(dict(protocol=PROTOCOL, request_id=1, operation=operation, payload=payload))+'\n')
    process.stdin.flush()
    return json.loads(process.stdout.readline())
try:
    assert call('command', dict(type='city_init',city=city,start_date='1999-12-31'))['ok']
    result = call('command', dict(type='city_advance',days=1))['result']
    assert result['date']=='2000-01-01' and result['months'][0]['period']=='1999-12'
    saved = call('save', {})['result']
    original = call('snapshot', {})['result']
    tampered = copy.deepcopy(saved); tampered['identity']='different-engine'
    assert not call('load',tampered)['ok']
    assert call('snapshot',{})['result']==original
    tampered = copy.deepcopy(saved); tampered['observation_digest']='diverged'
    tampered['digest']=digest({k:v for k,v in tampered.items() if k!='digest'})
    assert not call('load',tampered)['ok']
    assert call('snapshot',{})['result']==original
    assert not call('command',dict(type='city_init',city=bad))['ok']
    assert call('snapshot',{})['result']==original
    assert call('load',saved)['ok']
    assert call('snapshot',{})['result']==original
    assert not call('events',{'cursor':999})['ok']
    assert not call('command',{'type':'city_layer','name':'AirPollution\nRESET'})['ok']
    print('PASS year rollover, transactional restore, engine mismatch, replay divergence, invalid init and cursor')
finally:
    call('shutdown',{})
    process.wait(timeout=5)
    process.stdin.close(); process.stdout.close()

# Linux parent-death cleanup: a killed sidecar must not leave its native helper running.
if sys.platform == 'linux':
    import time
    process = subprocess.Popen([sys.executable, str(Path(sys.path[0])/'openglassbox_sidecar.py')],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert call('hello', {})['ok']
        children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
        assert children
        process.kill(); process.wait(timeout=5)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            alive = [pid for pid in children if Path(f'/proc/{pid}/stat').exists()
                     and Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z']
            if not alive:
                break
            time.sleep(.01)
        assert not alive, alive
        print('PASS sidecar death terminates native helper')
    finally:
        if process.poll() is None:
            process.kill(); process.wait(timeout=5)
        process.stdin.close(); process.stdout.close()
