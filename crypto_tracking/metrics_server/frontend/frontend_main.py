import requests
from flask import Flask, render_template, request

app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def home() -> str:
    return render_template("main.html")


@app.route("/threshold", methods=["GET", "POST"])
def set_threshold() -> str:
    if request.method == "POST":
        min_num = request.form["min_num"]
        max_num = request.form["max_num"]
        currency_type = request.form["currency_type"]

        localhost_url: str = "http://localhost:5001"
        # Send the numbers to the backend server
        response = requests.post(
            localhost_url + "/api/numbers",
            json={"min_num": min_num, "max_num": max_num, "currency_type": currency_type},
            timeout=60,
        )
        response.raise_for_status()
        return "Numbers sent successfully!"
    return render_template("threshold.html")


def main() -> None:
    app.run(debug=True)


if __name__ == "__main__":
    main()
