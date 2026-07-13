from flask import Flask, redirect, render_template, request, url_for
import yaml

from rules import detect_trend, is_good_price
from storage import get_all_prices, get_connection, get_recent_prices

app = Flask(__name__)
CONFIG_PATH = "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)


def to_float(value):
    if value in (None, ""):
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


@app.route("/")
def dashboard():
    config = load_config()
    conn = get_connection()

    routes_data = []
    chart_data = []
    for route in config["routes"]:
        history = get_all_prices(conn, route["id"])
        latest_price = history[-1][1] if history else None

        good, _ = is_good_price(
            latest_price, [p for _, p in history], route.get("target_price"), route.get("target_percent_below_avg")
        ) if latest_price else (False, "")

        recent = get_recent_prices(conn, route["id"], days=7)
        trending_up, _ = detect_trend(
            recent, config["trend"]["window_3d_pct"], config["trend"]["window_7d_pct"]
        )

        routes_data.append({
            "route": route,
            "latest_price": latest_price,
            "good": good,
            "trending_up": trending_up,
        })
        chart_data.append({
            "id": route["id"],
            "dates": [d[:10] for d, _ in history],
            "prices": [p for _, p in history],
        })

    conn.close()
    return render_template(
        "dashboard.html", routes_data=routes_data, chart_data=chart_data,
        notification=config["notification"], active="dashboard",
    )


@app.route("/config")
def config_page():
    config = load_config()
    return render_template("config.html", config=config, active="config")


@app.route("/config/route/add", methods=["POST"])
def add_route():
    config = load_config()
    origin = request.form["origin"].strip().upper()
    destination = request.form["destination"].strip().upper()
    route_id = f"{origin.lower()}-{destination.lower()}"

    config["routes"].append({
        "id": route_id,
        "origin": origin,
        "destination": destination,
        "currency": request.form.get("currency", "BRL").strip().upper() or "BRL",
        "target_price": to_float(request.form.get("target_price")),
        "target_percent_below_avg": to_float(request.form.get("target_percent_below_avg")),
    })
    save_config(config)
    return redirect(url_for("config_page", saved=1))


@app.route("/config/route/<route_id>/edit", methods=["POST"])
def edit_route(route_id):
    config = load_config()
    for route in config["routes"]:
        if route["id"] == route_id:
            route["target_price"] = to_float(request.form.get("target_price"))
            route["target_percent_below_avg"] = to_float(request.form.get("target_percent_below_avg"))
    save_config(config)
    return redirect(url_for("config_page", saved=1))


@app.route("/config/route/<route_id>/delete", methods=["POST"])
def delete_route(route_id):
    config = load_config()
    config["routes"] = [r for r in config["routes"] if r["id"] != route_id]
    save_config(config)
    return redirect(url_for("config_page", saved=1))


@app.route("/config/settings", methods=["POST"])
def save_settings():
    config = load_config()
    config["trend"]["window_3d_pct"] = to_float(request.form.get("window_3d_pct"))
    config["trend"]["window_7d_pct"] = to_float(request.form.get("window_7d_pct"))
    config["notification"]["mode"] = request.form.get("notification_mode", "alert_only")
    config["miles"]["cost_per_thousand_brl"] = to_float(request.form.get("cost_per_thousand_brl"))
    save_config(config)
    return redirect(url_for("config_page", saved=1))


if __name__ == "__main__":
    app.run(debug=True, port=5050)
