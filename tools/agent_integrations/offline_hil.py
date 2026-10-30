"""Offline HIL contract checks: consume fixtures, never open a device."""
import argparse,json,math,time,wave
from pathlib import Path


def thermal_frame(payload, now=None):
    now=time.time() if now is None else now
    frame=payload.get('temperatures',[])
    errors=[]
    if len(frame)!=768: errors.append('Expected 32x24 (768) temperatures')
    if any(type(v) not in (int,float) or not math.isfinite(v) or not -40<=v<=300 for v in frame): errors.append('Invalid temperature values')
    stamp=payload.get('timestamp')
    if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<=now-stamp<=2: errors.append('Stale or invalid timestamp')
    latency=payload.get('read_latency_ms')
    if type(latency) not in (int,float) or not math.isfinite(latency) or not 0<=latency<=2000: errors.append('Invalid read latency')
    return {'mode':'OFFLINE_FIXTURE','passed':not errors,'errors':errors,'refresh_rate_hz':payload.get('refresh_rate_hz','unknown')}


def audio_file(path):
    with wave.open(str(path),'rb') as f:
        rate,channels,width,frames=f.getframerate(),f.getnchannels(),f.getsampwidth(),f.getnframes()
        if width!=2 or not 0<frames<=rate*10 or channels not in (1,2): raise ValueError('Require <=10 second mono/stereo PCM16 WAV')
        raw=f.readframes(frames)
    if len(raw)!=frames*channels*width: raise ValueError('Truncated WAV')
    samples=[int.from_bytes(raw[i:i+2],'little',signed=True) for i in range(0,len(raw),2)]
    rms=math.sqrt(sum(v*v for v in samples)/len(samples))/32768
    return {'mode':'OFFLINE_FILE','sample_rate':rate,'channels':channels,'duration_s':frames/rate,
            'clipped_samples':sum(abs(v)>=32760 for v in samples),'rms':rms,'silent':rms<.001,
            'vad_activity':'NOT_MEASURED','capture_latency':'NOT_MEASURED'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--thermal-json',type=Path);p.add_argument('--audio-wav',type=Path)
    a=p.parse_args()
    if bool(a.thermal_json)==bool(a.audio_wav):p.error('Select one offline fixture')
    print(json.dumps(thermal_frame(json.loads(a.thermal_json.read_text())) if a.thermal_json else audio_file(a.audio_wav),indent=2))
if __name__=='__main__':main()
