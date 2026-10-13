from functools import wraps
import re
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.extensions import db

auth_bp = Blueprint("auth", __name__)


def normalize_account_details(data):
    username = str(data.get("username", "") or "").strip()
    email = str(data.get("email", "") or "").strip().lower()
    full_name = str(data.get("full_name", "") or "").strip()
    phone = re.sub(r"[^0-9+]", "", str(data.get("phone", "") or ""))
    site_name = str(data.get("site_name", "") or "").strip()
    password = str(data.get("password", "") or "")

    if len(username) < 3:
        return None, "Username must be at least 3 characters long."
    if len(full_name) < 2 or len(full_name) > 120:
        return None, "Enter your full name."
    if not re.fullmatch(r"[A-Za-z0-9._%+-]+@gmail\.com", email):
        return None, "Enter a valid Gmail address."
    if not re.fullmatch(r"\+?[1-9][0-9]{7,14}", phone):
        return None, "Enter a valid phone number with 8 to 15 digits."
    if len(site_name) < 2 or len(site_name) > 120:
        return None, "Enter your worksite or project name."
    if len(password) < 8:
        return None, "Password must be at least 8 characters long."

    return {
        "username": username,
        "email": email,
        "full_name": full_name,
        "phone": phone,
        "site_name": site_name,
        "password": password,
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


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_app.config["DEMO_MODE"]:
        return redirect(url_for("main.dashboard"))
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "user").strip().lower()
        remember = bool(request.form.get("remember"))

        user = User.query.filter_by(username=username).first()
        role_matches = user and (
            (selected_role == "admin" and user.is_admin) or
            (selected_role == "user" and user.is_standard_user)
        )
        if user and user.check_password(password) and role_matches:
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.username}!", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("main.dashboard"))
        else:
            flash("Invalid username, password, or account type.", "danger")

    return render_template("login.html")


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
        elif details["password"] != confirm:
            flash("Passwords do not match.", "danger")
        elif User.query.filter_by(username=details["username"]).first():
            flash("Username already exists. Please choose another.", "danger")
        elif User.query.filter_by(email=details["email"]).first():
            flash("That email address is already in use.", "danger")
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
            flash(f"Account created successfully! Welcome, {new_user.username}.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("register.html")


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
        return jsonify({"status": "error", "message": f"User '{details['username']}' already exists"}), 400
    if User.query.filter_by(email=details["email"]).first():
        return jsonify({"status": "error", "message": "That email address is already in use."}), 400

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
