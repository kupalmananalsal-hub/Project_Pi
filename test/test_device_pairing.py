import tempfile, unittest
from pathlib import Path
from raspberry_pi.device_pairing import DeviceRegistry

class PairingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve(); self.root.chmod(0o700)
        self.now=1000.
        self.registry=DeviceRegistry(self.root,clock=lambda:self.now)
        self.registry.initialize()
        self.identity='a'*32
        self.proof='fixture-poll-proof-'+'b'*40
    def request(self,role='caregiver'):
        return self.registry.request(role,self.identity,self.proof)
    def approve(self,role='caregiver'):
        self.registry.open_window(120)
        request=self.request(role)
        self.registry.approve(request['request_id'],request['code'])
        return self.registry.claim(request['request_id'],self.proof)
    def test_window_and_local_approval_required(self):
        with self.assertRaises(ValueError): self.request()
        self.registry.open_window(120)
        req=self.request()
        self.assertEqual(self.registry.claim(req['request_id'],self.proof)['state'],'pending')
        with self.assertRaises(ValueError): self.registry.approve(req['request_id'],'wrong')
        self.registry.approve(req['request_id'],req['code'])
        grant=self.registry.claim(req['request_id'],self.proof)
        self.assertEqual(grant['role'],'caregiver')
        self.assertTrue(self.registry.authenticate(self.identity,grant['token'],'caregiver'))
        self.assertFalse(self.registry.authenticate(self.identity,grant['token'],'resident'))
    def test_expired_or_wrong_poll_proof_never_gets_credentials(self):
        self.registry.open_window(120); req=self.request()
        with self.assertRaises(ValueError): self.registry.claim(req['request_id'],'wrong')
        self.now+=181
        with self.assertRaises(ValueError): self.registry.approve(req['request_id'],req['code'])
        with self.assertRaises(ValueError): self.registry.claim(req['request_id'],self.proof)
    def test_identity_survives_restart_and_ip_changes_and_revocation(self):
        grant=self.approve()
        again=DeviceRegistry(self.root,clock=lambda:self.now)
        self.assertEqual(again.discovery()['pi_id'],grant['pi_id'])
        self.assertTrue(again.authenticate(self.identity,grant['token'],'caregiver'))
        self.assertEqual(again.claim(grant['request_id'],self.proof)['token'],grant['token'])
        proof=again.prove(self.identity,'fixture-nonce-'+'c'*32)
        self.assertEqual(len(proof['proof']),64)
        again.revoke(self.identity)
        self.assertFalse(again.authenticate(self.identity,grant['token'],'caregiver'))
        with self.assertRaises(ValueError): again.prove(self.identity,'fixture-nonce-'+'c'*32)
    def test_resident_cannot_acquire_caregiver_role_or_reenroll_existing_identity(self):
        grant=self.approve('resident')
        self.assertTrue(self.registry.authenticate(self.identity,grant['token'],'resident'))
        with self.assertRaises(ValueError): self.request('caregiver')
        self.assertNotIn('token',self.registry.discovery())
    def test_claim_guess_limit_and_closed_window_do_not_bypass_approval(self):
        self.registry.open_window(120);req=self.request()
        for i in range(8):
            with self.assertRaises(ValueError):self.registry.claim(req['request_id'],'wrong-proof')
        with self.assertRaises(ValueError):self.registry.approve(req['request_id'],req['code'])
    def test_wrong_server_proof_cannot_match_another_device(self):
        import hashlib,hmac
        grant=self.approve()
        nonce='fixture-challenge-'+'z'*32
        expected=hmac.new(hashlib.sha256(grant['token'].encode()).digest(),f"{grant['pi_id']}:{self.identity}:{nonce}".encode(),'sha256').hexdigest()
        self.assertEqual(self.registry.prove(self.identity,nonce)['proof'],expected)
        self.assertNotEqual(self.registry.prove(self.identity,nonce+'x')['proof'],expected)
    def test_local_revoke_and_reapproval_preserve_device_identity(self):
        old=self.approve();self.registry.revoke(self.identity)
        new=self.approve()
        self.assertEqual(old['device_id'],new['device_id'])
        self.assertNotEqual(old['token'],new['token'])
        self.assertFalse(self.registry.authenticate(self.identity,old['token'],'caregiver'))
    def test_invalid_roles_and_bounded_pending_requests(self):
        self.registry.open_window(120)
        with self.assertRaises(ValueError): self.request('admin')
        for i in range(32): self.registry.request('resident',f'{i:032x}',self.proof)
        with self.assertRaises(ValueError): self.request()

if __name__=='__main__': unittest.main()
