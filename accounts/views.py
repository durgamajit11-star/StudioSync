from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib import messages
from django.views.decorators.cache import never_cache
from .forms import StyledAuthenticationForm
from .forms import UserRegisterForm, StudioRegisterForm


# ================= AUTH (LOGIN + REGISTER SINGLE PAGE) =================
@never_cache
def auth_view(request):

    # Redirect already logged-in users
    if request.user.is_authenticated:
        user = request.user
        if user.role == 'USER':
            return redirect('user_dashboard')
        elif user.role == 'STUDIO':
            return redirect('studio_dashboard')
        elif user.role == 'ADMIN':
            return redirect('admin_dashboard')

    login_form = StyledAuthenticationForm()
    user_form = UserRegisterForm()
    studio_form = StudioRegisterForm()
    active_tab = 'login'

    if request.method == 'POST':

        # ================= LOGIN =================
        if 'login_submit' in request.POST:
            active_tab = 'login'
            login_form = StyledAuthenticationForm(request, data=request.POST)

            if login_form.is_valid():
                user = login_form.get_user()
                login(request, user)

                if user.role == 'USER':
                    return redirect('user_dashboard')
                elif user.role == 'STUDIO':
                    return redirect('studio_dashboard')
                elif user.role == 'ADMIN':
                    return redirect('admin_dashboard')
            else:
                messages.error(request, "Invalid username or password!")

        # ================= USER REGISTER =================
        elif 'user_register_submit' in request.POST:
            active_tab = 'user'
            user_form = UserRegisterForm(request.POST)

            if user_form.is_valid():
                user_form.save()
                messages.success(request, "User registered successfully!")
                return redirect('auth_page')

        # ================= STUDIO REGISTER =================
        elif 'studio_register_submit' in request.POST:
            active_tab = 'studio'
            studio_form = StudioRegisterForm(request.POST, request.FILES)  # 🔥 IMPORTANT

            if studio_form.is_valid():
                studio_form.save()
                messages.success(request, "Studio registered successfully!")
                return redirect('auth_page')

    return render(request, 'accounts/auth.html', {
        'login_form': login_form,
        'user_form': user_form,
        'studio_form': studio_form,
        'active_tab': active_tab,
    })


# ================= LOGOUT =================
@never_cache
def logout_view(request):
    logout(request)
    return redirect("landing")   # 👈 THIS IS IMPORTANT
