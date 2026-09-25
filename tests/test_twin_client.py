"""Station-only tests: a real HTTP connection, synthetic camera, no database."""
import json
import io
import urllib.error
import os
from pathlib import Path
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
from threading import Thread
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from qc_station.storage import ResultStore
from qc_station.twin import TwinClient, post_json
from qc_station.__main__ import run
from qc_station.variants import create_variant_profile
from test_variants import scene


class TwinTests(unittest.TestCase):
    def test_old_server_claim_schema_explains_required_update(self):
        body = {'detail':[{'loc':['body','product_present'], 'msg':'Extra inputs are not permitted'}]}
        error = urllib.error.HTTPError(self.url+'/qc/claim',400,'Bad Request',{},
                                      io.BytesIO(json.dumps(body).encode()))
        with patch('urllib.request.OpenerDirector.open',side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                TwinClient(self.url,'test').claim(product_present=True)
        self.assertIn('update app/qc/api.py',str(caught.exception))
        self.assertIn('restart the API',str(caught.exception))

    def test_http_error_shows_endpoint_and_mapping_reason(self):
        error = urllib.error.HTTPError(self.url+'/qc/claim',422,'Unprocessable Entity',{},
            io.BytesIO(b'{"detail":"Product type has no qc_variant_mapping"}'))
        with patch('urllib.request.OpenerDirector.open',side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                TwinClient(self.url,'test').claim()
        self.assertEqual(caught.exception.code,422)
        self.assertIn('/qc/claim',str(caught.exception))
        self.assertIn('Product type has no qc_variant_mapping',str(caught.exception))
        self.assertIn('GET /qc/variants',str(caught.exception))

    def test_validation_detail_excludes_input_and_api_key_and_preserves_status(self):
        body = {'detail':[{'loc':['body','mode'],'msg':'invalid test-key',
                          'input':'do-not-print-input'}]}
        error = urllib.error.HTTPError(self.url+'/qc/results',503,'Unavailable',{},
            io.BytesIO(json.dumps(body).encode()))
        with patch('urllib.request.OpenerDirector.open',side_effect=error):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                post_json(self.url+'/qc/results',{})
        self.assertEqual(caught.exception.code,503)
        self.assertIn('body.mode',str(caught.exception))
        self.assertNotIn('test-key',str(caught.exception))
        self.assertNotIn('do-not-print-input',str(caught.exception))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.received = {}
        self.claims = []
        self.claim_calls = 0
        self.claim_payloads = []
        self.lose_ack = False
        self.bad_ack = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.headers.get('X-API-Key') != 'test-key':
                    self.send_error(401)
                    return
                if self.path == '/qc/claim':
                    owner.claim_calls += 1
                    owner.claim_payloads.append(body)
                    response = owner.claims.pop(0) if owner.claims else None
                elif self.path == '/qc/results':
                    identifier = body['inspection_id']
                    if self.headers.get('Idempotency-Key') != identifier:
                        self.send_error(422)
                        return
                    if identifier in owner.received and owner.received[identifier] != body:
                        self.send_error(409)
                        return
                    owner.received[identifier] = body
                    if owner.lose_ack:
                        owner.lose_ack = False
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    response = {'accepted':True,'inspection_id':'wrong' if owner.bad_ack else identifier}
                else:
                    self.send_error(404)
                    return
                data = json.dumps(response).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread = Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        env = patch.dict(os.environ,{'QC_API_KEY':'test-key'})
        env.start()
        self.addCleanup(env.stop)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def context(self, variant='A', product=1):
        return dict(inspection_id=str(uuid4()),station_id='test',product_instance_id=product,
                    order_id=10,arrival_event_id=product+100,expected_variant=variant)

    def test_lost_ack_and_restart_retry_same_result_without_database(self):
        payload = {'inspection_id':str(uuid4()),'result':{'status':'PASS'}}
        store = ResultStore(self.folder/'delivery')
        store.save(payload)
        self.lose_ack = True
        with self.assertRaises(OSError):
            store.flush(self.url+'/qc/results')
        self.assertTrue(store.has_pending())
        store.close()
        store = ResultStore(self.folder/'delivery')
        try:
            self.assertEqual(store.flush(self.url+'/qc/results'),1)
            self.assertFalse(store.has_pending())
            self.assertEqual(store.events(),[payload])
            self.assertEqual(len(self.received),1)
            self.assertEqual(len(list(self.folder.rglob('*.sqlite3'))),0)
        finally:
            store.close()

    def test_unrelated_ack_cannot_discard_result(self):
        store = ResultStore(self.folder/'delivery')
        try:
            store.save({'inspection_id':str(uuid4())})
            self.bad_ack = True
            with self.assertRaises(RuntimeError):
                store.flush(self.url+'/qc/results')
            self.assertTrue(store.has_pending())
        finally:
            store.close()

    def test_one_process_per_delivery_directory(self):
        store = ResultStore(self.folder/'delivery')
        try:
            with self.assertRaises(RuntimeError):
                ResultStore(self.folder/'delivery')
        finally:
            store.close()
        ResultStore(self.folder/'delivery').close()

    def test_failed_atomic_write_does_not_create_partial_result(self):
        store = ResultStore(self.folder/'delivery')
        try:
            with patch('qc_station.storage.os.replace',side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    store.save({'inspection_id':str(uuid4())})
            self.assertFalse(store.has_pending())
            self.assertEqual(list(store.pending.iterdir()),[])
        finally:
            store.close()

    def test_invalid_claim_is_rejected(self):
        context = self.context()
        context['product_instance_id'] = True
        self.claims.append(context)
        with self.assertRaises(ValueError):
            TwinClient(self.url,'test').claim()

    def camera(self, mode, frames, once=True):
        image, polygons = scene('A')
        profile = create_variant_profile(image,polygons,'A',[80,10,450,445])
        path = self.folder/'profile.json'
        path.write_text(json.dumps(profile),encoding='utf-8')
        args = SimpleNamespace(profile=str(path),fps=10,width=640,height=480,
            product_instance_id=None,expected_variant=None,once=once,seconds=.3,min_samples=2,
            camera='0',output=str(self.folder),no_video=True,max_videos=10,station_id='test',
            headless=True,debug=False,order_context=None,mode=mode,twin_url=self.url)
        ticks = iter(i*.11 for i in range(1000))
        with patch('qc_station.__main__.cv2.VideoCapture') as capture, \
             patch('qc_station.__main__.time',SimpleNamespace(monotonic=lambda:next(ticks),perf_counter=time.perf_counter)), \
             patch('builtins.print') as printer:
            capture.return_value.isOpened.return_value = True
            capture.return_value.read.side_effect = [(True,frame.copy()) for frame in frames]+[(False,None)]
            if once and self.claims or mode=='manual':
                run(args)
            else:
                with self.assertRaisesRegex(RuntimeError,'Camera read failed'):
                    run(args)
            self.notices = ' '.join(str(call.args[0]) for call in printer.call_args_list)
        store = ResultStore(self.folder/'delivery')
        try:
            return store.events()
        finally:
            store.close()

    def test_manual_auto_recognition_is_sent_without_product_identity(self):
        image, _ = scene('D')
        event, = self.camera('manual',[image]*12)
        self.assertEqual(event['result']['detected_variant'],'D')
        self.assertEqual(event['result']['status'],'PASS')
        self.assertIsNone(event['product_instance_id'])
        self.assertEqual(self.claim_calls,0)
        self.assertEqual(self.received[event['inspection_id']],event)

    def test_order_wrong_variant_is_sent_as_fail(self):
        job = self.context()
        self.claims.append(job)
        image, _ = scene('B')
        event, = self.camera('order',[image]*12)
        self.assertEqual(event['inspection_id'],job['inspection_id'])
        self.assertEqual(event['product_instance_id'],1)
        self.assertEqual(event['result']['detected_variant'],'B')
        self.assertEqual(event['result']['status'],'FAIL')

    def test_order_waits_for_tracking_identity(self):
        image, _ = scene('A')
        self.assertEqual(self.camera('order',[image]*12),[])
        self.assertEqual(self.received,{})
        self.assertIn('no eligible product arrived at visual_qc', self.notices)

    def test_order_pass_is_sent_for_the_claimed_product_and_order(self):
        job = self.context('A', 42)
        self.claims.append(job)
        image, _ = scene('A')
        event, = self.camera('order', [image]*12)
        self.assertEqual(event['result']['status'], 'PASS')
        self.assertEqual(event['product_instance_id'], 42)
        self.assertEqual(event['order_id'], job['order_id'])
        self.assertEqual(event['arrival_event_id'], job['arrival_event_id'])
        self.assertEqual(event['expected_variant'], 'A')
        self.assertEqual(self.received[job['inspection_id']], event)
        self.assertIn('order=10, product=42, expected=A', self.notices)
        self.assertTrue(self.claim_payloads[0]['product_present'])

    def test_empty_camera_does_not_claim_next_order(self):
        import numpy as np
        self.assertEqual(self.camera('order', [np.full((480,640,3),65,np.uint8)]*12), [])
        self.assertEqual(self.claim_calls, 0)

    def test_two_cycles_keep_separate_identities_and_variants(self):
        import numpy as np
        jobs = [self.context('A',1),self.context('B',2)]
        self.claims.extend(jobs)
        a, _ = scene('A')
        b, _ = scene('B')
        events = self.camera('order',[a]*12+[np.zeros_like(a)]*15+[b]*12,once=False)
        self.assertEqual(len(events),2)
        for event in events:
            self.assertEqual(event['result']['status'],'PASS')
            self.assertEqual(event['result']['detected_variant'],event['expected_variant'])
        self.assertEqual({e['inspection_id'] for e in events},{j['inspection_id'] for j in jobs})
