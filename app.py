"""
SignAI - Sign Language Interpreter Backend
Flask + Socket.IO server for frontend serving, TTS, AI Interpretation, and WebRTC signaling
"""

import base64
import io
import os

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from gtts import gTTS

app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = 'signai-secret-2024'
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Track connected users for pairing
waiting_users = []
active_rooms = {}

# ── Serve Frontend ──────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# ── Health Check ────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'SignAI Backend', 'version': '2.1.0'})

# ── Text to Speech ──────────────────────────────────────────────────
@app.route('/tts', methods=['POST'])
def text_to_speech():
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    try:
        tts = gTTS(text=text, lang=data.get('lang', 'en'), slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_b64 = base64.b64encode(buf.read()).decode()
        return jsonify({'audio': 'data:audio/mp3;base64,' + audio_b64, 'text': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── AI Interpretation ───────────────────────────────────────────────
@app.route('/interpret', methods=['POST'])
def interpret():
    data = request.get_json()
    text = data.get('text', '')
    interp = {
        'HELLO': 'Greeting: "Hello!" — A standard ASL greeting wave.',
        'I LOVE YOU': '"I love you" — The iconic ILY handshape combining I, L, Y.',
        'YES': 'Affirmation: "Yes" — Fist nodding motion.',
        'NO': 'Negation: "No" — Index and middle fingers snapping on thumb.',
        'THANK YOU': 'Gratitude: "Thank you" — Hand moves from chin forward.',
        'OK': 'Approval: "OK" or "Good"',
        'CALL ME': '"Call me" — Phone shape with thumb and pinky.',
        'GOOD': 'Positive affirmation: "Good"',
        'WAIT': 'Request to pause: "Wait"',
    }
    t = text.upper().strip()
    result = interp.get(t, None)
    if not result:
        if len(t) <= 5:
            result = f'Detected letters: {"-".join(t)}. This may spell a short word.'
        else:
            result = f'Detected sequence: "{text}". A series of ASL signs.'
    return jsonify({'interpretation': result, 'text': text})

# ── WebRTC Signaling via Socket.IO ──────────────────────────────────
@socketio.on('connect')
def on_connect():
    print(f'[WS] Client connected: {request.sid}')
    emit('status', {'connected': True, 'sid': request.sid})

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    print(f'[WS] Client disconnected: {sid}')
    if sid in waiting_users:
        waiting_users.remove(sid)
    # Clean up rooms
    for room_id, members in list(active_rooms.items()):
        if sid in members:
            members.remove(sid)
            for other in members:
                emit('peer_left', {'sid': sid}, room=other)
            if not members:
                del active_rooms[room_id]

@socketio.on('join_call')
def on_join_call(data):
    sid = request.sid
    room_id = data.get('room', 'default')
    join_room(room_id)
    if room_id not in active_rooms:
        active_rooms[room_id] = []
    active_rooms[room_id].append(sid)
    others = [s for s in active_rooms[room_id] if s != sid]
    emit('room_joined', {'room': room_id, 'peers': others, 'you': sid})
    # Notify others that a new peer joined
    for other_sid in others:
        emit('new_peer', {'sid': sid}, room=other_sid)
    print(f'[WS] {sid} joined room {room_id}, peers: {others}')

@socketio.on('leave_call')
def on_leave_call(data):
    sid = request.sid
    room_id = data.get('room', 'default')
    leave_room(room_id)
    if room_id in active_rooms and sid in active_rooms[room_id]:
        active_rooms[room_id].remove(sid)
        for other in active_rooms[room_id]:
            emit('peer_left', {'sid': sid}, room=other)
        if not active_rooms[room_id]:
            del active_rooms[room_id]

@socketio.on('webrtc_offer')
def on_offer(data):
    target = data.get('target')
    if target:
        emit('webrtc_offer', {'sdp': data['sdp'], 'sender': request.sid}, room=target)

@socketio.on('webrtc_answer')
def on_answer(data):
    target = data.get('target')
    if target:
        emit('webrtc_answer', {'sdp': data['sdp'], 'sender': request.sid}, room=target)

@socketio.on('webrtc_ice')
def on_ice(data):
    target = data.get('target')
    if target:
        emit('webrtc_ice', {'candidate': data['candidate'], 'sender': request.sid}, room=target)

@socketio.on('call_sign')
def on_call_sign(data):
    """Broadcast detected sign to peers in the same room"""
    room_id = data.get('room', 'default')
    emit('remote_sign', {'sign': data.get('sign', ''), 'sender': request.sid}, room=room_id, include_self=False)

# ── Main ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"""
╔══════════════════════════════════════════════╗
║   SignAI — Sign Language Interpreter         ║
║   Server v2.1.0 (with Video Call)            ║
║   http://localhost:{port}                      ║
╚══════════════════════════════════════════════╝
    """)
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
