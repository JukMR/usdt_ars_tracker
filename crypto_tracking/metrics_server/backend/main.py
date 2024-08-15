from flask import Flask, Response, jsonify, request

app = Flask(__name__)


@app.route("/metrics", methods=["GET"])
def get_current_price():
    current_value = read_value()
    return current_value


# Define a route to handle the numbers
@app.route("/api/numbers", methods=["POST"])
def handle_numbers() -> Response:
    data = request.get_json()
    print("received post")

    min_num = data["min_num"]
    max_num = data["max_num"]
    # Process the numbers here (e.g., store them in a database, perform calculations, etc.)
    print(f"Received numbers: min={min_num}, max={max_num}")
    return jsonify({"message": "Numbers received successfully!"})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
