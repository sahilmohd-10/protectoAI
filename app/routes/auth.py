from functools import wraps
import re
from typing import TypedDict, Optional, Any
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.extensions import db

auth_bp = Blueprint("auth", __name__)


class CountryPhoneSpec(TypedDict):
    name: str
    digits: list[int]
    example: str
    placeholder: str
    flag: str
    hint: str


DEFAULT_PHONE_SPEC: CountryPhoneSpec = {
    "name": "Other / International",
    "digits": [7, 8, 9, 10, 11, 12, 13, 14, 15],
    "example": "1234567890",
    "placeholder": "International number",
    "flag": "🌐",
    "hint": "7 to 15 digits required",
}

# Comprehensive Country Phone Specifications
# Defines calling code, country name, allowed national digit counts, placeholder, and flag emoji.
COUNTRY_PHONE_SPECS: dict[str, CountryPhoneSpec] = {
    "+91": {
        "name": "India",
        "digits": [10],
        "example": "9876543210",
        "placeholder": "98765 43210",
        "flag": "🇮🇳",
        "hint": "10 digits required for India"
    },
    "+1": {
        "name": "United States / Canada",
        "digits": [10],
        "example": "5551234567",
        "placeholder": "555 123 4567",
        "flag": "🇺🇸",
        "hint": "10 digits required for USA/Canada"
    },
    "+44": {
        "name": "United Kingdom",
        "digits": [10],
        "example": "7911123456",
        "placeholder": "7911 123456",
        "flag": "🇬🇧",
        "hint": "10 digits required for UK"
    },
    "+971": {
        "name": "United Arab Emirates",
        "digits": [9],
        "example": "501234567",
        "placeholder": "50 123 4567",
        "flag": "🇦🇪",
        "hint": "9 digits required for UAE"
    },
    "+966": {
        "name": "Saudi Arabia",
        "digits": [9],
        "example": "501234567",
        "placeholder": "50 123 4567",
        "flag": "🇸🇦",
        "hint": "9 digits required for Saudi Arabia"
    },
    "+61": {
        "name": "Australia",
        "digits": [9],
        "example": "412345678",
        "placeholder": "412 345 678",
        "flag": "🇦🇺",
        "hint": "9 digits required for Australia"
    },
    "+49": {
        "name": "Germany",
        "digits": [10, 11],
        "example": "15123456789",
        "placeholder": "151 23456789",
        "flag": "🇩🇪",
        "hint": "10 or 11 digits required for Germany"
    },
    "+33": {
        "name": "France",
        "digits": [9],
        "example": "612345678",
        "placeholder": "6 12 34 56 78",
        "flag": "🇫🇷",
        "hint": "9 digits required for France"
    },
    "+65": {
        "name": "Singapore",
        "digits": [8],
        "example": "81234567",
        "placeholder": "8123 4567",
        "flag": "🇸🇬",
        "hint": "8 digits required for Singapore"
    },
    "+81": {
        "name": "Japan",
        "digits": [10],
        "example": "9012345678",
        "placeholder": "90 1234 5678",
        "flag": "🇯🇵",
        "hint": "10 digits required for Japan"
    },
    "+86": {
        "name": "China",
        "digits": [11],
        "example": "13800138000",
        "placeholder": "138 0013 8000",
        "flag": "🇨🇳",
        "hint": "11 digits required for China"
    },
    "+55": {
        "name": "Brazil",
        "digits": [10, 11],
        "example": "11987654321",
        "placeholder": "11 98765 4321",
        "flag": "🇧🇷",
        "hint": "10 or 11 digits required for Brazil"
    },
    "+27": {
        "name": "South Africa",
        "digits": [9],
        "example": "711234567",
        "placeholder": "71 123 4567",
        "flag": "🇿🇦",
        "hint": "9 digits required for South Africa"
    },
    "+60": {
        "name": "Malaysia",
        "digits": [9, 10],
        "example": "123456789",
        "placeholder": "12 345 6789",
        "flag": "🇲🇾",
        "hint": "9 or 10 digits required for Malaysia"
    },
    "+92": {
        "name": "Pakistan",
        "digits": [10],
        "example": "3001234567",
        "placeholder": "300 123 4567",
        "flag": "🇵🇰",
        "hint": "10 digits required for Pakistan"
    },
    "+880": {
        "name": "Bangladesh",
        "digits": [10],
        "example": "1712345678",
        "placeholder": "171 234 5678",
        "flag": "🇧🇩",
        "hint": "10 digits required for Bangladesh"
    },
    "+": {
        "name": "Other / International",
        "digits": list(range(7, 16)),
        "example": "1234567890",
        "placeholder": "International number",
        "flag": "🌐",
        "hint": "7 to 15 digits required"
    },
}


