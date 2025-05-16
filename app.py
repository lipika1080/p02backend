import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from bson.objectid import ObjectId
import requests
from database import get_db
from utils.email import send_email
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
CORS(app)

db = get_db()

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
API_VERSION = "2025-01-01-preview"

@app.route("/appointments", methods=["POST"])
def book_appointment():
    data = request.get_json()
    required_fields = ["customer_name", "email", "car_model", "service", "datetime"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    appointment = {
        "customer_name": data["customer_name"],
        "email": data["email"],
        "car_model": data["car_model"],
        "service": data["service"],
        "datetime": data["datetime"],
        "created_at": datetime.utcnow(),
        "invoice": None
    }

    result = db.appointments.insert_one(appointment)
    return jsonify({"id": str(result.inserted_id)}), 201

@app.route("/appointments", methods=["GET"])
def list_appointments():
    date_str = request.args.get("date")
    query = {}
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            start = date_obj
            end = date_obj + timedelta(days=1)
            query["datetime"] = {"$gte": start.isoformat(), "$lt": end.isoformat()}
        except ValueError:
            return jsonify({"error": "Invalid date format, must be YYYY-MM-DD"}), 400

    appointments = []
    for appt in db.appointments.find(query):
        appt["_id"] = str(appt["_id"])
        appointments.append(appt)
    return jsonify(appointments), 200

@app.route("/appointments/summary", methods=["GET"])
def appointment_summary():
    date_param = request.args.get("date")

    total_appointments = db.appointments.count_documents({})

    date_total = 0
    if date_param:
        try:
            date_obj = datetime.strptime(date_param, "%Y-%m-%d")
            start = date_obj.isoformat()
            end = (date_obj + timedelta(days=1)).isoformat()
            date_total = db.appointments.count_documents({
                "datetime": {"$gte": start, "$lt": end}
            })
        except ValueError:
            return jsonify({"error": "Invalid date format, must be YYYY-MM-DD"}), 400

    return jsonify({
        "total": total_appointments,
        "dateTotal": date_total
    }), 200


@app.route("/appointments/<id>/invoice", methods=["POST"])
def generate_invoice(id):
    appointment = db.appointments.find_one({"_id": ObjectId(id)})
    if not appointment:
        return jsonify({"error": "Appointment not found"}), 404

    prompt = (
        f"Generate an invoice for {appointment['customer_name']} (email: {appointment['email']}), "
        f"car: {appointment['car_model']}, service: {appointment['service']}, at {appointment['datetime']}."
    )

    headers = {
        "api-key": AZURE_OPENAI_KEY,
        "Content-Type": "application/json"
    }

    body = {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that generates a simple invoice."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }

    try:
        response = requests.post(
            AZURE_OPENAI_ENDPOINT,
            headers=headers,
            json=body
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Failed to generate invoice",
            "exception": str(e),
            "response_status": getattr(e.response, "status_code", None),
            "response_body": getattr(e.response, "text", None)
        }), 500

    invoice = response.json()["choices"][0]["message"]["content"].strip()
    db.appointments.update_one({"_id": ObjectId(id)}, {"$set": {"invoice": invoice}})
    return jsonify({"invoice": invoice}), 200

@app.route("/appointments/<id>/email-invoice", methods=["POST"])
def email_invoice(id):
    appointment = db.appointments.find_one({"_id": ObjectId(id)})
    if not appointment or not appointment.get("invoice"):
        return jsonify({"error": "Invoice not found"}), 404

    status = send_email(
        appointment["email"],
        f"Your Car Workshop Invoice #{id}",
        appointment["invoice"]
    )

    if status < 300:
        return jsonify({"sent_status": status}), 200
    else:
        return jsonify({"sent_status": status}), 500

if __name__ == "__main__":
    app.run(debug=True)
