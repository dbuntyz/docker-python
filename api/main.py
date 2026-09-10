import os
from flask import Flask, jsonify, request
import redis

app = Flask(__name__)

# Connect to Redis via external network (hostname 'redis', port 6371)
redis_host = os.getenv('REDIS_HOST', 'redis')
redis_port = int(os.getenv('REDIS_PORT', 6371))

redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)


@app.route('/')
def index():
    return jsonify({
        'service': 'Separate External API',
        'connected_to_redis_host': redis_host,
        'connected_to_redis_port': redis_port,
        'endpoints': {
            'GET /stats': 'Get Redis stats and current counter value',
            'POST /set-counter': 'Set counter value (e.g. {"value": 100})',
            'GET /health': 'Health check status'
        }
    })


@app.route('/stats', methods=['GET'])
def get_stats():
    try:
        counter = redis_client.get('counter') or 0
        all_keys = redis_client.keys('*')
        redis_info = redis_client.info()

        return jsonify({
            'status': 'success',
            'redis_status': 'Connected via External Network',
            'counter_value': int(counter),
            'total_keys_in_redis': len(all_keys),
            'redis_version': redis_info.get('redis_version')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/set-counter', methods=['POST'])
def set_counter():
    try:
        data = request.get_json() or {}
        new_val = int(data.get('value', 0))
        redis_client.set('counter', new_val)
        return jsonify({
            'status': 'success',
            'message': f'Counter successfully updated to {new_val}',
            'counter_value': new_val
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 400


@app.route('/health', methods=['GET'])
def health():
    try:
        is_alive = redis_client.ping()
        return jsonify({'status': 'healthy', 'redis_ping': is_alive})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503


if __name__ == '__main__':
    # Running API on port 5001
    app.run(host='0.0.0.0', port=5001, debug=True)