def get_country_spec(country_code: str) -> CountryPhoneSpec:
    """Safely retrieves country phone specification or returns default fallback."""
    found = COUNTRY_PHONE_SPECS.get(country_code) or COUNTRY_PHONE_SPECS.get("+")
    if found is not None:
        return found
    return DEFAULT_PHONE_SPEC



def evaluate_password_strength(password: str) -> tuple[str, int]:
    """
    Evaluates password strength and returns a tuple of (label, score).
    Labels:
      - 'weak': score < 3 or length < 8
      - 'strong': score 3-4 and length >= 8
      - 'very_strong': score >= 5 and length >= 10
    """
    if not password:
        return "weak", 0

    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r"[a-z]", password):
        score += 1
    if re.search(r"[A-Z]", password):
        score += 1
    if re.search(r"[0-9]", password):
        score += 1
    if re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
        score += 1

    if len(password) < 8 or score < 3:
        return "weak", score
    elif score >= 5 and len(password) >= 10:
        return "very_strong", score
    else:
        return "strong", score


def normalize_account_details(data):
    """Validates and normalizes user input for registration and admin user creation."""
    username = str(data.get("username", "") or "").strip()
    email = str(data.get("email", "") or "").strip().lower()
    full_name = str(data.get("full_name", "") or "").strip()
    site_name = str(data.get("site_name", "") or "").strip()
    password = str(data.get("password", "") or "")
    country_code = str(data.get("country_code", "+91") or "+91").strip()
    if not country_code.startswith("+"):
        country_code = "+" + country_code

    raw_phone = str(data.get("phone", "") or "").strip()

    # 1. Username validation
    if len(username) < 3:
        return None, "Username must be at least 3 characters long."
    if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
        return None, "Username may only contain letters, numbers, periods, dashes, and underscores."

    # 2. Full Name validation
    if len(full_name) < 2 or len(full_name) > 120:
        return None, "Enter your full name (2 to 120 characters)."

    # 3. Email validation
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        return None, "Enter a valid email address."

    # 4. Phone number parsing & country-specific digit validation
    # Extract raw digits from input
    cleaned_digits = re.sub(r"[^0-9]", "", raw_phone)
    code_digits = country_code.replace("+", "")

    # If the user typed the phone with the country code already prefixed, strip it to isolate national digits
    if cleaned_digits.startswith(code_digits) and len(cleaned_digits) > len(code_digits):
        national_digits = cleaned_digits[len(code_digits):]
    else:
        national_digits = cleaned_digits

    spec: CountryPhoneSpec = get_country_spec(country_code)
    expected_digits: list[int] = spec["digits"]
    country_name: str = spec["name"]

    if country_code == "+91":
        if len(national_digits) != 10:
            return None, f"India (+91) phone number must be exactly 10 digits (entered {len(national_digits)} digits)."
    elif len(national_digits) not in expected_digits:
        expected_desc = f"{expected_digits[0]} digits" if len(expected_digits) == 1 else f"{expected_digits[0]} to {expected_digits[-1]} digits"
        return None, f"{country_name} ({country_code}) phone number must be {expected_desc} (entered {len(national_digits)} digits)."

    full_phone = f"{country_code}{national_digits}"

    # 5. Worksite / Project validation
    if len(site_name) < 2 or len(site_name) > 120:
        return None, "Enter your worksite or project name."

    # 6. Password validation & strength
    if len(password) < 8:
        return None, "Password must be at least 8 characters long."

    strength_label, strength_score = evaluate_password_strength(password)

    return {
        "username": username,
        "email": email,
        "full_name": full_name,
        "phone": full_phone,
        "country_code": country_code,
        "national_phone": national_digits,
        "site_name": site_name,
        "password": password,
        "password_strength": strength_label,
        "password_score": strength_score,
    }, None


