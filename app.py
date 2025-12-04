from adapter import Adapter
from flask import Flask, request, jsonify
import datetime

app = Flask(__name__)

@app.route('/adapt', methods=['POST'])
def adapt():
    data = request.get_json()
    eln = data['eln']
    experiment_id = data['id']
    user = data.get('user', None)  # Optional user parameter
    adapter = Adapter()
    result = adapter.adapt(eln, experiment_id, user)
    return jsonify(result)

@app.route('/test', methods=['POST'])
def test():
    return jsonify(success=True)

@app.route('/status', methods=['GET'])
def status():
    adapter = Adapter()
    return jsonify(adapter.get_status())

if __name__ == '__main__':
    app.run(debug=True)