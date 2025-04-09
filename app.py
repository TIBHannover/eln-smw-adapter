from adapter import Adapter
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/adapt', methods=['POST'])
def adapt():
    data = request.get_json()
    eln = data['eln']
    experiment_id = data['id']
    adapter = Adapter()
    result = adapter.adapt(eln, experiment_id)
    return jsonify(result)

@app.route('/test', methods=['POST'])
def test():
    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)