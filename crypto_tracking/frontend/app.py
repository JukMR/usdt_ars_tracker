from flask import Flask, render_template, request
import requests

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        min_num = request.form["min_num"]
        max_num = request.form["max_num"]
        # Send the numbers to the backend server
        response = requests.post("http://localhost/api/numbers:5001", json={"min_num": min_num, "max_num": max_num})
        return "Numbers sent successfully!"
        response.raise_for_status()
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