def admin_required(f):
    """Decorator to restrict route execution to administrators only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.url))
        if not current_user.is_admin:
            flash("Administrator privileges required for this action.", "danger")
            return redirect(url_for("main.dashboard"))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------------------------------------------
# Real-Time Validation APIs
# -------------------------------------------------------------

@auth_bp.route("/check-username", methods=["GET"])
def check_username():
    """Real-time API to check if a username already exists in the database."""
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({
            "status": "empty",
            "exists": False,
            "available": False,
            "message": "Please enter a username."
        })
    if len(username) < 3:
        return jsonify({
            "status": "too_short",
            "exists": False,
            "available": False,
            "message": "Username must be at least 3 characters long."
        })

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({
            "status": "exists",
            "exists": True,
            "available": False,
            "message": f"Username '{username}' already exists in database. Please choose another."
        })
    return jsonify({
        "status": "available",
        "exists": False,
        "available": True,
        "message": f"Username '{username}' is available!"
    })


@auth_bp.route("/check-phone", methods=["GET"])
def check_phone():
    """Real-time API to validate phone number length per selected country and database existence."""
    country_code = request.args.get("country_code", "+91").strip()
    raw_phone = request.args.get("phone", "").strip()

    digits = re.sub(r"[^0-9]", "", raw_phone)
    code_digits = country_code.replace("+", "")
    if digits.startswith(code_digits) and len(digits) > len(code_digits):
        national_digits = digits[len(code_digits):]
    else:
        national_digits = digits

    spec: CountryPhoneSpec = get_country_spec(country_code)
    expected: list[int] = spec["digits"]
    is_valid: bool = len(national_digits) in expected
    full_phone = f"{country_code}{national_digits}"

    exists = False
    if is_valid:
        exists = bool(User.query.filter_by(phone=full_phone).first())

    country_name: str = spec["name"]
    hint_text: str = spec["hint"]
    msg = "Valid number" if is_valid else f"{country_name} ({country_code}) requires {expected[0] if len(expected) == 1 else f'{expected[0]}-{expected[-1]}'} digits"

    return jsonify({
        "valid": is_valid,
        "country_code": country_code,
        "country_name": country_name,
        "digits_entered": len(national_digits),
        "expected_digits": expected,
        "exists": exists,
        "full_phone": full_phone,
        "hint": hint_text,
        "message": msg
    })


@auth_bp.route("/check-password-strength", methods=["POST"])
def check_password_strength():
    """Evaluates password strength and returns parameter: weak, strong, or very_strong."""
    data = request.get_json(silent=True) or {}
    password = data.get("password", "")
    label, score = evaluate_password_strength(password)
    return jsonify({
        "strength": label,  # 'weak', 'strong', 'very_strong'
        "score": score,
        "has_min_len": len(password) >= 8,
        "has_upper": bool(re.search(r"[A-Z]", password)),
        "has_lower": bool(re.search(r"[a-z]", password)),
        "has_number": bool(re.search(r"[0-9]", password)),
        "has_symbol": bool(re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password)),
    })


# -------------------------------------------------------------
# Authentication Views
# -------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_app.config["DEMO_MODE"]:
        return redirect(url_for("main.dashboard"))
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "user").strip().lower()
        remember = bool(request.form.get("remember"))

        # Look up user by username, email, or phone number (with or without +91)
        phone_cleaned = re.sub(r"[^0-9+]", "", identifier)
        phone_national = re.sub(r"[^0-9]", "", identifier)

        user = User.query.filter(
            (User.username == identifier) |
            (User.email == identifier.lower()) |
            (User.phone == identifier) |
            (User.phone == phone_cleaned) |
            (User.phone == f"+91{phone_national}" if len(phone_national) == 10 else False)
        ).first()

        role_matches = user and (
            (selected_role == "admin" and user.is_admin) or
            (selected_role == "user" and user.is_standard_user)
        )

        if user and user.check_password(password) and role_matches:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.full_name or user.username}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))
        else:
            if not user:
                flash("No account found with this username, email, or phone number.", "danger")
            elif not user.check_password(password):
                flash("Incorrect password. Please verify and try again.", "danger")
            elif not role_matches:
                flash(f"Account '{user.username}' is registered as a {user.role.title()}, not {selected_role.title()}.", "danger")
            else:
                flash("Invalid login credentials.", "danger")

    return render_template("login.html", country_specs=COUNTRY_PHONE_SPECS)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Sign up / create account option for new users."""
    if current_app.config["DEMO_MODE"]:
        flash("Account creation is disabled in the public demo.", "info")
        return redirect(url_for("main.dashboard"))
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        details, error = normalize_account_details(request.form)
        confirm = request.form.get("confirm_password", "")

        if error or not details:
            flash(error or "Invalid details provided.", "danger")
            return render_template("register.html", form_data=request.form, country_specs=COUNTRY_PHONE_SPECS)
        elif details["password"] != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", form_data=request.form, country_specs=COUNTRY_PHONE_SPECS)
        elif User.query.filter_by(username=details["username"]).first():
            flash(f"Username '{details['username']}' already exists in database. Please choose another.", "danger")
            return render_template("register.html", form_data=request.form, country_specs=COUNTRY_PHONE_SPECS)
        elif User.query.filter_by(email=details["email"]).first():
            flash("That email address is already in use.", "danger")
            return render_template("register.html", form_data=request.form, country_specs=COUNTRY_PHONE_SPECS)
        elif User.query.filter_by(phone=details["phone"]).first():
            flash("That phone number is already registered.", "danger")
            return render_template("register.html", form_data=request.form, country_specs=COUNTRY_PHONE_SPECS)
        else:
            is_first_user = (User.query.count() == 0)
            new_user = User(
                username=details["username"],
                email=details["email"],
                full_name=details["full_name"],
                phone=details["phone"],
                site_name=details["site_name"],
                role="admin" if is_first_user else "user",
            )
            new_user.set_password(details["password"])
            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            strength_title = details['password_strength'].replace('_', ' ').title()
            flash(f"Account created successfully! Welcome, {new_user.username}. Password security: {strength_title}.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("register.html", country_specs=COUNTRY_PHONE_SPECS)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# -------------------------------------------------------------
# Admin User Management APIs (Admin Functionality)
# -------------------------------------------------------------

@auth_bp.route("/api/users", methods=["GET"])
@admin_required
def list_users():
    """Admin-only: list all registered user accounts."""
    users = User.query.order_by(User.id.asc()).all()
    return jsonify({
        "status": "success",
        "users": [u.to_dict() for u in users]
    })


@auth_bp.route("/api/users", methods=["POST"])
@admin_required
def create_user_by_admin():
    """Admin-only: create a new user with specific role (admin or user)."""
    data = request.get_json() or {}
    details, error = normalize_account_details(data)
    role = str(data.get("role", "user") or "user").strip().lower()
    if error or not details:
        return jsonify({"status": "error", "message": error or "Invalid user details."}), 400
    if role not in ("admin", "user"):
        return jsonify({"status": "error", "message": "Role must be Admin or User."}), 400

    if User.query.filter_by(username=details["username"]).first():
        return jsonify({"status": "error", "message": f"User '{details['username']}' already exists in database"}), 400
    if User.query.filter_by(email=details["email"]).first():
        return jsonify({"status": "error", "message": "That email address is already in use."}), 400
    if User.query.filter_by(phone=details["phone"]).first():
        return jsonify({"status": "error", "message": "That phone number is already in use."}), 400

    user = User(
        username=details["username"],
        email=details["email"],
        full_name=details["full_name"],
        phone=details["phone"],
        site_name=details["site_name"],
        role=role,
    )
    user.set_password(details["password"])
    db.session.add(user)
    db.session.commit()

    return jsonify({
        "status": "success",
        "message": f"User '{details['username']}' created successfully as {role}.",
        "user": user.to_dict()
    })


@auth_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user_by_admin(user_id):
    """Admin-only: delete a user account."""
    if user_id == current_user.id:
        return jsonify({"status": "error", "message": "You cannot delete your own account."}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    if user.is_admin and User.query.filter_by(role="admin").count() <= 1:
        return jsonify({"status": "error", "message": "At least one administrator account must remain."}), 400

    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "success", "message": f"User '{user.username}' deleted."})


@auth_bp.route("/api/users/<int:user_id>", methods=["PATCH"])
@admin_required
def update_user_role(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    role = (request.get_json() or {}).get("role", "").strip().lower()
    if role not in ("admin", "user"):
        return jsonify({"status": "error", "message": "Role must be admin or user."}), 400
    if user.id == current_user.id and role != "admin":
        return jsonify({"status": "error", "message": "You cannot remove your own administrator access."}), 400
    if user.is_admin and role != "admin" and User.query.filter_by(role="admin").count() <= 1:
        return jsonify({"status": "error", "message": "At least one administrator account must remain."}), 400

    user.role = role
    db.session.commit()
    return jsonify({"status": "success", "message": f"{user.username}'s role updated to {role}.", "user": user.to_dict()})
