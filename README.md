# PhotoStudioPlatform

PhotoStudioPlatform is a Django-based marketplace for photography studios. It supports studio discovery, booking management, payments, reviews, recommendations, notifications, chatbot assistance, and role-based dashboards for users, studios, and administrators.

## Features

- Studio browsing and discovery
- Booking creation, approval, and payment tracking
- Demo UPI payments and Razorpay checkout support
- User and studio dashboards
- Reviews and recommendations
- Notifications
- Chatbot assistance
- REST API endpoints for app integration
- Admin and custom management panels

## Tech Stack

- Python 3.12
- Django 6
- Django REST Framework
- Gunicorn
- Whitenoise
- PostgreSQL support via `DATABASE_URL`
- Cloudinary support for uploaded media

## Project Layout

- `accounts/` - custom users, authentication, and profile logic
- `studios/` - studio models, listings, and studio-facing features
- `bookings/` - booking requests and booking workflow
- `payments/` - payment records, demo checkout, Razorpay integration, and refunds
- `reviews/` - review models and review-related logic
- `chatbot/` - chatbot responses and intents
- `recommendations/` - recommendation logic
- `notifications/` - notification delivery and listing
- `dashboard/` - user and studio dashboard views
- `adminpanel/` - custom admin views
- `api/` - API serializers and routes
- `templates/` - HTML templates
- `static/` - project static assets
- `media/` - local uploads and generated media during development

## Prerequisites

- Python 3.12
- pip
- A virtual environment tool such as `venv`
- PostgreSQL for production deployments
- Cloudinary account if you want persistent media storage in production

## Quick Start

1. Create and activate a virtual environment.

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies.

   ```powershell
   pip install -r requirements.txt
   ```

3. Create a local environment file.

   ```powershell
   Copy-Item .env.example .env
   ```

4. Set the required values in `.env`.

5. Run migrations.

   ```powershell
   python manage.py migrate
   ```

6. Create an admin user.

   ```powershell
   python manage.py createsuperuser
   ```

7. Start the development server.

   ```powershell
   python manage.py runserver
   ```

Open `http://127.0.0.1:8000/` in your browser.

## Environment Variables

Use `.env.example` as the source of truth. The most important values are:

- `DJANGO_SECRET_KEY` - Django secret key
- `DJANGO_DEBUG` - enable or disable debug mode
- `DJANGO_ALLOWED_HOSTS` - comma-separated allowed hosts
- `DATABASE_URL` - PostgreSQL connection string for production
- `ENABLE_WHITENOISE` - serve static files with Whitenoise
- `CLOUDINARY_URL` - Cloudinary connection string for media uploads
- `USE_CLOUDINARY_MEDIA` - enable Cloudinary-backed media storage
- `PAYMENT_GATEWAY_MODE` - `demo` or `razorpay`
- `RAZORPAY_KEY_ID` - Razorpay key id
- `RAZORPAY_KEY_SECRET` - Razorpay key secret
- `RAZORPAY_WEBHOOK_SECRET` - Razorpay webhook secret

## Local Development Notes

- SQLite is fine for local development.
- For production on serverless platforms, use PostgreSQL instead of SQLite.
- If `USE_CLOUDINARY_MEDIA=True`, uploaded media is stored in Cloudinary.
- If `PAYMENT_GATEWAY_MODE=demo`, payments use the manual/demo flow.
- If `PAYMENT_GATEWAY_MODE=razorpay`, the Razorpay checkout flow is enabled.

## Database And Static Files

- Run migrations after changing models.
- Use `python manage.py collectstatic` only when needed for production builds that serve static assets.
- The repository uses `static/` for source assets and `staticfiles/` only as collected build output.

## Deployment

### Vercel

This project includes a `vercel.json` configuration for Vercel deployment.

- `api/index.py` is used as the Python server entrypoint.
- Static assets are served from `static/`.
- The repo is configured to avoid `collectstatic` on Vercel via `DISABLE_COLLECTSTATIC=1`.

### Procfile / Gunicorn

The `Procfile` contains the Gunicorn command used by Procfile-based hosts such as Heroku or similar platforms.

## Useful Commands

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

## API

The project exposes routes under `/api/`, plus a performance ingestion endpoint at `/api/perf/web-vitals/`.

## Notes

- The project uses a custom user model: `accounts.CustomUser`.
- Authentication routes are mounted under `/accounts/`.
- Main app routes are mounted under `/dashboard/`, `/studios/`, `/bookings/`, `/payments/`, `/notifications/`, `/recommendations/`, `/chatbot/`, and `/api/`.
