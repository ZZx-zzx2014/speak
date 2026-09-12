"""Socket.IO behaviour tests (authentication, broadcast, history, limits)."""

import unittest

from speak import socketio

from .base import AppTestCase


def names(packets):
    return [packet['name'] for packet in packets]


def payload(packets, event):
    return [packet['args'][0] for packet in packets if packet['name'] == event]


class AnonymousSocketTest(AppTestCase):
    def test_connection_is_refused_without_a_session(self):
        anonymous = self.app.test_client()
        client = socketio.test_client(self.app, flask_test_client=anonymous)
        self.assertFalse(client.is_connected())


class AuthenticatedSocketTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.register(username='alice')
        self.login()
        self.socket = socketio.test_client(self.app, flask_test_client=self.client)

    def tearDown(self):
        try:
            self.socket.disconnect()
        except Exception:
            pass
        super().tearDown()

    def _join(self):
        self.socket.emit('join', {})
        return self.socket.get_received()

    def test_connection_is_accepted(self):
        self.assertTrue(self.socket.is_connected())

    def test_join_announces_and_reports_presence(self):
        packets = self._join()
        self.assertIn('history', names(packets))
        self.assertIn('system_message', names(packets))
        counts = [p['count'] for p in payload(packets, 'presence')]
        self.assertEqual(counts[-1], 1)

    def test_message_is_broadcast_to_the_room(self):
        self._join()
        self.socket.emit('chat_message', {'msg': 'hello world'})
        messages = payload(self.socket.get_received(), 'chat_message')

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['msg'], 'hello world')
        self.assertEqual(messages[0]['username'], 'alice')
        self.assertIn('ts', messages[0])

    def test_oversized_message_is_rejected(self):
        self._join()
        self.socket.emit('chat_message', {'msg': 'x' * 5000})
        packets = self.socket.get_received()

        self.assertNotIn('chat_message', names(packets))
        self.assertIn('system_message', names(packets))

    def test_empty_and_malformed_payloads_are_ignored(self):
        self._join()
        for bad in ({'msg': '   '}, {}, None, 'not-a-dict', {'msg': 5}):
            self.socket.emit('chat_message', bad)
            self.assertNotIn('chat_message', names(self.socket.get_received()))

    def test_history_is_replayed_to_a_late_joiner(self):
        self._join()
        self.socket.emit('chat_message', {'msg': 'first'})
        self.socket.get_received()

        second = socketio.test_client(self.app, flask_test_client=self.client)
        try:
            second.emit('join', {})
            history = payload(second.get_received(), 'history')
            self.assertEqual(len(history), 1)
            self.assertEqual([m['msg'] for m in history[0]['messages']], ['first'])
        finally:
            second.disconnect()

    def test_disconnect_is_announced_to_the_room(self):
        observer = socketio.test_client(self.app, flask_test_client=self.client)
        try:
            observer.emit('join', {})
            observer.get_received()

            self._join()
            observer.get_received()

            self.socket.disconnect()
            self.socket = socketio.test_client(self.app, flask_test_client=self.client)

            announcements = payload(observer.get_received(), 'system_message')
            self.assertTrue(any('离开' in item['msg'] for item in announcements))
        finally:
            observer.disconnect()

    def test_markup_is_delivered_verbatim_and_escaped_client_side(self):
        self._join()
        payload_text = '<img src=x onerror=alert(1)>'
        self.socket.emit('chat_message', {'msg': payload_text})
        messages = payload(self.socket.get_received(), 'chat_message')
        self.assertEqual(messages[0]['msg'], payload_text)


if __name__ == '__main__':
    unittest.main()
