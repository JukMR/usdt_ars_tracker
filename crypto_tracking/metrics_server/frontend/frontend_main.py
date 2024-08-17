import requests
from flask import Flask, render_template, request

app = Flask(__name__)

localhost_url: str = "http/localhost/api/numbers:5001"


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        min_num = request.form["min_num"]
        max_num = request.form["max_num"]

        # Send the numbers to the backend server
        response = requests.post(localhost_url, json={"min_num": min_num, "max_num": max_num}, timeout=60)
        response.raise_for_status()
        return "Numbers sent successfully!"
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=False)
