from adapter import Adapter
from flask import Flask, request, jsonify
from job_manager import JobManager
import datetime
import threading
import uuid

app = Flask(__name__)
job_manager = JobManager()

@app.route('/adapt', methods=['POST'])
def adapt():
    request_data = request.get_json()
    eln = request_data['eln']
    experiment_id = request_data['id']
    data = request_data.get('data', {})  # Additional data (user, fields, etc.)
    adapter = Adapter()
    result = adapter.adapt(eln, experiment_id, data)
    return jsonify(result)

@app.route('/adapt-async', methods=['POST'])
def adapt_async():
    """Start async job and return job ID immediately"""
    request_data = request.get_json()
    eln = request_data['eln']
    experiment_id = request_data['id']
    data = request_data.get('data', {})

    # Generate unique job ID
    job_id = str(uuid.uuid4())

    # Create job
    job_manager.create_job(job_id)

    # Run adapter in background thread
    def run_adapter():
        try:
            job_manager.update_job(job_id, status='running')
            adapter = Adapter()
            result = adapter.adapt(eln, experiment_id, data)
            job_manager.update_job(job_id, status='completed', result=result)
        except Exception as e:
            job_manager.update_job(job_id, status='failed', error=str(e))

    thread = threading.Thread(target=run_adapter)
    thread.daemon = True
    thread.start()

    return jsonify({'job_id': job_id, 'status': 'pending'})

@app.route('/job/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status"""
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/test', methods=['POST'])
def test():
    return jsonify(success=True)

@app.route('/status', methods=['GET'])
def status():
    adapter = Adapter()
    return jsonify(adapter.get_status())

@app.route('/plugin-info/<plugin_name>', methods=['GET'])
def plugin_info(plugin_name):
    adapter = Adapter()
    return jsonify(adapter.get_plugin_info(plugin_name))

# No app.run() here: the service is started via gunicorn (see Dockerfile and service/).
# Use a single worker, as async jobs run in-process.
