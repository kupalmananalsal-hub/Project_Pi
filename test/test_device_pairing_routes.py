"""Real ASGI pairing/auth fixtures, with mocked hardware and temporary state."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test.test_backend_alert_smoke import load_backend_module,restore_modules
from raspberry_pi.device_pairing import DeviceRegistry
try:
 from fastapi.testclient import TestClient
except ImportError: TestClient=None

@unittest.skipIf(TestClient is None,'optional HTTP test dependencies unavailable')
class PairingRoutesTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
  self.module,previous=load_backend_module(str(self.root),real_http=True);self.addCleanup(restore_modules,previous)
  self.module.API_AUTH_MODE='required';self.module.API_TOKEN='fixture-backend-admin-token'
  self.registry=DeviceRegistry(self.root);self.registry.initialize();self.module.device_registry=self.registry
  self.env=patch.dict(os.environ,{'PROJECT_PI_PAIRING_DIR':str(self.root)});self.env.start();self.addCleanup(self.env.stop)
  self.client=TestClient(self.module.app);self.addCleanup(self.client.close)
 def enroll(self,role,identity):
  self.registry.open_window(120)
  response=self.client.post('/api/pairing/request',json={'role':role,'device_id':identity,'claim_proof':'fixture-request-proof-'+'x'*32})
  self.assertEqual(response.status_code,200,response.text);req=response.json()
  self.assertEqual(self.client.post('/api/pairing/claim',json={'request_id':req['request_id'],'claim_proof':'fixture-request-proof-'+'x'*32}).json()['state'],'pending')
  self.registry.approve(req['request_id'],req['code'])
  grant=self.client.post('/api/pairing/claim',json={'request_id':req['request_id'],'claim_proof':'fixture-request-proof-'+'x'*32}).json()
  return {'Authorization':'Bearer '+grant['token'],'X-Device-Id':identity,'X-Resident-Id':identity},grant
 def test_minimal_health_and_no_remote_approval_or_anonymous_control(self):
  discovery=self.client.get('/api/discovery').json()
  self.assertEqual(set(discovery),{'protocol','service','pi_id','pairing_available','enrollment_open'})
  self.assertEqual(self.client.get('/api/status').status_code,401)
  self.assertEqual(self.client.post('/api/pairing/approve',json={}).status_code,401)
  self.assertEqual(self.client.post('/api/alerts/manual',json={}).status_code,401)
 def test_roles_do_not_authorize_admin_training_or_resident_mute(self):
  main,_=self.enroll('caregiver','a'*32)
  resident,_=self.enroll('resident','b'*32)
  self.assertEqual(self.client.get('/api/status',headers=main).status_code,200)
  for path in ['/api/refresh','/api/training/deploy','/api/training/train','/api/alerts']:
   self.assertEqual(self.client.post(path,headers=main,json={}).status_code,401,path)
  self.assertEqual(self.client.get('/api/status',headers=resident).status_code,401)
  self.assertEqual(self.client.post('/api/resident/control',headers=resident,json={'action':'mute_start'}).status_code,403)
 def test_paired_caregiver_uses_existing_durable_delivery_identity(self):
  headers,grant=self.enroll('caregiver','c'*32)
  with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
   ws.send_json({'protocol_version':2,'type':'authenticate','installation_id':'c'*32,'token':grant['token']})
   self.assertEqual(ws.receive_json()['type'],'connected')
  self.registry.revoke('c'*32)
  self.assertEqual(self.client.get('/api/status',headers=headers).status_code,401)
 def test_migrated_identity_cannot_bypass_revocation_with_legacy_secret(self):
  import json,hashlib
  from alert_delivery import authenticate
  identity='e'*32;old_secret='fixture-old-caregiver-secret'
  path=self.root/'legacy.json';path.write_text(json.dumps({identity:hashlib.sha256(old_secret.encode()).hexdigest()}))
  with patch.dict(os.environ,{'PROJECT_PI_CAREGIVER_CREDENTIALS':str(path)}):
   self.assertTrue(authenticate(identity,old_secret))
   _,grant=self.enroll('caregiver',identity)
   self.assertFalse(authenticate(identity,old_secret))
   self.assertTrue(authenticate(identity,grant['token']))
   self.registry.revoke(identity)
   self.assertFalse(authenticate(identity,old_secret))
   self.assertFalse(authenticate(identity,grant['token']))
 def test_bad_messages_and_closed_window_fail_without_enrollment(self):
  self.assertEqual(self.client.post('/api/pairing/request',json={'role':'caregiver','device_id':'d'*32,'claim_proof':'x'*40}).status_code,409)
  self.assertEqual(self.client.post('/api/pairing/request',content='x'*4097).status_code,413)
  self.assertEqual(self.client.post('/api/pairing/request',content='[]').status_code,400)

if __name__=='__main__':unittest.main()
