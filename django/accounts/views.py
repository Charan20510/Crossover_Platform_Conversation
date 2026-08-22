
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import password_validation
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect

from .models import Account
from .utils import get_account

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("core:overview")

    errors = []
    form = {}

    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in
                ("username", "email", "full_name", "password", "confirm")}

        if not form["username"]:
            errors.append("Username is required.")
        elif User.objects.filter(username=form["username"]).exists():
            errors.append("That username is already taken.")

        if not form["email"]:
            errors.append("Email is required.")
        elif User.objects.filter(email=form["email"]).exists():
            errors.append("An account with this email already exists.")
        elif Account.objects.filter(email=form["email"]).exists():
            errors.append("An account with this email already exists.")

        if form["password"] != form["confirm"]:
            errors.append("Passwords do not match.")
        else:
            try:
                password_validation.validate_password(form["password"])
            except ValidationError as e:
                errors.extend(e.messages)

        if not errors:
            user = User.objects.create_user(
                username=form["username"],
                email=form["email"],
                password=form["password"],
            )
            first, *rest = (form["full_name"].split(" ", 1) + [""])[:2]
            user.first_name = first
            user.last_name = rest[0] if rest else ""
            user.save(update_fields=["first_name", "last_name"])

            Account.objects.create(
                user=user,
                name=form["full_name"] or form["username"],
                email=form["email"],
            )

            login(request, user)
            return redirect("core:overview")

    return render(request, "accounts/signup.html", {"errors": errors, "form": form})

def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:overview")

    error = None
    username_val = ""

    if request.method == "POST":
        username_val = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username_val, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next") or "core:overview"
            if next_url.startswith("/"):
                return redirect(next_url)
            return redirect("core:overview")
        else:
            error = "Incorrect username or password."

    return render(request, "accounts/login.html", {
        "error": error,
        "username_val": username_val,
        "next": request.GET.get("next", ""),
    })

def logout_view(request):
    logout(request)
    return redirect("accounts:login")

@login_required
def profile_view(request):
    account = get_account(request)
    devices = account.devices.all()
    return render(request, "accounts/profile.html", {
        "account": account,
        "user": request.user,
        "devices": devices,
    })
