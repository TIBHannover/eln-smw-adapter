import os
import json
import time
import threading

class JobManager:
    def __init__(self):
        self.jobs_dir = os.path.join(os.path.dirname(__file__), 'jobs')
        if not os.path.exists(self.jobs_dir):
            os.makedirs(self.jobs_dir)

    def create_job(self, job_id):
        """Create a new job with pending status"""
        job_file = os.path.join(self.jobs_dir, f'{job_id}.json')
        job_data = {
            'id': job_id,
            'status': 'pending',
            'created_at': time.time(),
            'updated_at': time.time(),
            'result': None,
            'error': None
        }
        with open(job_file, 'w') as f:
            json.dump(job_data, f)
        return job_data

    def update_job(self, job_id, status=None, result=None, error=None):
        """Update job status"""
        job_file = os.path.join(self.jobs_dir, f'{job_id}.json')
        if not os.path.exists(job_file):
            return None

        with open(job_file, 'r') as f:
            job_data = json.load(f)

        if status:
            job_data['status'] = status
        if result is not None:
            job_data['result'] = result
        if error:
            job_data['error'] = error
        job_data['updated_at'] = time.time()

        with open(job_file, 'w') as f:
            json.dump(job_data, f)

        return job_data

    def get_job(self, job_id):
        """Get job status"""
        job_file = os.path.join(self.jobs_dir, f'{job_id}.json')
        if not os.path.exists(job_file):
            return None

        with open(job_file, 'r') as f:
            return json.load(f)

    def cleanup_old_jobs(self, max_age_hours=24):
        """Remove job files older than max_age_hours"""
        now = time.time()
        max_age_seconds = max_age_hours * 3600

        for filename in os.listdir(self.jobs_dir):
            if filename.endswith('.json'):
                file_path = os.path.join(self.jobs_dir, filename)
                if os.path.getmtime(file_path) < (now - max_age_seconds):
                    os.remove(file_path)
