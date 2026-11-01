#!/usr/bin/env python3
"""Mock integration tests: isolated Docker, no network/capabilities/kernel modules."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import textwrap

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True, help='Rendered service bundle; outputs stay outside the skill source')
    parser.add_argument('--image', default=os.environ.get('WIREGUARD_TEST_IMAGE', 'wireguard-tun-build:pw3'))
    args = parser.parse_args()
    BASE = args.bundle.resolve()
    IMAGE = args.image
    subprocess.run(['docker', 'image', 'inspect', IMAGE], check=True, stdout=subprocess.DEVNULL)
    FIX = Path(tempfile.mkdtemp(prefix='mock-tests-', dir=BASE))
    for folder in ['bin', 'state', 'upstart', 'mnt-us/kwg-service',
                   'mnt-us/koreader/plugins/kwg.koplugin', 'mnt-us/kwg-tun']:
        (FIX / folder).mkdir(parents=True, exist_ok=True)

    def script(name, content):
        path = FIX / name
        path.write_text('#!/bin/sh\n' + content)
        path.chmod(0o755)

    # Substitute only the boot-ID input path in fixture copies; do not mount over /proc.
    for source, target in [('control.sh', 'mnt-us/kwg-service/control.sh'),
                           ('kwg-loop.sh', 'mnt-us/koreader/plugins/kwg.koplugin/kwg-loop.sh')]:
        content = (BASE / source).read_text().replace('/proc/sys/kernel/random/boot_id', '/fixtures/boot-id')
        if source == 'control.sh':
            content = content.replace("[ -c /dev/net/tun ] && grep -Eq '(^|[[:space:]])tun$' /proc/misc", "[ -f /fixtures/mock-tun-ready ]")
        (FIX / target).write_text(content)
    (FIX / 'mock-tun-ready').write_text('controller readiness fixture only; no real TUN device\n')
    shutil.copyfile(BASE / 'kwg.upstart', FIX / 'mnt-us/kwg-service/kwg.upstart')
    (FIX / 'state/wg.conf').write_text('valid synthetic config; no real credentials\n')
    (FIX / 'boot-id').write_text('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa\n')
    (FIX / 'network').write_text('default via 192.0.2.1 dev wlan0\n')
    (FIX / 'handshake').write_text('3s ago\n')
    script('bin/uname', 'case "$1" in -r) echo 3.0.35-lab126;; -m) echo armv7l;; *) exec /usr/bin/uname "$@";; esac\n')
    script('bin/sha256sum', 'if [ "$1" = /proc/version ]; then echo "d7ea2ab48e56b27c5e7f53488d140ea58bc242463b33d2605092a18b5e674918  /proc/version"; elif [ "$1" = /mnt/us/koreader/plugins/kwg.koplugin/kwg.bin ]; then echo "9167c55f126cd6b74dbe3184b22a59fe1dc90c829754d0d5d0cf6eb731a6dee3  $1"; else exec /usr/bin/sha256sum "$@"; fi\n')
    script('bin/ip', 'cat /fixtures/network\n')
    script('bin/mntroot', 'printf "%s\\n" "$1" >> /fixtures/remounts\n')
    script('bin/initctl', 'exit 0\n')
    script('bin/status', 'if [ -f /var/local/kwg/mock-service ]; then echo "kwg start/running, process 4242"; else echo "kwg stop/waiting"; fi\n')
    script('bin/start', '''touch /var/local/kwg/mock-service /var/local/kwg/mock-up
    printf 'start\n' >> /fixtures/start-count
    origin=${MOCK_START_ORIGIN:-manual}
    cat /fixtures/boot-id > /var/local/kwg/service-boot-id
    printf '%s\n' "$origin" > /var/local/kwg/service-origin
    printf 'tunnel_up\n' > /var/local/kwg/service-phase
    printf '{"origin":"%s"}\n' "$origin" > /var/local/kwg/service-start.json
    ''')
    script('bin/stop', 'rm -f /var/local/kwg/mock-service /var/local/kwg/mock-up\nprintf "stop\\n" >> /fixtures/stop-count\n')
    script('mnt-us/koreader/plugins/kwg.koplugin/kwg.bin', '''case "$1" in
    check) if grep -q INVALID "$2"; then exit 1; fi; echo ok ;;
    status)
        if [ -f /var/local/kwg/mock-up ]; then
            echo 'state: up'; echo 'address: 10.77.77.8/24'
            printf 'handshake: '; cat /fixtures/handshake
            echo 'received: 348 B'; echo 'sent: 436 B'
        else echo 'state: down'; exit 3; fi
        ;;
    up)
        printf 'start:%s\n' "$$" >> /fixtures/up-events
        touch /var/local/kwg/mock-up
        trap 'printf "stop:%s\\n" "$$" >> /fixtures/up-events; rm -f /var/local/kwg/mock-up; exit 0' TERM INT
        while :; do sleep 1 & wait $!; done
        ;;
    *) exit 2 ;;
    esac
    ''')
    script('mnt-us/koreader/plugins/kwg.koplugin/kwg', 'exec /mnt/us/koreader/plugins/kwg.koplugin/kwg.bin "$@"\n')
    script('mnt-us/kwg-tun/load-test.sh', 'printf "load\\n" >> /fixtures/module-attempts\nexit 0\n')
    files = [p for p in (FIX / 'mnt-us').rglob('*') if p.is_file()]
    (FIX / 'mnt-us/kwg-service/payload.sha256').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(FIX / 'mnt-us')) + '\n'
        for p in files))

    RUNNER = r'''
    from pathlib import Path
    import json, os, signal, subprocess, time
    F=Path('/fixtures'); S=Path('/var/local/kwg')
    controller='/mnt/us/kwg-service/control.sh'
    checks=[]
    def record(name): checks.append(name)
    def call(action, expected=0):
        p=subprocess.run(['/bin/sh',controller,action],capture_output=True,text=True,timeout=40)
        if p.returncode!=expected:
            raise AssertionError((action,p.returncode,p.stdout,p.stderr))
        s=json.loads((S/'status.json').read_text())
        return s
    def count(path):
        p=F/path
        return len(p.read_text().splitlines()) if p.exists() else 0

    a=call('status'); assert a['connectionState']=='OFF' and not a['autostartEnabled']; record('initial_status_read_only')
    a=call('enable-autostart'); assert a['autostartEnabled'] and a['connectionState']=='CONNECTED'
    assert not a['rebootAutostartVerified'] and count('start-count')==1
    assert (F/'remounts').read_text().splitlines()==['rw','ro']; record('enable_job_and_restore_root_mode')
    call('start'); assert count('start-count')==1; record('manual_start_idempotent')
    a=call('stop'); assert a['autostartEnabled'] and a['connectionState']=='OFF'; record('stop_preserves_autostart')
    a=call('start'); assert a['connectionState']=='CONNECTED' and count('start-count')==2
    stops=count('stop-count'); a=call('disable-autostart')
    assert not a['autostartEnabled'] and a['connectionState']=='CONNECTED' and count('stop-count')==stops
    record('disable_autostart_preserves_live_tunnel')
    for handshake, age, state in [('0s ago',0,'CONNECTED'),('1m2s ago',62,'CONNECTED'),('5m0s ago',300,'STALE_HANDSHAKE'),('1h2m3s ago',3723,'STALE_HANDSHAKE'),('never',None,'WAITING_FOR_HANDSHAKE')]:
        (F/'handshake').write_text(handshake+'\n'); a=call('status')
        assert a['handshakeAgeSeconds']==age and a['connectionState']==state,(handshake,a)
    record('handshake_age_and_stale_states')
    (F/'network').write_text(''); a=call('status'); assert a['connectionState']=='WAITING_FOR_NETWORK'
    (F/'network').write_text('default via 192.0.2.1 dev wlan0\n'); (F/'handshake').write_text('3s ago\n')
    record('network_wait_state')
    call('enable-autostart')
    (F/'boot-id').write_text('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb\n')
    subprocess.run(['stop','kwg'],check=True)
    subprocess.run(['start','kwg'],env=dict(os.environ,MOCK_START_ORIGIN='framework_ready'),check=True)
    starts=count('start-count'); a=call('status')
    assert a['rebootAutostartVerified'] and a['serviceOrigin']=='framework_ready' and a['connectionState']=='CONNECTED'
    assert count('start-count')==starts; record('new_boot_event_verified_without_manual_start')
    proof=json.loads((S/'boot-verification.json').read_text()); assert proof['rebootAutostartVerified'] and proof['tunReady']
    call('stop'); assert json.loads((S/'boot-verification.json').read_text())==proof
    assert json.loads((F/'mnt-us/kwg-service/state/boot-verification.json').read_text())==proof
    call('start'); record('verified_boot_evidence_survives_manual_stop')
    job=Path('/etc/upstart/kwg.conf'); expected=job.read_bytes(); job.write_text('# unrelated job\n')
    a=call('enable-autostart',1); assert job.read_text()=='# unrelated job\n' and not a['jobConfigured']
    assert (F/'mnt-us/kwg-service/state/control-error.txt').exists(); job.write_bytes(expected)
    record('unknown_job_preserved_and_error_exported')
    loop=Path('/mnt/us/koreader/plugins/kwg.koplugin/kwg-loop.sh'); original=loop.read_bytes(); loop.write_bytes(original+b'\n# corruption test\n')
    call('enable-autostart',1); loop.write_bytes(original); record('payload_integrity_guard')

    # Watchdog tests use an actual child process, but mocked driver/network/VPN tools.
    subprocess.run(['stop','kwg'],check=True)
    (S/'tun-load-pending').unlink(missing_ok=True)
    loop_path='/mnt/us/koreader/plugins/kwg.koplugin/kwg-loop.sh'
    env=dict(os.environ,KWG_WATCH_INTERVAL='1',UPSTART_EVENTS='framework_ready',UPSTART_JOB='kwg')
    processes=[]
    def launch():
        p=subprocess.Popen(['/bin/sh',loop_path,str(S/'wg.conf'),str(S/'watchdog-test.log')],env=env,start_new_session=True)
        processes.append(p); return p
    def waitfor(predicate, timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            if predicate():return
            time.sleep(0.1)
        raise AssertionError('Timed out waiting for watchdog state')
    def phase():
        p=S/'service-phase'; return p.read_text().strip() if p.exists() else ''
    def events():
        p=F/'up-events'; return p.read_text().splitlines() if p.exists() else []
    def terminate(p):
        start=time.monotonic(); p.send_signal(signal.SIGTERM); p.wait(timeout=5)
        assert p.returncode==0 and time.monotonic()-start<5
    try:
        p=launch(); waitfor(lambda:any(x.startswith('start:') for x in events()))
        child=int([x for x in events() if x.startswith('start:')][-1].split(':')[1])
        assert not (S/'tun-load-pending').exists()
        q=launch(); q.wait(timeout=3); assert q.returncode==1
        assert p.poll() is None; record('watchdog_single_instance')
        terminate(p); waitfor(lambda:'stop:'+str(child) in events())
        assert not Path('/proc/'+str(child)).exists(); assert phase()=='stopped'
        assert not Path('/tmp/kwg-watchdog.lock').exists(); record('stop_forwards_sigterm_and_cleans_child')
        previous=len([x for x in events() if x.startswith('start:')])
        p=launch(); waitfor(lambda:len([x for x in events() if x.startswith('start:')])>previous)
        child=int([x for x in events() if x.startswith('start:')][-1].split(':')[1])
        (F/'network').write_text(''); waitfor(lambda:'stop:'+str(child) in events())
        waitfor(lambda:phase()=='waiting_network')
        previous=len([x for x in events() if x.startswith('start:')])
        (F/'network').write_text('default via 192.0.2.2 dev wlan0\n')
        waitfor(lambda:len([x for x in events() if x.startswith('start:')])>previous)
        terminate(p); record('network_loss_stops_child_and_reconnects')
        before=count('module-attempts'); (S/'tun-load-pending').write_text('old-boot-interrupted\n')
        p=launch(); waitfor(lambda:phase()=='tun_guard_paused')
        assert count('module-attempts')==before; terminate(p)
        assert (S/'tun-load-pending').exists(); record('interrupted_module_load_is_not_retried')
    finally:
        for p in processes:
            if p.poll() is None:
                os.killpg(p.pid,signal.SIGKILL); p.wait(timeout=3)
    report={'mockChecksPassed':checks,'count':len(checks),'physicalAutostart':'not_tested','realKernelModulesLoaded':False,'realNetworkAccess':False}
    (F/'test-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    '''
    (FIX / 'runner.py').write_text(textwrap.dedent(RUNNER))
    args = ['docker','run','--rm','--network','none','--cap-drop','ALL','--read-only',
            '--tmpfs','/tmp','--memory','256m','--pids-limit','128',
            '-v',f'{FIX}:/fixtures','-v',f'{FIX / "mnt-us"}:/mnt/us',
            '-v',f'{FIX / "state"}:/var/local/kwg','-v',f'{FIX / "upstart"}:/etc/upstart',
            '-e','PATH=/fixtures/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
            '--entrypoint','python3',IMAGE,'/fixtures/runner.py']
    run = subprocess.run(args, text=True, capture_output=True, timeout=100)
    (FIX / 'test.stdout').write_text(run.stdout)
    (FIX / 'test.stderr').write_text(run.stderr)
    print('Fixture directory (removed on success):', FIX)
    print(run.stdout)
    if run.returncode:
        print(run.stderr)
        raise SystemExit(run.returncode)
    shutil.copyfile(FIX / 'test-report.json', BASE / 'test-report.json')
    shutil.rmtree(FIX)  # Only the fixture directory created by this test run.


if __name__ == '__main__':
    main()
