import os
from flask import Flask, render_template
import redis

app = Flask(__name__)

# Connect to Redis (port 6371)
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6371))

redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=True)


@app.route('/')
def home():
    try:
        visits = redis_client.incr('counter')
        redis_status = 'Connected'
    except Exception as e:
        visits = 'N/A'
        redis_status = f'Error: {e}'

    return render_template('index.html', visits=visits, redis_status=redis_status)


@app.route('/api/counter')
def api_counter():
    try:
        visits = redis_client.incr('counter')
        return {
            'status': 'success',
            'redis_status': 'Connected',
            'visits': visits
        }
    except Exception as e:
        return {
            'status': 'error',
            'redis_status': f'Error: {e}',
            'visits': None
        }, 500


@app.route('/healthz')
def healthz():
    try:
        redis_client.ping()
        redis_status = 'Connected'
    except Exception as e:
        redis_status = f'Disconnected: {e}'

    return {
        'status': 'healthy',
        'service': 'flask-web',
        'redis_status': redis_status
    }, 200


@app.errorhandler(404)
def not_found(e):
    return {
        'error': {
            'code': 'NOT_FOUND',
            'message': 'The requested endpoint does not exist. Available endpoints: GET / and GET /api/counter'
        }
    }, 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
